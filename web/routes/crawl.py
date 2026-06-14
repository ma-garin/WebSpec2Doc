from __future__ import annotations

import json
import subprocess
import sys
import uuid

from flask import Blueprint, Response, request, send_file

from web.config import MAX_DEPTH, MAX_PAGES_LIMIT, OUTPUT_DIR
from web.process import _RUNNING_PROCS, _terminate_proc
from web.summary import _summary_for_domain
from web.validation import _clean_formats, _clean_int, _domain_of, _safe_auth_path, _valid_domain

bp = Blueprint("crawl", __name__)


@bp.post("/run")
def run() -> Response:
    from web.routes.site import save_site_config

    urls = request.form.get("urls", "").strip()
    depth = str(_clean_int(request.form.get("depth", "2"), 2, 1, MAX_DEPTH))
    max_pages = str(_clean_int(request.form.get("max_pages", "30"), 30, 1, MAX_PAGES_LIMIT))
    # 出力形式は許可リストで検証。report.json は結果ページのデータ源なので常に生成する
    selected = _clean_formats(request.form.get("format", "md,html")) or ["md", "html"]
    if "json" not in selected:
        selected.append("json")
    fmt = ",".join(selected)
    compare = request.form.get("compare", "false") == "true"
    auth = _safe_auth_path(request.form.get("auth", "").strip())
    crawl_mode = request.form.get("crawl_mode", "").strip()
    domain = _domain_of(urls.split(",")[0]) if urls else ""

    run_id = uuid.uuid4().hex

    def generate():
        cmd = [
            sys.executable,
            "src/main.py",
            "--urls",
            urls,
            "--depth",
            depth,
            "--max-pages",
            max_pages,
            "--parallelism",
            "2",
            "--format",
            fmt,
        ]
        if compare:
            cmd.append("--compare")
        if auth:
            cmd += ["--auth", auth]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        _RUNNING_PROCS[run_id] = proc
        try:
            yield f"RUN_ID:{run_id}\n"
            yield from proc.stdout
            proc.wait()
            if proc.returncode is not None and proc.returncode < 0:
                yield "\n停止しました。\n"
                return
            domain_dir = OUTPUT_DIR / domain
            report = domain_dir / "report.html"
            pdf = domain_dir / "report.pdf"
            if report.exists():
                yield f"REPORT_PATH:{report.resolve()}\n"
            if pdf.exists():
                yield f"PDF_PATH:{pdf.resolve()}\n"
            yield f"SUMMARY:{json.dumps(_summary_for_domain(domain))}\n"
            if proc.returncode == 0 and domain:
                save_site_config(domain, urls, crawl_mode, depth, max_pages, selected, auth)
            if proc.returncode != 0:
                yield "\nエラーが発生しました。\n"
        finally:
            _RUNNING_PROCS.pop(run_id, None)
            _terminate_proc(proc)

    return Response(generate(), mimetype="text/plain")


@bp.post("/api/cancel")
def api_cancel() -> dict:
    proc = _RUNNING_PROCS.get(request.form.get("run_id", ""))
    if proc is None:
        return {"ok": False}
    _terminate_proc(proc)
    return {"ok": True}


@bp.get("/api/live-screenshot")
def live_screenshot() -> Response:
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return Response(status=404)
    shots_dir = OUTPUT_DIR / domain / "screenshots"
    if not shots_dir.is_dir():
        return Response(status=404)
    pngs = sorted(shots_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pngs:
        return Response(status=404)
    resp = send_file(pngs[0].resolve(), mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp
