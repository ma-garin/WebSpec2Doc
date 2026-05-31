from __future__ import annotations

import subprocess
import sys

from flask import Blueprint, request

from web.config import LOGIN_FINISH_TIMEOUT_SEC, OUTPUT_DIR
from web.process import _LOGIN_PROCS, _terminate_proc
from web.validation import _valid_domain

bp = Blueprint("login", __name__)


@bp.post("/api/login/start")
def api_login_start() -> tuple[dict, int] | dict:
    """手渡しログイン用ブラウザをサブプロセスで開く（ADR-0001）。"""
    from registry.session_store import session_path, signal_path

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


@bp.post("/api/login/finish")
def api_login_finish() -> tuple[dict, int] | dict:
    """ログイン完了シグナルを置き、サブプロセスのセッション保存完了を待つ。"""
    from registry.session_store import has_session, signal_path

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
