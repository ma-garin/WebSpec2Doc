from __future__ import annotations

import json
import logging
import subprocess  # noqa: F401  互換維持: テストが auto_run.subprocess.Popen を差し替えるため
import threading
import uuid
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, request, send_file

from web.config import OUTPUT_DIR
from web.services.auto_run_config import resolve_crawl_limits as _resolve_crawl_limits
from web.services.auto_run_job import AutoRunJob, _job_out, logger
from web.services.auto_run_pipeline import (
    _GATE_MESSAGES,
    _execute_tests,
    _now_iso,
    _record_autorun_usage_safely,
    _report_html_path,
    _run_job,
    _truthy,
)
from web.services.auto_run_pipeline import (
    _await_stage_approval as _await_stage_approval,  # noqa: F401
)
from web.services.auto_run_pipeline import _do_login as _do_login  # noqa: F401
from web.services.auto_run_pipeline import (
    _ensure_stage_content as _ensure_stage_content,  # noqa: F401
)
from web.services.auto_run_pipeline import _mark_job_failed as _mark_job_failed  # noqa: F401
from web.services.auto_run_pipeline import _phase_crawl as _phase_crawl  # noqa: F401
from web.services.auto_run_pipeline import _phase_discover as _phase_discover  # noqa: F401
from web.services.auto_run_pipeline import (  # noqa: F401
    _phase_generate_document_mbt as _phase_generate_document_mbt,
)
from web.services.auto_run_pipeline import _phase_generate_qa as _phase_generate_qa  # noqa: F401
from web.services.auto_run_pipeline import (  # noqa: F401
    _phase_generate_scripts as _phase_generate_scripts,
)
from web.services.auto_run_pipeline import (  # noqa: F401
    _publish_playwright_stage as _publish_playwright_stage,
)
from web.services.auto_run_pipeline import _run_child_process as _run_child_process  # noqa: F401
from web.services.auto_run_pipeline import (  # noqa: F401
    _run_mutation_self_check as _run_mutation_self_check,
)
from web.services.auto_run_preview import build_autorun_preview
from web.services.document_autorun import parse_document_autorun_config
from web.services.playwright_executor import _read_progress_ndjson
from web.services.viewpoint_store import ViewpointStoreError, get_viewpoint_store
from web.tenancy import scoped_output_dir
from web.validation import (
    _clean_int,
    _safe_auth_path,
    _valid_domain,
)

bp = Blueprint("auto_run", __name__)

_JOBS: dict[str, AutoRunJob] = {}
_JOBS_LOCK = threading.Lock()


