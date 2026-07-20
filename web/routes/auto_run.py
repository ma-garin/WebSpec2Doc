from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, request, send_file

from web.config import DISCOVER_TIMEOUT_SEC, OUTPUT_DIR
from web.routes.qa_process import _generate_advanced_outputs, _generate_outputs, _load_report
from web.services.auto_run_config import resolve_crawl_limits as _resolve_crawl_limits
from web.services.auto_run_job import AutoRunJob, job_output_dir
from web.services.auto_run_preview import build_autorun_preview
from web.services.document_autorun import (
    candidate_filename,
    parse_document_autorun_config,
    run_document_autorun_phase,
)
from web.services.evidence_pack_service import attach_evidence_pack
from web.services.failure_classifier import (
    classify_failure,
    classify_failures,
    summarize_classifications,
)
from web.services.playwright_executor import _read_progress_ndjson, run_playwright
from web.services.qa.helpers import use_output_dir, use_viewpoint_snapshot
from web.services.spec_ts_generator import compute_filter_counts, generate_spec_ts
from web.services.viewpoint_store import ViewpointStoreError, get_viewpoint_store
from web.tenancy import scoped_output_dir
from web.validation import (
    _clean_int,
    _domain_of,
    _safe_auth_path,
    _valid_domain,
)

bp = Blueprint("auto_run", __name__)
logger = logging.getLogger(__name__)

_JOBS: dict[str, AutoRunJob] = {}
_JOBS_LOCK = threading.Lock()


def _out() -> Path:
    """テナントスコープ済みの出力ディレクトリ（リクエスト毎に解決）。"""
    return scoped_output_dir(OUTPUT_DIR)


def _job_out(job: AutoRunJob) -> Path:
    return job_output_dir(job, OUTPUT_DIR)


# ─────────────────────────── API ───────────────────────────


@bp.post("/api/autorun/start")
def api_autorun_start() -> dict | tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    url = (request.form.get("url") or body.get("url", "")).strip()
    if not url:
        return {"error": "url is required"}, 400

    depth, max_pages = _resolve_crawl_limits(request.form, body)
    auth = _safe_auth_path((request.form.get("auth") or body.get("auth", "")).strip())
    try:
        document_config = parse_document_autorun_config(request.form, body, url)
    except ValueError as exc:
        return {"error": str(exc)}, 400
    viewpoint_set_id = (
        request.form.get("viewpoint_set_id") or body.get("viewpoint_set_id", "")
    ).strip()
    viewpoint_version_raw = request.form.get("viewpoint_version") or body.get("viewpoint_version")

    try:
        snapshot = get_viewpoint_store().select_snapshot(
            {"url": url},
            set_id=viewpoint_set_id or None,
            version_number=int(viewpoint_version_raw) if viewpoint_version_raw else None,
        )
    except (ViewpointStoreError, ValueError) as exc:
        return {
            "error": f"観点セットを固定できません: {exc}",
            "recovery": "既定公開版へ切り替えるか、観点DBを確認して再試行してください。",
        }, getattr(exc, "status_code", 409)

    job_id = uuid.uuid4().hex
    job = AutoRunJob(
        job_id=job_id,
        url=url,
        started_at=_now_iso(),
        viewpoint_set_id=snapshot["set_id"],
        viewpoint_set_name=snapshot["set_name"],
        viewpoint_version=int(snapshot["version"]),
        viewpoint_checksum=snapshot["checksum"],
        viewpoint_selection_reason=snapshot["selection_reason"],
        viewpoint_count=int(snapshot["viewpoint_count"]),
        mode=document_config.mode,
        selection_criterion=document_config.selection_criterion,
        target_page_id=document_config.target_page_id,
        observe_validation=document_config.observe_validation,
    )
    job._viewpoint_snapshot = snapshot
    job._output_dir = _out()
    job._reference_docs = document_config.reference_docs
    job.add_log(
        f"観点セットを固定: {job.viewpoint_set_name} v{job.viewpoint_version} "
        f"({job.viewpoint_count}件 / {job.viewpoint_selection_reason})"
    )
    if auth:
        job.auth_path = auth
    with _JOBS_LOCK:
        _JOBS[job_id] = job

    threading.Thread(target=_run_job, args=(job, depth, max_pages), daemon=True).start()

    return {"ok": True, "job_id": job_id}


@bp.get("/api/autorun/status")
def api_autorun_status() -> dict | tuple[dict, int]:
    with _JOBS_LOCK:
        job = _JOBS.get(request.args.get("job_id", ""))
    if job is None:
        return {"error": "not found"}, 404
    data = job.to_dict()
    if job.status == "running_tests":
        data["test_progress"] = _current_test_progress(job)
    return data


