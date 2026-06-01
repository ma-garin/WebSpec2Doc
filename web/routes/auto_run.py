from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Blueprint, request

from web.config import MAX_DEPTH, MAX_PAGES_LIMIT, OUTPUT_DIR
from web.routes.qa_process import _generate_advanced_outputs, _generate_outputs, _load_report
from web.services.playwright_executor import run_playwright
from web.services.spec_ts_generator import generate_spec_ts
from web.validation import _clean_int, _domain_of, _safe_auth_path, _valid_domain

bp = Blueprint("auto_run", __name__)
logger = logging.getLogger(__name__)

_JOBS: dict[str, AutoRunJob] = {}


@dataclass
class AutoRunJob:
    job_id: str
    url: str
    domain: str = ""
    status: str = "idle"
    step_label: str = ""
    log: list[str] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)
    test_results: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    started_at: str = ""
    finished_at: str = ""
    approved: bool = False

    def add_log(self, msg: str) -> None:
        self.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
        logger.info("autorun[%s] %s", self.job_id, msg)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "url": self.url,
            "domain": self.domain,
            "status": self.status,
            "step_label": self.step_label,
            "log": self.log[-100:],
            "outputs": self.outputs,
            "test_results": self.test_results,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


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
    job = AutoRunJob(job_id=job_id, url=url, started_at=datetime.now().isoformat())
    _JOBS[job_id] = job

    thread = threading.Thread(
        target=_run_job,
        args=(job, depth, max_pages, auth),
        daemon=True,
    )
    thread.start()

    return {"ok": True, "job_id": job_id}


@bp.get("/api/autorun/status")
def api_autorun_status() -> dict | tuple[dict, int]:
    job_id = request.args.get("job_id", "")
    job = _JOBS.get(job_id)
    if job is None:
        return {"error": "not found"}, 404
    return job.to_dict()


@bp.post("/api/autorun/approve")
def api_autorun_approve() -> dict | tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    job_id = (request.form.get("job_id") or body.get("job_id", "")).strip()
    job = _JOBS.get(job_id)
    if job is None:
        return {"error": "not found"}, 404
    if job.status != "awaiting_approval":
        return {"error": f"cannot approve in status '{job.status}'"}, 400

    job.approved = True
    thread = threading.Thread(target=_execute_tests, args=(job,), daemon=True)
    thread.start()
    return {"ok": True, "job_id": job_id}


@bp.get("/api/autorun/report")
def api_autorun_report() -> dict | tuple[dict, int]:
    job_id = request.args.get("job_id", "")
    job = _JOBS.get(job_id)
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
            }
            for j in reversed(list(_JOBS.values()))
        ][:20]
    }


def _run_job(job: AutoRunJob, depth: int, max_pages: int, auth: str) -> None:
    try:
        _phase_crawl(job, depth, max_pages, auth)
        if job.status == "failed":
            return
        _phase_generate_qa(job)
        if job.status == "failed":
            return
        _phase_generate_scripts(job)
        if job.status == "failed":
            return
        job.status = "awaiting_approval"
        job.step_label = "テスト実行の承認待ち"
        job.add_log("自動生成完了。「テスト実行を承認」ボタンで Playwright を実行できます。")
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.add_log(f"予期しないエラー: {exc}")
        job.finished_at = datetime.now().isoformat()


def _phase_crawl(job: AutoRunJob, depth: int, max_pages: int, auth: str) -> None:
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
    if auth:
        cmd += ["--auth", auth]

    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                job.add_log(line)
        proc.wait(timeout=600)
    except subprocess.TimeoutExpired:
        proc.kill()
        job.status = "failed"
        job.error = "クロールタイムアウト"
        job.finished_at = datetime.now().isoformat()
        return
    except Exception as exc:
        job.status = "failed"
        job.error = f"クロールエラー: {exc}"
        job.finished_at = datetime.now().isoformat()
        return

    domain = _domain_of(job.url)
    job.domain = domain
    report_json = OUTPUT_DIR / domain / "report.json"
    if not report_json.is_file():
        job.status = "failed"
        job.error = "クロール完了後に report.json が見つかりません"
        job.finished_at = datetime.now().isoformat()
        return

    job.outputs["report_json"] = str(report_json.resolve())
    report_html = OUTPUT_DIR / domain / "report.html"
    if report_html.is_file():
        job.outputs["report_html"] = str(report_html.resolve())
    job.add_log(f"クロール完了: {domain}")


