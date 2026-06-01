from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Blueprint, request

from web.config import DISCOVER_TIMEOUT_SEC, MAX_DEPTH, MAX_PAGES_LIMIT, OUTPUT_DIR
from web.routes.qa_process import _generate_advanced_outputs, _generate_outputs, _load_report
from web.services.playwright_executor import run_playwright
from web.services.spec_ts_generator import compute_filter_counts, generate_spec_ts
from web.validation import _clean_int, _domain_of, _safe_auth_path

bp = Blueprint("auto_run", __name__)
logger = logging.getLogger(__name__)

_JOBS: dict[str, AutoRunJob] = {}


@dataclass
class AutoRunJob:
    job_id: str
    url: str
    domain: str = ""
    status: str = "idle"
    # idle | discovering | awaiting_input | crawling | generating_qa
    # generating_scripts | awaiting_approval | running_tests | complete
    # cancelled | failed
    step_label: str = ""
    log: list[str] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)
    test_results: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    started_at: str = ""
    finished_at: str = ""
    approved: bool = False
    auth_path: str = ""
    input_request: dict[str, Any] | None = None
    run_policy: dict[str, Any] = field(default_factory=dict)

    # 非シリアライズフィールド（dataclass外で設定）
    _proc: Any = field(default=None, init=False, repr=False, compare=False)
    _input_event: Any = field(
        default_factory=threading.Event, init=False, repr=False, compare=False
    )
    _input_data: dict[str, Any] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )
    _cancelled: bool = field(default=False, init=False, repr=False, compare=False)

    def add_log(self, msg: str) -> None:
        self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        logger.info("autorun[%s] %s", self.job_id, msg)

    def elapsed_sec(self) -> int:
        if not self.started_at:
            return 0
        try:
            start = datetime.fromisoformat(self.started_at)
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            end_str = self.finished_at
            if end_str:
                end = datetime.fromisoformat(end_str)
                if end.tzinfo is None:
                    end = end.replace(tzinfo=timezone.utc)
            else:
                end = datetime.now(timezone.utc)
            return max(0, int((end - start).total_seconds()))
        except Exception:
            return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "url": self.url,
            "domain": self.domain,
            "status": self.status,
            "step_label": self.step_label,
            "log": self.log[-200:],
            "outputs": self.outputs,
            "test_results": self.test_results,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_sec": self.elapsed_sec(),
            "input_request": self.input_request,
            "run_policy": self.run_policy,
        }

    def cancel(self) -> None:
        self._cancelled = True
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        # 入力待ちで止まっていたら解除
        self._input_event.set()


# ─────────────────────────── API ───────────────────────────

@bp.post("/api/autorun/start")
def api_autorun_start() -> dict | tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    url = (request.form.get("url") or body.get("url", "")).strip()
    if not url:
        return {"error": "url is required"}, 400

    depth = _clean_int(request.form.get("depth") or body.get("depth", "2"), 2, 1, MAX_DEPTH)
    max_pages = _clean_int(
        request.form.get("max_pages") or body.get("max_pages", "30"), 30, 1, MAX_PAGES_LIMIT
    )
    auth = _safe_auth_path((request.form.get("auth") or body.get("auth", "")).strip())

    job_id = uuid.uuid4().hex
    job = AutoRunJob(job_id=job_id, url=url, started_at=_now_iso())
    if auth:
        job.auth_path = auth
    _JOBS[job_id] = job

    threading.Thread(
        target=_run_job, args=(job, depth, max_pages), daemon=True
    ).start()

    return {"ok": True, "job_id": job_id}


@bp.get("/api/autorun/status")
def api_autorun_status() -> dict | tuple[dict, int]:
    job = _JOBS.get(request.args.get("job_id", ""))
    if job is None:
        return {"error": "not found"}, 404
    return job.to_dict()


@bp.post("/api/autorun/cancel")
def api_autorun_cancel() -> dict | tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    job_id = (request.form.get("job_id") or body.get("job_id", "")).strip()
    job = _JOBS.get(job_id)
    if job is None:
        return {"error": "not found"}, 404
    job.cancel()
    job.status = "cancelled"
    job.step_label = "キャンセルしました"
    job.finished_at = _now_iso()
    job.add_log("ユーザーによってキャンセルされました。")
    return {"ok": True}