_LIVE_TESTS_LIMIT = 50  # ポーリング応答の肥大防止（負荷予算: 応答JSON<64KB。D-3でテスト固定）


def _current_test_progress(job: AutoRunJob) -> dict[str, object]:
    """実行中（running_tests）の進捗を進捗NDJSONから読む（読み取り専用・非破壊）。

    「n/188件目」のような実行中進捗表示に加え、per-test の実況（title/status/
    error）も返す（R3-01: リアルタイムOK/NG表示）。テストの完走・失敗時の
    結果集計（test_results）は run_playwright() の戻り値がそのまま正なので、
    ここでは一切書き換えない。ファイルが無い・空の間は 0/不明 として返す
    （捏造しない）。
    """
    progress_path = _job_out(job) / job.domain / "qa_process" / "playwright_progress.ndjson"
    expected_total, tests = _read_progress_ndjson(progress_path)
    recent = tests[-_LIVE_TESTS_LIMIT:]
    return {
        "completed": len(tests),
        "total": expected_total,
        "passed": sum(1 for t in tests if t.get("status") == "passed"),
        "failed": sum(1 for t in tests if t.get("status") == "failed"),
        "tests": [
            {
                "title": str(t.get("title", ""))[:200],
                "status": t.get("status", ""),
                "duration_ms": t.get("duration_ms"),
                "error": (str(t.get("error", "")) or "")[:300],
            }
            for t in reversed(recent)  # 新しい順
        ],
    }


@bp.post("/api/autorun/cancel")
def api_autorun_cancel() -> dict | tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    job_id = (request.form.get("job_id") or body.get("job_id", "")).strip()
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        return {"error": "not found"}, 404
    job.cancel()
    job.status = "cancelled"
    job.step_label = "キャンセルしました"
    job.finished_at = _now_iso()
    job.add_log("ユーザーによってキャンセルされました。")
    _record_autorun_usage_safely(job)
    return {"ok": True}


@bp.get("/api/history/runs")
def api_history_runs() -> dict:
    """種別を問わない一般化された実行履歴（R2-27）。

    usage_log.jsonl の実績と実行中（未終端）のAutoRunジョブをマージして返す。
    リンクは実在するファイルのみ（実在検証・捏造しない）。
    """
    from web.services.usage_tracker import build_run_history

    with _JOBS_LOCK:
        running_jobs = [job.to_dict() for job in _JOBS.values()]
    runs = build_run_history(_out(), running_jobs)
    _attach_stage_approval(runs)
    return {"runs": runs}


