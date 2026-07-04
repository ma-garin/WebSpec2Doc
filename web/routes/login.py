from __future__ import annotations

import json
import os
import signal as signal_module
import subprocess
import sys
from typing import Any

from flask import Blueprint, request

from web.config import OUTPUT_DIR
from web.validation import _valid_domain

bp = Blueprint("login", __name__)

SCRAPE_TIMEOUT_SEC = 30
SUBMIT_TIMEOUT_SEC = 60

# 認証フローレコーダー（SPEC-3-2）の出力ファイル名。ドット始まり = report 出力と混同しない
LOGIN_SIGNAL_FILE_NAME = ".login_signal"
LOGIN_STATUS_FILE_NAME = ".login_status.json"
DEFAULT_RECORD_STATUS = {
    "phase": "waiting",
    "current_url": "",
    "detail": "",
    "verified": None,
}


@bp.post("/api/login/simple")
def api_login_simple() -> tuple[dict, int] | dict:
    """IDとパスワードをtype属性ベースで自動マッピングしてログインする（シンプルフロー）。
    認証情報はstdin経由でサブプロセスに渡し、コマンドライン引数・ログに残さない。"""
    domain = request.form.get("domain", "").strip()
    login_url = request.form.get("login_url", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not domain or not _valid_domain(domain) or not login_url:
        return {"success": False, "error": "ドメインとログインURLを指定してください"}, 400

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
            timeout=SUBMIT_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "ログイン処理がタイムアウトしました"}, 504
    try:
        data = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError:
        return {"success": False, "error": "ログイン結果の解析に失敗しました"}, 500

    if data.get("success"):
        data["auth_path"] = str(auth_path.resolve())
    return data


@bp.post("/api/login/scrape")
def api_login_scrape() -> tuple[dict, int] | dict:
    """ログインページのフォームフィールドを動的スクレイプする（ADR-0002）。"""
    url = request.form.get("url", "").strip()
    domain = request.form.get("domain", "").strip()
    if not url or not domain or not _valid_domain(domain):
        return {"ok": False, "error": "URLとドメインを指定してください"}, 400
    cmd = [sys.executable, "src/main.py", "--login-scrape", url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=SCRAPE_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "フォーム取得がタイムアウトしました"}, 504
    try:
        data = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": "フォーム取得結果の解析に失敗しました"}, 500
    return data


@bp.post("/api/login/submit")
def api_login_submit() -> tuple[dict, int] | dict:
    """ログインフォームを自動送信してセッションを保存する（ADR-0002）。
    フィールド値（パスワードを含む）はサブプロセスのstdin経由で渡し、ログに残さない。"""
    domain = request.form.get("domain", "").strip()
    current_url = request.form.get("current_url", "").strip()
    fields_json = request.form.get("fields_json", "{}").strip()

    if not domain or not _valid_domain(domain) or not current_url:
        return {"success": False, "error": "ドメインとURLを指定してください"}, 400
    try:
        json.loads(fields_json)
    except json.JSONDecodeError:
        return {"success": False, "error": "フィールドデータが不正です"}, 400

    auth_path = OUTPUT_DIR / domain / "auth.json"
    temp_path = OUTPUT_DIR / domain / ".login_temp.json"
    auth_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "src/main.py",
        "--login-submit",
        "--login-current-url",
        current_url,
        "--auth",
        str(auth_path),
        "--login-temp-session",
        str(temp_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=fields_json,
            capture_output=True,
            text=True,
            timeout=SUBMIT_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "ログイン処理がタイムアウトしました"}, 504
    try:
        data = json.loads(proc.stdout.strip() or "{}")
    except json.JSONDecodeError:
        return {"success": False, "error": "ログイン結果の解析に失敗しました"}, 500

    if data.get("success"):
        data["auth_path"] = str(auth_path.resolve())
    return data


