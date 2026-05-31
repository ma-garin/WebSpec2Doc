from __future__ import annotations

import json
import subprocess
import sys
import threading
import uuid
import webbrowser
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, make_response, redirect, request, send_file, url_for
from web.config import (
    _PREVIEW_MIME,
    DEFAULT_OPENAI_MODEL,
    DISCOVER_TIMEOUT_SEC,
    LOGIN_FINISH_TIMEOUT_SEC,
    MAX_DEPTH,
    MAX_PAGES_LIMIT,
    OUTPUT_DIR,
    PORT,
)
from web.env_store import _mask_key, _read_env, _write_env
from web.process import _LOGIN_PROCS, _RUNNING_PROCS, _terminate_proc
from web.security import csrf_guard
from web.summary import _fmt_snap_ts, _summary_for_domain
from web.validation import (
    _clean_formats,
    _clean_int,
    _domain_of,
    _safe_auth_path,
    _safe_output_path,
    _sanitize,
    _valid_domain,
)

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from registry.session_store import (  # noqa: E402
    has_session,
    session_path,
    signal_path,
)
from registry.site_registry import SiteConfig, load_site, save_site  # noqa: E402

app = Flask(__name__)
app.before_request(csrf_guard)

from web.routes import pages  # noqa: E402

app.register_blueprint(pages.bp)


@app.post("/api/discover")
def api_discover() -> Response | tuple[dict, int] | dict:
    url = request.form.get("url", "").strip()
    depth = str(_clean_int(request.form.get("depth", "2"), 2, 1, MAX_DEPTH))
    max_pages = str(_clean_int(request.form.get("max_pages", "30"), 30, 1, MAX_PAGES_LIMIT))
    auth = _safe_auth_path(request.form.get("auth", "").strip())
    if not url:
        return {"pages": [], "error": "URLを入力してください"}, 400
    cmd = [
        sys.executable,
        "src/main.py",
        "--discover",
        "--url",
        url,
        "--depth",
        depth,
        "--max-pages",
        max_pages,
    ]
    if auth:
        cmd += ["--auth", auth]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=DISCOVER_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return {"pages": [], "error": "画面リスト取得がタイムアウトしました"}, 504
    try:
        data = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError:
        return {"pages": [], "error": "画面リストの解析に失敗しました"}, 500
    return {"pages": data.get("pages", [])}


def _save_site_config(
    domain: str,
    urls: str,
    crawl_mode: str,
    depth: str,
    max_pages: str,
    formats: list[str],
    auth: str,
) -> None:
    """クロール成功時に再クロール用の設定を site.json へ保存する。"""
    try:
        save_site(
            SiteConfig(
                domain=domain,
                urls=tuple(u for u in urls.split(",") if u),
                crawl_mode=crawl_mode,
                depth=int(depth),
                max_pages=int(max_pages),
                formats=tuple(formats),
                auth_path=auth,
            ),
            OUTPUT_DIR,
        )
    except (OSError, ValueError) as exc:
        app.logger.warning("site.json の保存に失敗しました: %s (%s)", domain, exc)


@app.get("/api/site")
def api_site() -> dict:
    domain = request.args.get("domain", "").strip()
    if not domain or not _valid_domain(domain):
        return {"site": None}
    config = load_site(domain, OUTPUT_DIR)
    return {"site": asdict(config) if config else None}