@bp.post("/api/autorun/submit-input")
def api_autorun_submit_input() -> dict | tuple[dict, int]:
    """ログイン情報などの人的インプットを受け取り、待機中のジョブを再開する。"""
    body = request.get_json(silent=True) or {}
    job_id = (request.form.get("job_id") or body.get("job_id", "")).strip()
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
    job = _JOBS.get(request.args.get("job_id", ""))
    if job is None:
        return {"error": "not found"}, 404

    candidates_path = OUTPUT_DIR / job.domain / "qa_process" / "playwright_candidates.json"
    spec_path_str = job.outputs.get("spec_ts", "")

    result: dict[str, Any] = {"job_id": job.job_id}

    # 候補一覧
    if candidates_path.is_file():
        try:
            data = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates: list[dict[str, Any]] = data.get("candidates", [])
            by_status: dict[str, int] = {}
            by_title: dict[str, int] = {}
            for c in candidates:
                s = c.get("automation_status", "")
                t = c.get("title", "")
                by_status[s] = by_status.get(s, 0) + 1
                by_title[t] = by_title.get(t, 0) + 1
            result["candidates"] = candidates
            result["summary"] = {
                "total": len(candidates),
                "by_status": by_status,
                "by_title": by_title,
                "filter_counts": compute_filter_counts(candidates),
            }
        except Exception as exc:
            result["candidates"] = []
            result["summary"] = {"error": str(exc)}
    else:
        result["candidates"] = []
        result["summary"] = {}

    # スクリプト内容
    if spec_path_str and Path(spec_path_str).is_file():
        try:
            result["spec_content"] = Path(spec_path_str).read_text(encoding="utf-8")
        except Exception:
            result["spec_content"] = ""
    else:
        result["spec_content"] = ""

    return result


@bp.post("/api/autorun/approve")
def api_autorun_approve() -> dict | tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    job_id = (request.form.get("job_id") or body.get("job_id", "")).strip()
    job = _JOBS.get(job_id)
    if job is None:
        return {"error": "not found"}, 404
    if job.status != "awaiting_approval":
        return {"error": f"status '{job.status}' では承認できません"}, 400

    filter_mode = (request.form.get("filter_mode") or body.get("filter_mode", "all")).strip()
    if filter_mode not in ("all", "smoke", "transition", "form"):
        filter_mode = "all"
    timeout_sec = _clean_int(
        request.form.get("timeout_sec") or body.get("timeout_sec", "60"), 60, 10, 600
    )
    job.run_policy = {"filter_mode": filter_mode, "timeout_sec": timeout_sec}
    job.add_log(f"実行方針: {filter_mode} / タイムアウト {timeout_sec}秒")

    job.approved = True
    threading.Thread(target=_execute_tests, args=(job,), daemon=True).start()
    return {"ok": True, "job_id": job_id}


@bp.get("/api/autorun/report")
def api_autorun_report() -> dict | tuple[dict, int]:
    job = _JOBS.get(request.args.get("job_id", ""))
    if job is None:
        return {"error": "not found"}, 404
    return {**job.to_dict(), "report_html": _report_html_path(job)}


@bp.get("/api/autorun/jobs")
def api_autorun_jobs() -> dict:
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
            for j in reversed(list(_JOBS.values()))
        ][:20]
    }


# ─────────────────────────── ジョブ実行 ───────────────────────────

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
        _phase_generate_scripts(job)
        if job.status in ("failed", "cancelled"):
            return
        job.status = "awaiting_approval"
        job.step_label = "テスト実行の承認待ち"
        job.add_log("自動生成完了。「テスト実行を承認」ボタンで Playwright を実行できます。")
    except Exception as exc:
        if job._cancelled:
            return
        job.status = "failed"
        job.error = str(exc)
        job.add_log(f"予期しないエラー: {exc}")
        job.finished_at = _now_iso()


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

    auth_path = OUTPUT_DIR / domain / "auth.json"
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
    ]
    if job.auth_path:
        cmd += ["--auth", job.auth_path]

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        job._proc = proc
        for line in proc.stdout:
            if job._cancelled:
                proc.terminate()
                return
            line = line.rstrip()
            if line:
                job.add_log(line)
        proc.wait(timeout=600)
        job._proc = None
    except subprocess.TimeoutExpired:
        if proc:
            proc.kill()
        job.status = "failed"
        job.error = "クロールタイムアウト"
        job.finished_at = _now_iso()
        return
    except Exception as exc:
        job.status = "failed"
        job.error = f"クロールエラー: {exc}"
        job.finished_at = _now_iso()
        return

    if job._cancelled:
        return

    domain = _domain_of(job.url)
    job.domain = domain
    report_json = OUTPUT_DIR / domain / "report.json"
    if not report_json.is_file():
        job.status = "failed"
        job.error = "クロール完了後に report.json が見つかりません"
        job.finished_at = _now_iso()
        return

    job.outputs["report_json"] = str(report_json.resolve())
    report_html = OUTPUT_DIR / domain / "report.html"
    if report_html.is_file():
        job.outputs["report_html"] = str(report_html.resolve())
    job.add_log(f"クロール完了: {domain}")