def _attach_stage_approval(runs: list[dict]) -> None:
    """各実行に段階承認の状況を添える（過去履歴画面で表示するため）。

    承認状態はドメイン単位で保存しているので、同一ドメインの実行には
    同じ状態が付く。「未承認のまま実行された」ことを隠さないのが目的。
    """
    from autorun.stages import Pipeline

    cache: dict[str, dict[str, Any] | None] = {}
    out_root = _out()

    for run in runs:
        domain = str(run.get("domain") or "")
        if not domain:
            continue
        if domain not in cache:
            path = out_root / domain / "qa_process" / "stages.json"
            summary: dict[str, Any] | None = None
            if path.is_file():
                try:
                    pipeline = Pipeline.from_dict(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                    skipped = [
                        s.definition.name for s in pipeline.stages if s.status == "skipped"
                    ]
                    summary = {
                        "approved": pipeline.approved_stage_count,
                        "total": len(pipeline.stages),
                        "all_approved": pipeline.all_approved,
                        "skipped": skipped,
                        "audit_count": len(pipeline.audit),
                    }
                except (OSError, json.JSONDecodeError, ValueError) as exc:
                    logger.warning("段階承認の状況を読めません（%s）: %s", domain, exc)
            cache[domain] = summary
        if cache[domain] is not None:
            run["stage_approval"] = cache[domain]
            run["report_url"] = f"/autorun/report/{domain}"


@bp.post("/api/autorun/submit-input")
def api_autorun_submit_input() -> dict | tuple[dict, int]:
    """ログイン情報などの人的インプットを受け取り、待機中のジョブを再開する。"""
    body = request.get_json(silent=True) or {}
    job_id = (request.form.get("job_id") or body.get("job_id", "")).strip()
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        return {"error": "not found"}, 404
    if job.status != "awaiting_input":
        return {"error": f"awaiting_input ではありません (status={job.status})"}, 400

    input_type = (request.form.get("type") or body.get("type", "")).strip()
    if input_type == "login":
        job._input_data = {
            "type": "login",
            "username": (request.form.get("username") or body.get("username", "")).strip(),
            "password": (request.form.get("password") or body.get("password", "")),
            "skip": _truthy(request.form.get("skip") or body.get("skip", "")),
        }
    elif input_type == "skip":
        job._input_data = {"type": "skip"}
    else:
        return {"error": f"unknown input type: {input_type}"}, 400

    job.input_request = None
    job.status = "crawling"
    job._input_event.set()
    return {"ok": True}


@bp.get("/api/autorun/preview")
def api_autorun_preview() -> dict | tuple[dict, int]:
    """テストケース一覧・スクリプト内容・フィルター件数を返す。"""
    with _JOBS_LOCK:
        job = _JOBS.get(request.args.get("job_id", ""))
    if job is None:
        return {"error": "not found"}, 404
    return build_autorun_preview(job, _job_out(job))


@bp.post("/api/autorun/approve")
def api_autorun_approve() -> dict | tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    job_id = (request.form.get("job_id") or body.get("job_id", "")).strip()
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if job is None:
        return {"error": "not found"}, 404
    if job.status != "awaiting_approval":
        return {"error": f"status '{job.status}' では承認できません"}, 400

    filter_mode = (request.form.get("filter_mode") or body.get("filter_mode", "all")).strip()
    if filter_mode not in ("all", "smoke", "transition", "form"):
        filter_mode = "all"
    per_test_timeout_sec = _clean_int(
        request.form.get("per_test_timeout_sec") or body.get("per_test_timeout_sec", "30"),
        30,
        5,
        120,
    )
    device = (request.form.get("device") or body.get("device", "pc")).strip()
    if device not in ("pc", "mobile"):
        device = "pc"
    page_object = _truthy(request.form.get("page_object") or body.get("page_object", False))
    job.run_policy = {
        "filter_mode": filter_mode,
        "per_test_timeout_sec": per_test_timeout_sec,
        "device": device,
        "page_object": page_object,
    }
    job.add_log(
        f"実行方針: {filter_mode} / 1テストあたり {per_test_timeout_sec}秒 / "
        f"デバイス: {'モバイル' if device == 'mobile' else 'PC'}"
    )

    job.approved = True
    threading.Thread(target=_execute_tests, args=(job,), daemon=True).start()
    return {"ok": True, "job_id": job_id}


@bp.get("/api/autorun/report")
def api_autorun_report() -> dict | tuple[dict, int]:
    with _JOBS_LOCK:
        job = _JOBS.get(request.args.get("job_id", ""))
    if job is None:
        return {"error": "not found"}, 404
    return {**job.to_dict(), "report_html": _report_html_path(job)}


@bp.get("/api/autorun/live-screenshot")
def api_autorun_live_screenshot() -> Response:
    """テスト実行中の最新スクリーンショットを返す（screenshot:'on' 設定済みの
    Playwright実行が qa_process/test-results/ 配下に生成するPNGを配信する）。
    実行中のライブプレビュー表示用。クロール側の /api/live-screenshot と同じパターン。"""
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return Response(status=404)
    results_dir = _out() / domain / "qa_process" / "test-results"
    if not results_dir.is_dir():
        return Response(status=404)
    pngs = sorted(results_dir.rglob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pngs:
        return Response(status=404)
    resp = send_file(pngs[0].resolve(), mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.get("/api/autorun/jobs")
def api_autorun_jobs() -> dict:
    with _JOBS_LOCK:
        jobs_snapshot = list(_JOBS.values())
    return {
        "jobs": [
            {
                "job_id": j.job_id,
                "url": j.url,
                "domain": j.domain,
                "status": j.status,
                "started_at": j.started_at,
                "finished_at": j.finished_at,
                "elapsed_sec": j.elapsed_sec(),
            }
            for j in reversed(jobs_snapshot)
        ][:20]
    }


# ─────────────────────────── ジョブ実行 ───────────────────────────


#: 段階承認の待機上限。人の確認を待つので長め（無期限にはしない）。
STAGE_APPROVAL_TIMEOUT_SEC = 7200


def release_stage_gate(job_id: str, domain: str) -> bool:
    """段階承認の関門を解除する。解除できたら True。

    job_id 指定があればそのジョブを、無ければ同一ドメインで承認待ちの
    ジョブを対象にする（画面をリロードして job_id を失った場合の救済）。
    """
    with _JOBS_LOCK:
        job = _JOBS.get(job_id) if job_id else None
        if job is None:
            job = next(
                (
                    candidate
                    for candidate in _JOBS.values()
                    if candidate.domain == domain and candidate.status == "awaiting_stages"
                ),
                None,
            )
        if job is None or job.status != "awaiting_stages":
            return False
        job.add_log("段階承認が完了しました。Playwright 化へ進みます。")
        job._stages_event.set()
        return True


_GATE_MESSAGES = {
    "design": (
        "テスト目的〜テストケースの承認待ち",
        "実測が揃いました。テスト目的・計画・フィーチャー・観点・設計・ケースを"
        "確認し、承認すると Playwright 化へ進みます。",
        "設計内容",
    ),
    "playwright": (
        "Playwright 自動化の承認待ち",
        "スクリプトを生成しました。承認済みケースとの対応・未自動化のケースを"
        "確認し、承認するとテストを実行します。",
        "自動化の内容",
    ),
}


def _await_stage_approval(job: AutoRunJob, gate: str) -> None:
    """段階承認（仕様7〜14）が済むまで待つ。

    実行は対象サイトへ実際に操作を行うため、人が確認・承認するまで進めない。
    タイムアウト時は「未承認のまま進めた」ことを記録し、黙って進んだように見せない。
    """
    label, message, subject = _GATE_MESSAGES[gate]

    if not job.require_stage_approval:
        # 人が承認できない文脈（自動実行など）。飛ばした事実を必ず残す。
        job.add_log(
            f"段階承認をスキップしました（自動実行）。この実行の{subject}は人の確認を経ていません。"
        )
        return

    job._stages_event.clear()
    job.status = "awaiting_stages"
    job.step_label = label
    job.add_log(message)

    approved = job._stages_event.wait(timeout=STAGE_APPROVAL_TIMEOUT_SEC)
    if job._cancelled:
        return
    if not approved:
        job.add_log(
            "承認待ちがタイムアウトしました。未承認のまま後続へ進みます"
            f"（この実行の{subject}は人の確認を経ていません）。"
        )


def _run_job(job: AutoRunJob, depth: int, max_pages: int) -> None:
    try:
        _phase_discover(job, depth, max_pages)
        if job.status in ("failed", "cancelled"):
            return

        # ログイン入力待ち（最大 30 分）
        if job.status == "awaiting_input":
            job._input_event.wait(timeout=1800)
            if job._cancelled:
                return
            if not job._input_data:
                job.add_log("入力タイムアウト。スキップしてクロールを続行します。")

            if job._input_data.get("type") == "login" and not job._input_data.get("skip"):
                _do_login(job)
                if job.status == "failed":
                    return

        _phase_crawl(job, depth, max_pages)
        if job.status in ("failed", "cancelled"):
            return
        _phase_generate_qa(job)
        if job.status in ("failed", "cancelled"):
            return
        if job.mode == "document":
            _phase_generate_document_mbt(job)
            if job.status in ("failed", "cancelled"):
                return

        # 関門1: 設計段階（1〜7）。実測が揃ったこの時点で、テスト目的から
        # テストケースまでを提示し、承認を得るまでスクリプト生成へ進まない。
        _await_stage_approval(job, "design")
        if job.status in ("failed", "cancelled"):
            return

        _phase_generate_scripts(job)
        if job.status in ("failed", "cancelled"):
            return

        # 関門2: 段階8（Playwright 自動化）。生成したスクリプトと未自動化を
        # 提示し、承認を得るまでテストを実行しない。
        _await_stage_approval(job, "playwright")
        if job.status in ("failed", "cancelled"):
            return
        job.status = "awaiting_approval"
        job.step_label = "テスト実行の承認待ち"
        job.add_log("自動生成完了。「テスト実行を承認」ボタンで Playwright を実行できます。")
    except Exception as exc:
        if job._cancelled:
            return
        _mark_job_failed(job, str(exc))
        job.add_log(f"予期しないエラー: {exc}")


def _phase_discover(job: AutoRunJob, depth: int, max_pages: int) -> None:
    """画面リスト取得 + ログイン壁検知。"""
    job.status = "discovering"
    job.step_label = "画面を分析中"
    job.add_log(f"画面分析開始: {job.url}")

    cmd = [
        sys.executable,
        "src/main.py",
        "--discover",
        "--url",
        job.url,
        "--depth",
        str(depth),
        "--max-pages",
        str(max_pages),
    ]
    if job.auth_path:
        cmd += ["--auth", job.auth_path]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=DISCOVER_TIMEOUT_SEC,
        )
        data = json.loads(proc.stdout.strip() or "{}")
        pages: list[dict[str, Any]] = data.get("pages", [])
    except subprocess.TimeoutExpired:
        job.add_log("画面分析タイムアウト。そのままクロールを続行します。")
        return
    except Exception as exc:
        job.add_log(f"画面分析エラー: {exc}。そのままクロールを続行します。")
        return

    login_pages = [p for p in pages if p.get("login_required")]
    job.step_data["discover"] = {"pages": len(pages), "login_required": len(login_pages)}
    job.add_log(f"画面分析完了: {len(pages)}件 (要ログイン: {len(login_pages)}件)")

    if login_pages:
        login_url = login_pages[0].get("login_url") or job.url
        login_fields = login_pages[0].get("login_fields", [])
        job.status = "awaiting_input"
        job.step_label = "ログイン情報の入力待ち"
        job.input_request = {
            "type": "login",
            "login_url": login_url,
            "login_fields": login_fields,
            "domain": _domain_of(job.url),
            "message": f"{len(login_pages)}件のページにログインが必要です。認証情報を入力するかスキップしてください。",
        }
        job.add_log("ログインが必要なページが検出されました。認証情報の入力を待っています。")


def _do_login(job: AutoRunJob) -> None:
    input_data = job._input_data
    login_url = (job.input_request or {}).get("login_url") or job.url
    username = input_data.get("username", "")
    password = input_data.get("password", "")
    domain = _domain_of(job.url)

    job.add_log(f"ログイン試行: {login_url}")

    auth_path = _job_out(job) / domain / "auth.json"
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    creds_json = json.dumps({"username": username, "password": password})
    cmd = [
        sys.executable,
        "src/main.py",
        "--login-simple",
        "--login-simple-url",
        login_url,
        "--auth",
        str(auth_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=creds_json,
            capture_output=True,
            text=True,
            timeout=60,
        )
        data = json.loads(proc.stdout.strip() or "{}")
        if data.get("success"):
            job.auth_path = str(auth_path.resolve())
            job.add_log(f"ログイン成功。auth.json を保存しました: {job.auth_path}")
        else:
            job.add_log(
                f"ログインに失敗しました: {data.get('error', '不明なエラー')}。スキップして続行します。"
            )
    except subprocess.TimeoutExpired:
        job.add_log("ログインタイムアウト。スキップして続行します。")
    except Exception as exc:
        job.add_log(f"ログインエラー: {exc}。スキップして続行します。")


def _phase_crawl(job: AutoRunJob, depth: int, max_pages: int) -> None:
    job.status = "crawling"
    job.step_label = "仕様書を生成中"
    job.add_log(f"クロール開始: {job.url} (depth={depth}, max={max_pages})")

    cmd = [
        sys.executable,
        "src/main.py",
        "--url",
        job.url,
        "--depth",
        str(depth),
        "--max-pages",
        str(max_pages),
        "--format",
        "json,md,html",
        "--output",
        str(_job_out(job)),
    ]
    if job.auth_path:
        cmd += ["--auth", job.auth_path]
    if job.mode == "document":
        for doc_path in job._reference_docs:
            cmd += ["--reference-doc", doc_path]

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        job._proc = proc
        for line in proc.stdout or []:
            if job._cancelled:
                proc.terminate()
                return
            line = line.rstrip()
            if line:
                # クロールCLIの生出力は開発者向け（UIでは既定非表示、トグルで表示）。
                # 生ログがそのまま表示され読みにくい、というドッグフーディング指摘への対応。
                job.add_log(f"[cli] {line}")
        proc.wait(timeout=600)
        job._proc = None
    except subprocess.TimeoutExpired:
        if proc:
            proc.kill()
        _mark_job_failed(job, "クロールタイムアウト")
        return
    except Exception as exc:
        _mark_job_failed(job, f"クロールエラー: {exc}")
        return

    if job._cancelled:
        return

    domain = _domain_of(job.url)
    job.domain = domain
    report_json = _job_out(job) / domain / "report.json"
    if not report_json.is_file():
        _mark_job_failed(job, "クロール完了後に report.json が見つかりません")
        return

    job.outputs["report_json"] = str(report_json.resolve())
    report_html = _job_out(job) / domain / "report.html"
    if report_html.is_file():
        job.outputs["report_html"] = str(report_html.resolve())
    try:
        rj = json.loads(report_json.read_text(encoding="utf-8"))
        screens = rj.get("screens", [])
        job.step_data["crawl"] = {
            "screens": len(screens),
            "forms": sum(len(s.get("forms", [])) for s in screens),
            "domain": domain,
        }
    except Exception:
        job.step_data["crawl"] = {"domain": domain}
    job.add_log(f"クロール完了: {domain}")


def _phase_generate_qa(job: AutoRunJob) -> None:
    if job._cancelled:
        return
    job.status = "generating_qa"
    job.step_label = "QA成果物を生成中"
    job.add_log("QAプロセス成果物を生成しています…")

    out_dir = _job_out(job)
    report_path = out_dir / job.domain / "report.json"
    report = _load_report(report_path)
    if report is None:
        _mark_job_failed(job, "report.json の読み込みに失敗しました")
        return

    try:
        snapshot = get_viewpoint_store().apply_snapshot_to_report(job._viewpoint_snapshot, report)
        job.viewpoint_count = int(snapshot["viewpoint_count"])
        snapshot_path = out_dir / job.domain / "qa_process" / "viewpoint_snapshot.json"
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        job.outputs["viewpoint_snapshot"] = str(snapshot_path.resolve())
        report_with_snapshot = report | {
            "viewpoint_snapshot": {key: value for key, value in snapshot.items() if key != "items"}
        }
        # スレッド内はリクエストコンテキストが無いため、出力先を明示的に固定する
        with use_output_dir(out_dir), use_viewpoint_snapshot(snapshot["items"]):
            outputs = _generate_outputs(job.domain, report_with_snapshot)
            outputs |= _generate_advanced_outputs(job.domain, report_with_snapshot)
    except (ViewpointStoreError, OSError, ValueError) as exc:
        _mark_job_failed(
            job,
            f"観点スナップショット生成エラー: {exc}。既定公開版へ切り替えるか再試行してください。",
        )
        return
    except Exception as exc:
        _mark_job_failed(job, f"QA成果物生成エラー: {exc}")
        return

    for key, path in outputs.items():
        if path.is_file():
            job.outputs[key] = str(path.resolve())
    job.step_data["qa"] = {
        "count": len(outputs),
        "viewpoint_set": job.viewpoint_set_name,
        "viewpoint_version": job.viewpoint_version,
        "viewpoint_count": job.viewpoint_count,
    }
    job.add_log(
        f"QA成果物生成完了: {len(outputs)}件 / 適用観点: "
        f"{job.viewpoint_set_name} v{job.viewpoint_version} ({job.viewpoint_count}件)"
    )


def _phase_generate_document_mbt(job: AutoRunJob) -> None:
    run_document_autorun_phase(job, _job_out(job), _mark_job_failed)


def _apply_automation_plan(job: AutoRunJob, candidates_path: Path, spec_dir: Path) -> Path:
    """承認済みテストケースで自動化対象を絞り、使用する候補ファイルのパスを返す。

    承認済みケースが無い / 突合できない場合は元の候補をそのまま使う
    （段階承認を使わない実行を壊さない）。判断はログと成果物に残す。
    """
    from autorun.automation_plan import build_plan
    from autorun.stages import Pipeline

    stages_path = spec_dir / "stages.json"
    if not stages_path.is_file():
        return candidates_path

    try:
        pipeline = Pipeline.from_dict(json.loads(stages_path.read_text(encoding="utf-8")))
        raw = json.loads(candidates_path.read_text(encoding="utf-8"))
        plan = build_plan(pipeline, list(raw.get("candidates") or []))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        job.add_log(f"自動化対象の絞り込みをスキップしました（{exc}）。全候補を使います。")
        return candidates_path

    for line in plan.summary_lines():
        job.add_log(line)

    # 対応関係を成果物として残す（未自動化のケースを追跡できるようにする）
    coverage_path = spec_dir / "automation_coverage.json"
    try:
        coverage_path.write_text(
            json.dumps(plan.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        job.outputs["automation_coverage"] = str(coverage_path.resolve())
    except OSError as exc:
        job.add_log(f"自動化カバレッジを保存できませんでした: {exc}")

    if plan.unfiltered:
        return candidates_path

    selected_path = spec_dir / "approved_candidates.json"
    try:
        selected_path.write_text(
            json.dumps({"candidates": list(plan.selected)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        job.add_log(f"絞り込んだ候補を保存できませんでした（{exc}）。全候補を使います。")
        return candidates_path
    return selected_path


def _phase_generate_scripts(job: AutoRunJob) -> None:
    if job._cancelled:
        return
    job.status = "generating_scripts"
    job.step_label = "Playwright スクリプトを生成中"
    job.add_log("Playwright .spec.ts を生成しています…")

    candidates_filename = candidate_filename(job.mode)
    candidates_path = _job_out(job) / job.domain / "qa_process" / candidates_filename
    if not candidates_path.is_file():
        _mark_job_failed(job, f"{candidates_filename} が見つかりません")
        return

    spec_dir = _job_out(job) / job.domain / "qa_process"
    spec_path = spec_dir / "autorun.spec.ts"

    # 仕様14: 承認済みのローレベルテストケースを自動化の入力にする。
    # 対応づく候補だけを対象にし、対応の無いケースは「未自動化」として残す。
    source_path = _apply_automation_plan(job, candidates_path, spec_dir)

    try:
        generate_spec_ts(job.domain, source_path, spec_path)
    except Exception as exc:
        _mark_job_failed(job, f"スクリプト生成エラー: {exc}")
        return

    try:
        raw = json.loads(candidates_path.read_text(encoding="utf-8"))
        job.step_data["scripts"] = compute_filter_counts(raw.get("candidates", []))
    except Exception:
        job.step_data["scripts"] = {}
    job.outputs["spec_ts"] = str(spec_path.resolve())
    job.add_log(f"スクリプト生成完了: {spec_path.name}")
    _publish_playwright_stage(job, spec_dir)


def _publish_playwright_stage(job: AutoRunJob, spec_dir: Path) -> None:
    """段階8（Playwright 自動化）の内容を生成して保存する。

    生成結果を人が確認できるようにするため、関門2で待つ前に用意しておく。
    """
    from autorun.stages import STAGE_PLAYWRIGHT, Observation, Pipeline, build_stage

    stages_path = spec_dir / "stages.json"
    if not stages_path.is_file():
        return
    try:
        pipeline = Pipeline.from_dict(json.loads(stages_path.read_text(encoding="utf-8")))
        coverage_path = spec_dir / "automation_coverage.json"
        automation = (
            json.loads(coverage_path.read_text(encoding="utf-8"))
            if coverage_path.is_file()
            else None
        )
        stage = build_stage(STAGE_PLAYWRIGHT, Observation(), pipeline, automation)
        pipeline = pipeline.replaced(stage).recorded(
            "generate", STAGE_PLAYWRIGHT, f"{len(stage.items)}項目を生成"
        )
        stages_path.write_text(
            json.dumps(pipeline.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        job.add_log(f"段階8の内容を用意できませんでした: {exc}")


def _execute_tests(job: AutoRunJob) -> None:
    if job._cancelled:
        return
    job.status = "running_tests"
    job.step_label = "Playwright テストを実行中"
    job.add_log("Playwright テスト実行を開始します…")

    spec_path_str = job.outputs.get("spec_ts", "")
    if not spec_path_str:
        _mark_job_failed(job, "spec.ts が見つかりません")
        return

    spec_path = Path(spec_path_str)
    report_dir = _job_out(job) / job.domain / "qa_process"

    # ポリシーに基づいてスクリプトを再生成（フィルター適用）
    filter_mode = job.run_policy.get("filter_mode", "all")
    per_test_timeout_sec = int(job.run_policy.get("per_test_timeout_sec", 30))
    device = job.run_policy.get("device", "pc")
    if device not in ("pc", "mobile"):
        device = "pc"
    # 出力形式（フラット / Page Object）。既定はフラットで後方互換。
    page_object = bool(job.run_policy.get("page_object", False))
    if filter_mode != "all" or page_object:
        candidates_path = _job_out(job) / job.domain / "qa_process" / candidate_filename(job.mode)
        if candidates_path.is_file():
            try:
                generate_spec_ts(
                    job.domain,
                    candidates_path,
                    spec_path,
                    filter_mode=filter_mode,
                    generate_page_object=page_object,
                )
                detail = f"フィルター '{filter_mode}'" + (
                    "・Page Object形式" if page_object else ""
                )
                job.add_log(f"{detail} を適用したスクリプトを再生成しました。")
            except Exception as exc:
                job.add_log(f"スクリプト再生成時エラー（元スクリプトで続行）: {exc}")

    try:
        result = run_playwright(
            spec_path,
            report_dir,
            per_test_timeout_sec=per_test_timeout_sec,
            add_log=job.add_log,
            device=device,
        )
    except Exception as exc:
        _mark_job_failed(job, f"テスト実行エラー: {exc}")
        return

    job.test_results = result
    if (report_dir / "playwright_report.json").is_file():
        job.outputs["playwright_report_json"] = str(
            (report_dir / "playwright_report.json").resolve()
        )
    # 既定は自前の日本語サマリレポート（非エンジニアにも読める・ライト基調）。
    # Playwright ネイティブ HTML レポート（英語・スクショ/トレース付き）は
    # 開発者向けの副導線として playwright_native_html に別キーで残す（R3-03/04/05）。
    ja_report = report_dir / "playwright_report.html"
    native_report = report_dir / "playwright-report" / "index.html"
    if ja_report.is_file():
        job.outputs["playwright_report_html"] = str(ja_report.resolve())
    if native_report.is_file():
        job.outputs["playwright_native_html"] = str(native_report.resolve())

    passed = result.get("passed", 0)
    failed = result.get("failed", 0)
    total = result.get("total", 0)
    result_error = result.get("error", "")
    interrupted = bool(result.get("interrupted"))

    if result_error or interrupted:
        # evidence-only: 実行が異常終了（解析失敗・タイムアウト中断・未セットアップ等）した
        # 場合に「完了」を偽装しない。0/0/0 を無言で成功扱いにしていた過去の実装が、
        # AutoRun で188件承認・実行したのに結果が全件0で表示される致命的UX破綻の原因だった。
        if interrupted and total > 0:
            job.add_log(
                f"テスト実行が中断されました（部分結果を回収）: "
                f"PASS={passed} FAIL={failed} TOTAL={total}"
            )
        else:
            job.add_log(f"テスト実行が異常終了しました: {result_error or '中断されました'}")
        _mark_job_failed(job, result_error or "テスト実行が中断されました（部分結果なし）")
        _update_failure_classification(job, result)
        # 中断でも「どこまで実行したか」は検収上の証跡になるため生成する。
        attach_evidence_pack(job, _job_out(job))
        return

    job.status = "complete"
    job.step_label = "完了"
    job.finished_at = _now_iso()
    job.add_log(f"テスト実行完了: PASS={passed} FAIL={failed} TOTAL={total}")
    _update_failure_classification(job, result)
    attach_evidence_pack(job, _job_out(job))
    _record_autorun_usage_safely(job)


# ─────────────────────────── ユーティリティ ───────────────────────────


def _update_failure_classification(
    job: AutoRunJob,
    result: dict[str, Any] | None = None,
) -> None:
    """AutoRunの失敗要因をUI表示用に分類して保存する。"""
    result = result or {}
    failures: list[dict[str, Any]] = []
    for idx, test in enumerate(result.get("tests") or [], start=1):
        if test.get("status") != "failed":
            continue
        failures.append(
            {
                "test_id": test.get("id") or test.get("title") or f"TC{idx:03d}",
                "status": "failed",
                "error": test.get("error")
                or result.get("error")
                or result.get("stderr_snippet", ""),
            }
        )

    if not failures and (result.get("error") or job.error):
        failures.append(
            {
                "test_id": "AutoRun",
                "status": "failed",
                "error": result.get("error") or job.error,
            }
        )

    if not failures:
        job.failure_classifications = []
        job.failure_summary = {}
        return

    classifications = classify_failures(failures)
    job.failure_classifications = [asdict(item) for item in classifications]
    job.failure_summary = summarize_classifications(classifications)


def _mark_job_failed(job: AutoRunJob, error: str) -> None:
    job.status = "failed"
    job.error = error
    job.finished_at = _now_iso()
    classification = classify_failure("AutoRun", error)
    job.failure_classifications = [asdict(classification)]
    job.failure_summary = summarize_classifications([classification])
    _record_autorun_usage_safely(job)


def _record_autorun_usage_safely(job: AutoRunJob) -> None:
    """実行履歴（usage_log.jsonl）へのAutoRun実績記録。記録失敗は応答を妨げない。"""
    try:
        from web.services.usage_tracker import record_autorun

        test_results = job.test_results or {}
        record_autorun(
            _job_out(job),
            job.domain,
            status=job.status,
            passed=int(test_results.get("passed", 0)),
            failed=int(test_results.get("failed", 0)),
            total=int(test_results.get("total", 0)),
            duration_sec=job.elapsed_sec(),
        )
    except Exception:  # noqa: BLE001
        logger.warning("AutoRun実績の記録に失敗しました（応答は継続）", exc_info=True)


def _report_html_path(job: AutoRunJob) -> str:
    path_str = job.outputs.get("playwright_report_html", "")
    if path_str and Path(path_str).is_file():
        return path_str
    return job.outputs.get("qa_process_report", "")


def _now_iso() -> str:
    return datetime.now().isoformat()


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