@app.post("/api/login/start")
def api_login_start() -> tuple[dict, int] | dict:
    """手渡しログイン用ブラウザをサブプロセスで開く（ADR-0001）。"""
    login_url = request.form.get("url", "").strip()
    domain = request.form.get("domain", "").strip()
    if not login_url or not domain or not _valid_domain(domain):
        return {"ok": False, "error": "ログインURLとドメインを指定してください"}, 400
    sig = signal_path(domain, OUTPUT_DIR)
    auth = session_path(domain, OUTPUT_DIR)
    auth.parent.mkdir(parents=True, exist_ok=True)
    if sig.exists():
        sig.unlink()  # 前回の取り残しシグナルを掃除
    cmd = [
        sys.executable,
        "src/main.py",
        "--login",
        login_url,
        "--login-signal",
        str(sig),
        "--auth",
        str(auth),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    _LOGIN_PROCS[domain] = proc
    return {"ok": True, "domain": domain}


@app.post("/api/login/finish")
def api_login_finish() -> tuple[dict, int] | dict:
    """ログイン完了シグナルを置き、サブプロセスのセッション保存完了を待つ。"""
    domain = request.form.get("domain", "").strip()
    if not domain or not _valid_domain(domain):
        return {"ok": False, "error": "ドメインを指定してください"}, 400
    proc = _LOGIN_PROCS.pop(domain, None)
    if proc is None:
        return {"ok": False, "error": "ログインセッションが開始されていません"}, 409
    signal_path(domain, OUTPUT_DIR).write_text("", encoding="utf-8")
    try:
        proc.wait(timeout=LOGIN_FINISH_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        _terminate_proc(proc)
        return {"ok": False, "error": "セッション保存がタイムアウトしました"}, 504
    saved = proc.returncode == 0 and has_session(domain, OUTPUT_DIR)
    return {"ok": saved, "session_saved": saved}


@app.post("/run")
def run() -> Response:
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
                _save_site_config(domain, urls, crawl_mode, depth, max_pages, selected, auth)
            if proc.returncode != 0:
                yield "\nエラーが発生しました。\n"
        finally:
            _RUNNING_PROCS.pop(run_id, None)
            _terminate_proc(proc)

    return Response(generate(), mimetype="text/plain")


@app.post("/api/cancel")
def api_cancel() -> dict:
    proc = _RUNNING_PROCS.get(request.form.get("run_id", ""))
    if proc is None:
        return {"ok": False}
    _terminate_proc(proc)
    return {"ok": True}


@app.get("/api/live-screenshot")
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


@app.get("/preview")
def preview() -> Response:
    target = _safe_output_path(request.args.get("path", ""))
    if target is None:
        return Response(status=404)
    mime = _PREVIEW_MIME.get(target.suffix.lower(), "text/plain; charset=utf-8")
    resp = send_file(target, mimetype=mime)
    resp.headers["Content-Disposition"] = "inline"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/download")
def download() -> Response:
    target = _safe_output_path(request.args.get("path", ""))
    if target is None:
        return Response(status=404)
    return send_file(target, as_attachment=True, download_name=target.name)


@app.get("/download-zip")
def download_zip() -> Response:
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return Response(status=404)
    base = (OUTPUT_DIR / domain).resolve()
    if OUTPUT_DIR.resolve() not in base.parents or not base.is_dir():
        return Response(status=404)
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in base.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(base.parent))
    buf.seek(0)
    return send_file(
        buf, as_attachment=True, download_name=f"{domain}.zip", mimetype="application/zip"
    )


@app.get("/api/result")
def api_result() -> dict | tuple[dict, int]:
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    domain_dir = OUTPUT_DIR / domain
    if not domain_dir.is_dir():
        return {"error": "not found"}, 404

    def path_of(name: str) -> str:
        f = domain_dir / name
        return str(f.resolve()) if f.exists() else ""

    shots_dir = domain_dir / "screenshots"
    shots = sorted(shots_dir.glob("*.png")) if shots_dir.is_dir() else []
    return {
        "summary": _summary_for_domain(domain),
        "files": {
            "html": path_of("report.html"),
            "pdf": path_of("report.pdf"),
            "json": path_of("report.json"),
            "excel": path_of("spec.xlsx"),
            "screens_md": path_of("screens.md"),
            "forms_md": path_of("forms.md"),
            "transition_mmd": path_of("transition.mmd"),
            "diff": path_of("diff_report.html"),
        },
        "screenshots": [str(s.resolve()) for s in shots],
    }


@app.get("/api/snapshots")
def api_snapshots() -> dict | tuple[dict, int]:
    """サイトのクロール履歴（スナップショット）一覧。新しい順。"""
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    snaps_dir = OUTPUT_DIR / domain / "snapshots"
    items: list[dict] = []
    if snaps_dir.is_dir():
        for f in sorted(snaps_dir.glob("*.json"), reverse=True):
            try:
                pages = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            forms = sum(len(p.get("forms", [])) for p in pages)
            fields = sum(len(fm.get("fields", [])) for p in pages for fm in p.get("forms", []))
            items.append(
                {
                    "id": f.stem,
                    "label": _fmt_snap_ts(f.stem),
                    "screens": len(pages),
                    "forms": forms,
                    "fields": fields,
                }
            )
    return {"snapshots": items}


@app.get("/api/snapshot-diff")
def api_snapshot_diff() -> Response:
    """2つのスナップショット間の仕様ドリフト差分をHTMLで返す。"""
    domain = request.args.get("domain", "")
    if not _valid_domain(domain):
        return Response(status=404)
    snaps_dir = OUTPUT_DIR / domain / "snapshots"
    from_path = _safe_output_path(str(snaps_dir / (request.args.get("from", "") + ".json")))
    to_path = _safe_output_path(str(snaps_dir / (request.args.get("to", "") + ".json")))
    if from_path is None or to_path is None:
        return Response(
            "<p style='font-family:sans-serif;padding:16px'>指定されたスナップショットが見つかりません。</p>",
            mimetype="text/html",
        )
    if str(Path("src").resolve()) not in sys.path:
        sys.path.insert(0, str(Path("src").resolve()))
    try:
        from diff.differ import compute_diff
        from diff.snapshot import load_snapshot
        from generator.diff_reporter import generate_diff_report
    except ImportError:
        return Response(status=500)
    old_pages = load_snapshot(from_path)
    new_pages = load_snapshot(to_path)
    diff = compute_diff(old_pages, new_pages)
    report_html = generate_diff_report(
        diff=diff,
        old_label=_fmt_snap_ts(from_path.stem),
        new_label=_fmt_snap_ts(to_path.stem),
        target_url=f"https://{domain}/",
    )
    resp = Response(report_html, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/history")
def api_history() -> dict:
    items: list[dict] = []
    if OUTPUT_DIR.is_dir():
        domains = [d for d in OUTPUT_DIR.iterdir() if d.is_dir()]
        for d in sorted(domains, key=lambda p: p.stat().st_mtime, reverse=True):
            summary = _summary_for_domain(d.name)
            formats = [
                name
                for name, fname in (
                    ("HTML", "report.html"),
                    ("PDF", "report.pdf"),
                    ("Excel", "spec.xlsx"),
                    ("JSON", "report.json"),
                    ("MD", "screens.md"),
                    ("差分", "diff_report.html"),
                )
                if (d / fname).exists()
            ]
            items.append(
                {
                    "domain": d.name,
                    "screens": summary.get("screens", 0),
                    "fields": summary.get("fields", 0),
                    "updated": datetime.fromtimestamp(d.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "formats": formats,
                }
            )
    return {"items": items}


@app.get("/api/settings")
def get_settings() -> dict:
    env = _read_env()
    key = env.get("OPENAI_API_KEY", "")
    return {
        "openai_key_set": bool(key),
        "openai_key_masked": _mask_key(key),
        "openai_model": env.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
        "openai_org_id": env.get("OPENAI_ORG_ID", ""),
        "openai_project_id": env.get("OPENAI_PROJECT_ID", ""),
    }


@app.post("/api/settings")
def post_settings() -> dict:
    updates: dict[str, str] = {}
    api_key = _sanitize(request.form.get("api_key", ""))
    if api_key:
        updates["OPENAI_API_KEY"] = api_key
    if "model" in request.form:
        updates["OPENAI_MODEL"] = _sanitize(request.form.get("model", "")) or DEFAULT_OPENAI_MODEL
    if "org_id" in request.form:
        updates["OPENAI_ORG_ID"] = _sanitize(request.form.get("org_id", ""))
    if "project_id" in request.form:
        updates["OPENAI_PROJECT_ID"] = _sanitize(request.form.get("project_id", ""))
    if updates:
        _write_env(updates)
    return {"ok": True, "openai_key_set": bool(_read_env().get("OPENAI_API_KEY"))}


@app.get("/open")
def open_file() -> Response:
    target = _safe_output_path(request.args.get("path", ""))
    if target is not None:
        subprocess.Popen(["open", str(target)])
    return make_response(redirect(url_for("index")))


def _open_browser() -> None:
    import time

    time.sleep(1.0)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


if __name__ == "__main__":
    threading.Thread(target=_open_browser, daemon=True).start()
    app.run(host="127.0.0.1", port=PORT, debug=False)