def _phase_generate_qa(job: AutoRunJob) -> None:
    job.status = "generating_qa"
    job.step_label = "QA成果物を生成中"
    job.add_log("QAプロセス成果物を生成しています…")

    report_path = OUTPUT_DIR / job.domain / "report.json"
    report = _load_report(report_path)
    if report is None:
        job.status = "failed"
        job.error = "report.json の読み込みに失敗しました"
        job.finished_at = datetime.now().isoformat()
        return

    try:
        outputs = _generate_outputs(job.domain, report)
        outputs |= _generate_advanced_outputs(job.domain, report)
    except Exception as exc:
        job.status = "failed"
        job.error = f"QA成果物生成エラー: {exc}"
        job.finished_at = datetime.now().isoformat()
        return

    for key, path in outputs.items():
        if path.is_file():
            job.outputs[key] = str(path.resolve())

    job.add_log(f"QA成果物生成完了: {len(outputs)}件")


def _phase_generate_scripts(job: AutoRunJob) -> None:
    job.status = "generating_scripts"
    job.step_label = "Playwright スクリプトを生成中"
    job.add_log("Playwright .spec.ts を生成しています…")

    candidates_path = OUTPUT_DIR / job.domain / "qa_process" / "playwright_candidates.json"
    if not candidates_path.is_file():
        job.status = "failed"
        job.error = "playwright_candidates.json が見つかりません"
        job.finished_at = datetime.now().isoformat()
        return

    spec_dir = OUTPUT_DIR / job.domain / "qa_process"
    spec_path = spec_dir / "autorun.spec.ts"
    try:
        generate_spec_ts(job.domain, candidates_path, spec_path)
    except Exception as exc:
        job.status = "failed"
        job.error = f"スクリプト生成エラー: {exc}"
        job.finished_at = datetime.now().isoformat()
        return

    job.outputs["spec_ts"] = str(spec_path.resolve())
    job.add_log(f"スクリプト生成完了: {spec_path.name}")


def _execute_tests(job: AutoRunJob) -> None:
    job.status = "running_tests"
    job.step_label = "Playwright テストを実行中"
    job.add_log("Playwright テスト実行を開始します…")

    spec_path_str = job.outputs.get("spec_ts", "")
    if not spec_path_str:
        job.status = "failed"
        job.error = "spec.ts が見つかりません"
        job.finished_at = datetime.now().isoformat()
        return

    spec_path = Path(spec_path_str)
    report_dir = OUTPUT_DIR / job.domain / "qa_process"

    try:
        result = run_playwright(spec_path, report_dir)
    except Exception as exc:
        job.status = "failed"
        job.error = f"テスト実行エラー: {exc}"
        job.finished_at = datetime.now().isoformat()
        return

    job.test_results = result
    if (report_dir / "playwright_report.json").is_file():
        job.outputs["playwright_report_json"] = str((report_dir / "playwright_report.json").resolve())
    if (report_dir / "playwright_report.html").is_file():
        job.outputs["playwright_report_html"] = str((report_dir / "playwright_report.html").resolve())

    job.status = "complete"
    job.step_label = "完了"
    job.finished_at = datetime.now().isoformat()
    passed = result.get("passed", 0)
    failed = result.get("failed", 0)
    total = result.get("total", 0)
    job.add_log(f"テスト実行完了: PASS={passed} FAIL={failed} TOTAL={total}")
    if result.get("unavailable"):
        job.add_log("※ Playwright が未インストールのため実行をスキップしました。")


def _report_html_path(job: AutoRunJob) -> str:
    path_str = job.outputs.get("playwright_report_html", "")
    if path_str and Path(path_str).is_file():
        return path_str
    return job.outputs.get("qa_process_report", "")