def _phase_generate_qa(job: AutoRunJob) -> None:
    if job._cancelled:
        return
    job.status = "generating_qa"
    job.step_label = "QA成果物を生成中"
    job.add_log("QAプロセス成果物を生成しています…")

    report_path = OUTPUT_DIR / job.domain / "report.json"
    report = _load_report(report_path)
    if report is None:
        job.status = "failed"
        job.error = "report.json の読み込みに失敗しました"
        job.finished_at = _now_iso()
        return

    try:
        outputs = _generate_outputs(job.domain, report)
        outputs |= _generate_advanced_outputs(job.domain, report)
    except Exception as exc:
        job.status = "failed"
        job.error = f"QA成果物生成エラー: {exc}"
        job.finished_at = _now_iso()
        return

    for key, path in outputs.items():
        if path.is_file():
            job.outputs[key] = str(path.resolve())
    job.add_log(f"QA成果物生成完了: {len(outputs)}件")


def _phase_generate_scripts(job: AutoRunJob) -> None:
    if job._cancelled:
        return
    job.status = "generating_scripts"
    job.step_label = "Playwright スクリプトを生成中"
    job.add_log("Playwright .spec.ts を生成しています…")

    candidates_path = OUTPUT_DIR / job.domain / "qa_process" / "playwright_candidates.json"
    if not candidates_path.is_file():
        job.status = "failed"
        job.error = "playwright_candidates.json が見つかりません"
        job.finished_at = _now_iso()
        return

    spec_dir = OUTPUT_DIR / job.domain / "qa_process"
    spec_path = spec_dir / "autorun.spec.ts"
    try:
        generate_spec_ts(job.domain, candidates_path, spec_path)
    except Exception as exc:
        job.status = "failed"
        job.error = f"スクリプト生成エラー: {exc}"
        job.finished_at = _now_iso()
        return

    job.outputs["spec_ts"] = str(spec_path.resolve())
    job.add_log(f"スクリプト生成完了: {spec_path.name}")


def _execute_tests(job: AutoRunJob) -> None:
    if job._cancelled:
        return
    job.status = "running_tests"
    job.step_label = "Playwright テストを実行中"
    job.add_log("Playwright テスト実行を開始します…")

    spec_path_str = job.outputs.get("spec_ts", "")
    if not spec_path_str:
        job.status = "failed"
        job.error = "spec.ts が見つかりません"
        job.finished_at = _now_iso()
        return

    spec_path = Path(spec_path_str)
    report_dir = OUTPUT_DIR / job.domain / "qa_process"

    # ポリシーに基づいてスクリプトを再生成（フィルター適用）
    filter_mode = job.run_policy.get("filter_mode", "all")
    timeout_sec = int(job.run_policy.get("timeout_sec", 60))
    if filter_mode != "all":
        candidates_path = OUTPUT_DIR / job.domain / "qa_process" / "playwright_candidates.json"
        if candidates_path.is_file():
            try:
                generate_spec_ts(job.domain, candidates_path, spec_path, filter_mode=filter_mode)
                job.add_log(f"フィルター '{filter_mode}' を適用したスクリプトを再生成しました。")
            except Exception as exc:
                job.add_log(f"フィルター適用時エラー（元スクリプトで続行）: {exc}")

    try:
        result = run_playwright(spec_path, report_dir, timeout_sec=timeout_sec, add_log=job.add_log)
    except Exception as exc:
        job.status = "failed"
        job.error = f"テスト実行エラー: {exc}"
        job.finished_at = _now_iso()
        return

    job.test_results = result
    if (report_dir / "playwright_report.json").is_file():
        job.outputs["playwright_report_json"] = str(
            (report_dir / "playwright_report.json").resolve()
        )
    if (report_dir / "playwright_report.html").is_file():
        job.outputs["playwright_report_html"] = str(
            (report_dir / "playwright_report.html").resolve()
        )

    job.status = "complete"
    job.step_label = "完了"
    job.finished_at = _now_iso()
    passed = result.get("passed", 0)
    failed = result.get("failed", 0)
    total = result.get("total", 0)
    job.add_log(f"テスト実行完了: PASS={passed} FAIL={failed} TOTAL={total}")
    if result.get("unavailable"):
        job.add_log("※ @playwright/test 未セットアップのため実行をスキップしました。")


# ─────────────────────────── ユーティリティ ───────────────────────────

def _report_html_path(job: AutoRunJob) -> str:
    path_str = job.outputs.get("playwright_report_html", "")
    if path_str and Path(path_str).is_file():
        return path_str
    return job.outputs.get("qa_process_report", "")


def _now_iso() -> str:
    return datetime.now().isoformat()


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}
