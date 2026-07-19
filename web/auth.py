"""アプリ利用者認証のガードとセッションクッキー管理。

動作モード（WEBSPEC2DOC_AUTH_MODE）:
- auto（既定）: ユーザーが1人も居なければ従来どおり認証なしで利用可能
  （localhost 単独利用）。ユーザーが作成された時点からログイン必須になる。
- required: 常にログイン必須。ユーザー未作成の間は /auth/setup のみ到達可能。
- off: 認証を完全に無効化（明示的なオプトアウト）。

対象サイトへのクロール用ログイン（web/routes/login.py）とは無関係。
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from flask import Flask, Response, g, jsonify, redirect, request
from werkzeug.wrappers import Response as BaseResponse

from web.services.auth_store import get_auth_store

AUTH_MODE_ENV = "WEBSPEC2DOC_AUTH_MODE"
SECRET_KEY_ENV = "WEBSPEC2DOC_SECRET_KEY"
SECURE_COOKIES_ENV = "WEBSPEC2DOC_SECURE_COOKIES"
SESSION_COOKIE_NAME = "ws2d_session"

# 認証が有効でも到達できるパス（ログイン画面・静的ファイル・死活監視）
_EXEMPT_PREFIXES = ("/static/",)
_EXEMPT_PATHS = frozenset(
    {
        "/favicon.ico",
        "/api/v1/healthz",
        "/auth/login",
        "/auth/logout",
        "/auth/setup",
    }
)


def effective_auth_mode() -> str:
    mode = os.environ.get(AUTH_MODE_ENV, "auto").strip().lower()
    return mode if mode in ("auto", "required", "off") else "auto"


def auth_enabled() -> bool:
    """このリクエスト時点でログインを要求するかどうか。"""
    mode = effective_auth_mode()
    if mode == "off":
        return False
    if mode == "required":
        return True
    return get_auth_store().has_any_user()


def _is_exempt(path: str) -> bool:
    if path in _EXEMPT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES)


def _bearer_token() -> str:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[len("Bearer ") :].strip()
    return ""


def _wants_login_redirect() -> bool:
    """ブラウザの画面遷移ならログイン画面へリダイレクト、API呼び出しなら 401 JSON。"""
    if request.method != "GET":
        return False
    if request.path.startswith("/api"):
        return False
    # Accept ヘッダーが無い/曖昧なクライアントも画面遷移とみなしてリダイレクトする
    if not request.accept_mimetypes:
        return True
    return request.accept_mimetypes.accept_html


def safe_next_path(raw: str) -> str:
    """ログイン後リダイレクト先の検証（オープンリダイレクト防止: 相対パスのみ許可）。"""
    if raw and raw.startswith("/") and not raw.startswith("//") and "\\" not in raw:
        return raw
    return "/"


def auth_guard() -> BaseResponse | None:
    """before_request: 認証が有効なら全ルートでログイン/APIトークンを要求する。"""
    g.auth_user = None
    g.tenant = None
    if not auth_enabled():
        return None
    path = request.path
    if _is_exempt(path):
        return None

    store = get_auth_store()

    # required モードで初期セットアップ前は /auth/setup へ誘導する
    if not store.has_any_user():
        return redirect("/auth/setup")

    # /api/v1 は Bearer APIトークン（テナント単位）を第一に受け付ける
    if path.startswith("/api/v1/"):
        token = _bearer_token()
        if token:
            tenant = store.resolve_api_token(token)
            if tenant is None:
                return _unauthorized_json("APIトークンが無効です。")
            g.tenant = tenant
            g.auth_via = "api_token"
            g.token_scope = str(tenant.get("token_scope", "full"))
            if g.token_scope == "read" and request.method not in _READ_METHODS:
                return _forbidden_json(
                    "このAPIトークンは読み取り専用です。変更操作には全権トークンが必要です。"
                )
            return None

    session = store.resolve_session(request.cookies.get(SESSION_COOKIE_NAME, ""))
    if session is not None:
        g.auth_user = session["user"]
        g.tenant = session["tenant"]
        g.auth_via = "session"
        return None

    if _wants_login_redirect():
        return redirect(f"/auth/login?next={request.full_path.rstrip('?')}")
    return _unauthorized_json("ログインが必要です。")


_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _forbidden_json(message: str) -> Response:
    resp = jsonify({"error": message, "code": "forbidden_scope"})
    resp.status_code = 403
    return resp


def _unauthorized_json(message: str) -> Response:
    resp = jsonify({"error": message, "code": "unauthorized"})
    resp.status_code = 401
    return resp


def require_admin() -> BaseResponse | None:
    """管理者（owner/admin）専用エンドポイント用のチェック。認証オフ時は制限しない。"""
    if not auth_enabled():
        return None
    user = getattr(g, "auth_user", None)
    if user is None or user.get("role") not in ("owner", "admin"):
        resp = jsonify({"error": "この操作には管理者権限が必要です。", "code": "forbidden"})
        resp.status_code = 403
        return resp
    return None


# --- セッションクッキー ------------------------------------------------


def _secure_cookies() -> bool:
    if os.environ.get(SECURE_COOKIES_ENV, "").strip() == "1":
        return True
    return request.is_secure


def set_session_cookie(response: BaseResponse, token: str) -> BaseResponse:
    from web.services.auth_store import session_hours

    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=session_hours() * 3600,
        httponly=True,
        samesite="Lax",
        secure=_secure_cookies(),
        path="/",
    )
    return response


def clear_session_cookie(response: BaseResponse) -> BaseResponse:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response


# --- SECRET_KEY ---------------------------------------------------------


def ensure_secret_key(app: Flask, instance_dir: Path = Path("instance")) -> None:
    """SECRET_KEY を環境変数 → instance/secret_key の順で解決する（無ければ生成・保存）。"""
    env_key = os.environ.get(SECRET_KEY_ENV, "").strip()
    if env_key:
        app.secret_key = env_key
        return
    key_file = instance_dir / "secret_key"
    try:
        if key_file.is_file():
            stored = key_file.read_text(encoding="utf-8").strip()
            if stored:
                app.secret_key = stored
                return
        instance_dir.mkdir(parents=True, exist_ok=True)
        generated = secrets.token_hex(32)
        key_file.write_text(generated + "\n", encoding="utf-8")
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        app.secret_key = generated
    except OSError:
        # 書込不可環境（読み取り専用FS等）ではプロセス内一時キーで継続する
        app.secret_key = secrets.token_hex(32)