# ---------- 認証フローレコーダー（SPEC-3-2） ----------
# 「見えるブラウザで人が普通にログインし、ボタン一つで保存する」フロー。
# start は非ブロッキング（subprocess.Popen）で起動し、PID を返す。
# 進行状態は status_file（JSON）経由で共有する（Flask ワーカー間でメモリ共有しないため）。


@bp.post("/api/login/record/start")
def api_login_record_start() -> tuple[dict, int] | dict:
    """認証フローレコーダーを起動する。ブラウザは非ブロッキングで起動し、
    完了は /api/login/record/status のポーリングで検知する。"""
    domain = request.form.get("domain", "").strip()
    login_url = request.form.get("login_url", "").strip()
    if not domain or not _valid_domain(domain) or not login_url:
        return {"success": False, "error": "ドメインとログインURLを指定してください"}, 400

    domain_dir = OUTPUT_DIR / domain
    domain_dir.mkdir(parents=True, exist_ok=True)
    auth_path = domain_dir / "auth.json"
    signal_path = domain_dir / LOGIN_SIGNAL_FILE_NAME
    status_path = domain_dir / LOGIN_STATUS_FILE_NAME
    # 前回セッションの残骸（シグナル・状態ファイル）を持ち越さない
    for stale in (signal_path, status_path):
        try:
            stale.unlink(missing_ok=True)
        except OSError:
            pass

    cmd = [
        sys.executable,
        "src/main.py",
        "--login-record",
        "--login-record-url",
        login_url,
        "--auth",
        str(auth_path),
        "--login-signal",
        str(signal_path),
        "--login-status",
        str(status_path),
    ]
    try:
        proc = subprocess.Popen(cmd)
    except OSError as exc:
        return {"success": False, "error": f"レコーダーの起動に失敗しました: {exc}"}, 500
    return {"success": True, "pid": proc.pid, "status_path": str(status_path)}


@bp.get("/api/login/record/status")
def api_login_record_status() -> tuple[dict, int] | dict:
    """レコーダーの進行状態をポーリングする（1秒間隔想定）。"""
    domain = request.args.get("domain", "").strip()
    if not domain or not _valid_domain(domain):
        return {"success": False, "error": "ドメインを指定してください"}, 400

    status_path = OUTPUT_DIR / domain / LOGIN_STATUS_FILE_NAME
    data: dict[str, Any]
    if not status_path.exists():
        data = dict(DEFAULT_RECORD_STATUS)
    else:
        try:
            data = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # 書き込み途中で読んだ場合など。次回ポーリングに任せ、未確認として扱う
            data = dict(DEFAULT_RECORD_STATUS)

    data["success"] = True
    if data.get("phase") == "saved":
        auth_path = OUTPUT_DIR / domain / "auth.json"
        if auth_path.exists():
            data["auth_path"] = str(auth_path.resolve())
    return data


@bp.post("/api/login/record/complete")
def api_login_record_complete() -> tuple[dict, int] | dict:
    """「ログイン完了」ボタン。シグナルファイルを作成し、レコーダーに保存を指示する。"""
    domain = request.form.get("domain", "").strip()
    if not domain or not _valid_domain(domain):
        return {"success": False, "error": "ドメインを指定してください"}, 400
    signal_path = OUTPUT_DIR / domain / LOGIN_SIGNAL_FILE_NAME
    signal_path.parent.mkdir(parents=True, exist_ok=True)
    signal_path.touch()
    return {"success": True}


@bp.post("/api/login/record/cancel")
def api_login_record_cancel() -> tuple[dict, int] | dict:
    """保存前にレコーダーを中断する（PID を直接 terminate。状態はファイルで共有するため
    起動ワーカーと異なるワーカーが受けても対応できる）。"""
    pid_text = request.form.get("pid", "").strip()
    if not pid_text or not pid_text.isdigit():
        return {"success": False, "error": "pidを指定してください"}, 400
    try:
        os.kill(int(pid_text), signal_module.SIGTERM)
    except ProcessLookupError:
        pass  # 既に終了済み
    except OSError as exc:
        return {"success": False, "error": f"中断に失敗しました: {exc}"}, 500
    return {"success": True}
