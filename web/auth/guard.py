"""未認証アクセスのガード（WEBSPEC2DOC_AUTH 有効時のみ登録）。

- /auth/* とログイン API（/api/login/*：サイト認証）と static は常に許可。
- 未ログイン → /auth/login。
- ログイン済・テナント未選択 → /auth/tenants。
"""

from __future__ import annotations

from flask import Response, redirect, request, url_for

from web.auth.session import current_tenant_id, current_user_email

# 認証不要で常に通すパス接頭辞。
_PUBLIC_PREFIXES = (
    "/auth/",
    "/api/login/",  # クロール対象サイトのログインセッション取得 API
    "/static/",
)


def _is_public(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


def auth_guard() -> Response | None:
    path = request.path
    if _is_public(path):
        return None
    if current_user_email() is None:
        return redirect(url_for("auth.login_page"))
    if current_tenant_id() is None:
        return redirect(url_for("auth.tenants_page"))
    return None