def _out() -> Path:
    """テナントスコープ済みの出力ディレクトリ（リクエスト毎に解決）。"""
    return scoped_output_dir(OUTPUT_DIR)


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
    """AutoRun の実行に段階承認の状況を添える（実行履歴で表示するため）。

    承認状態はドメイン単位でしか保存されていないため、同一ドメインの実行には
    同じ値が付く。実際の承認時点とは一致しないので、その旨を ``scope`` で明示する
    （「この実行時点の承認状態」だと誤読させない）。

    段階承認は AutoRun にしか無い概念なので、crawl / 現新比較 / UX レビュー /
    スケジュールの行には付けない。以前は種別を見ずに全行へ付けており、
    ドキュメント作成の 24 行中 22 行が AutoRun のレポートへ飛んでいた。
    """
    from autorun.stages import Pipeline

    cache: dict[str, dict[str, Any] | None] = {}
    out_root = _out()

    for run in runs:
        if str(run.get("type") or "") != "autorun":
            continue
        domain = str(run.get("domain") or "")
        if not domain:
            continue
        if domain not in cache:
            path = out_root / domain / "qa_process" / "stages.json"
            summary: dict[str, Any] | None = None
            if path.is_file():
                try:
                    pipeline = Pipeline.from_dict(json.loads(path.read_text(encoding="utf-8")))
                    skipped = [s.definition.name for s in pipeline.stages if s.status == "skipped"]
                    summary = {
                        "approved": pipeline.approved_stage_count,
                        "total": len(pipeline.stages),
                        "all_approved": pipeline.all_approved,
                        "skipped": skipped,
                        "audit_count": len(pipeline.audit),
                        # 実行ごとではなくドメイン単位の値であることを画面へ伝える。
                        # 黙って出すと、過去の実行に現在の承認状態が付いて見える。
                        "scope": "domain",
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


def current_awaiting_stage(job_id: str, domain: str) -> str:
    """いま承認待ちの段階IDを返す（無ければ空文字）。

    仕様7〜14では各段階が独立した承認点なので、「どの段階を承認すれば
    先へ進むのか」を API 側が知る必要がある。
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
            return ""
        return job.awaiting_stage_id


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
        # 1段階ずつ進むため、どの段階の承認で解除されたのかを記録する。
        gate = job.awaiting_stage_id
        label = _GATE_MESSAGES.get(gate, ("", "", "この段階"))[2]
        job.add_log(f"{label}を承認しました。次の段階へ進みます。")
        job._stages_event.set()
        return True


def release_all_stage_gates(
    job_id: str,
    domain: str,
    decisions: dict[str, Any] | None = None,
    note: str = "",
    unverified: list[str] | None = None,
) -> bool:
    """実行条件の確定により、以降すべての段階の関門を解除する。

    段階ごとに承認させるのをやめたため、ここで一度に解除する。
    いま待機中の関門も同時に解除し、後続の段階では止まらないようにする。
    """
    with _JOBS_LOCK:
        job = _JOBS.get(job_id) if job_id else None
        if job is None:
            job = next(
                (
                    candidate
                    for candidate in _JOBS.values()
                    if candidate.domain == domain
                    and candidate.status in ("awaiting_stages", "generating_qa")
                ),
                None,
            )
        if job is None:
            return False
        job.stages_all_released = True
        job.decisions = dict(decisions or {})
        job.decisions_note = note

        # 記録して終わらせない。選んだ内容を実行の挙動へ反映する。
        _apply_decisions_to_policy(job)

        job.add_log("実行条件を確定しました。以降の段階は承認済みとして進みます。")
        # 人が見ていない項目は「確認済み」に数えない。成果物へ持ち越す。
        for item in unverified or []:
            job.add_unverified(f"人の確認を経ずに実行へ進みました — {item}")
        # 待機中なら起こす。待機していなければフラグだけが効く。
        job._stages_event.set()
        return True


def _apply_decisions_to_policy(job: AutoRunJob) -> None:
    """確定した実行条件を run_policy へ反映し、選んだ結果をログに残す。

    以前は選択内容を保存するだけで挙動が変わらなかった。「送信まで実行」を
    選んでも送信されないのは、選ばせている意味がない。
    """
    answers = job.decisions or {}

    side_effect = (answers.get("side_effect") or {}).get("choice", "observe_only")
    allow_submit = side_effect == "submit"
    job.run_policy["allow_submit"] = allow_submit
    job.add_log(
        "フォーム送信: 実行します（対象サイトに実データが登録されます）"
        if allow_submit
        else "フォーム送信: 行いません（入力の観測にとどめます）"
    )

    auth_scope = (answers.get("auth_scope") or {}).get("choice", "public_only")
    job.run_policy["auth_scope"] = auth_scope
    if auth_scope == "authenticated":
        job.add_log("認証範囲: ログイン後の画面も対象にします（認証情報が必要です）")
        # 選択を記録するだけでは、ログイン後の画面を対象にできない。
        # 認証情報が未登録なら、その場で登録を求めて止める。
        auth_path = _job_out(job) / job.domain / "auth.json" if job.domain else None
        if auth_path is None or not auth_path.is_file():
            job.status = "awaiting_input"
            job.step_label = "認証情報の登録待ち"
            job.input_request = {
                "type": "login",
                "login_url": job.url,
                "login_fields": [],
                "domain": job.domain,
                "message": (
                    "ログイン後の画面もテストする条件を選びました。"
                    "認証情報を登録してください。登録せずに進むと未ログインの範囲のみになります。"
                ),
            }
            job.add_log("認証情報が未登録です。登録するまでログイン後の画面は対象になりません。")
    else:
        job.add_log("認証範囲: 未ログインで到達できる範囲のみを対象にします")

    exit_criteria = answers.get("exit_criteria") or {}
    if exit_criteria.get("choice") == "custom" and exit_criteria.get("text"):
        job.run_policy["exit_criteria"] = exit_criteria["text"]
        job.add_log(f"合否基準: {exit_criteria['text']}")
    else:
        job.run_policy["exit_criteria"] = "severity"
        job.add_log("合否基準: 重大度で整理し、最終判断は人が行います")

    browser = answers.get("browser") or {}
    requested = browser.get("text", "") if browser.get("choice") == "custom" else ""
    job.run_policy["browser_request"] = requested
    if requested:
        from web.services.playwright_executor import ensure_browser_available, normalize_browser

        resolved = normalize_browser(requested)
        if not resolved:
            # 判別できないものを黙って Chromium へ読み替えない。
            job.run_policy["browser"] = "chromium"
            job.add_log(
                f"ブラウザ指定「{requested}」を判別できませんでした。Chromium で実行します"
                "（指定した環境での確認にはなっていません）"
            )
        else:
            ok, reason = ensure_browser_available(resolved)
            if ok:
                job.run_policy["browser"] = resolved
                job.add_log(f"ブラウザ: {resolved} で実行します")
            else:
                job.run_policy["browser"] = "chromium"
                job.add_log(
                    f"{resolved} を使えないため Chromium で実行します（{reason}）。"
                    "この実行は指定した環境での確認になっていません"
                )
    else:
        job.run_policy["browser"] = "chromium"

    if job.decisions_note:
        job.run_policy["note"] = job.decisions_note
        job.add_log(f"追加の指示: {job.decisions_note}")

    _annotate_docs_with_conditions(job)


def _annotate_docs_with_conditions(job: AutoRunJob) -> None:
    """生成済みのテスト文書へ、実際の実行条件を追記する。

    テスト設計・ケースは条件確定より前に生成されるため、本文には
    「フォーム送信を確認」と書かれたまま残る。実際には送信しない設定で
    実行されることがあり、文書と実施内容が食い違う。
    再生成はせず、実際の条件を明記して食い違いを解消する。
    """
    if not job.domain:
        return
    allow_submit = bool(job.run_policy.get("allow_submit"))
    note = [
        "",
        "## 実行条件（この実行で確定した内容）",
        "",
        "- フォーム送信: "
        + (
            "実行します（対象サイトに実データが登録されます）"
            if allow_submit
            else "**行いません**。送信を伴う設計項目は、入力の観測までを実施範囲とします"
        ),
        "- 認証範囲: "
        + (
            "ログイン後の画面を含みます"
            if job.run_policy.get("auth_scope") == "authenticated"
            else "未ログインで到達できる範囲のみです"
        ),
        f"- 合否基準: {job.run_policy.get('exit_criteria', 'severity')}",
        "",
    ]
    qa_dir = _job_out(job) / job.domain / "qa_process"
    for name in ("test_design.md", "test_cases.md"):
        path = qa_dir / name
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8")
            if "## 実行条件（この実行で確定した内容）" in body:
                continue
            path.write_text(body.rstrip("\n") + "\n" + "\n".join(note), encoding="utf-8")
        except OSError as exc:
            logging.warning("実行条件を %s へ追記できませんでした: %s", name, exc)
