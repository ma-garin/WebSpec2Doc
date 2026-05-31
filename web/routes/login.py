from __future__ import annotations

import json
import subprocess
import sys

from flask import Blueprint, request

from web.config import OUTPUT_DIR
from web.validation import _valid_domain

bp = Blueprint("login", __name__)

SCRAPE_TIMEOUT_SEC = 30
SUBMIT_TIMEOUT_SEC = 60


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
        sys.executable, "src/main.py",
        "--login-simple",
        "--login-simple-url", login_url,
        "--auth", str(auth_path),
    ]
    try:
        proc = subprocess.run(
            cmd, input=creds_json,
            capture_output=True, text=True,
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
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=SCRAPE_TIMEOUT_SEC
        )
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
        sys.executable, "src/main.py",
        "--login-submit",
        "--login-current-url", current_url,
        "--auth", str(auth_path),
        "--login-temp-session", str(temp_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=fields_json,
            capture_output=True, text=True,
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
