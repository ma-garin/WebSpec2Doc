"""Flask セッションと AuthStore のヘルパ。"""

from __future__ import annotations

from pathlib import Path

from flask import current_app, session

from web.auth.store import AuthStore

_STORE_KEY = "auth_store"
SESSION_USER = "user_email"
SESSION_TENANT = "tenant_id"


def get_store() -> AuthStore:
    """アプリ単位の AuthStore を取得（未生成なら instance/auth 配下に作成）。"""
    store = current_app.config.get(_STORE_KEY)
    if store is None:
        base = Path(current_app.instance_path) / "auth"
        store = AuthStore(base)
        current_app.config[_STORE_KEY] = store
    return store


def current_user_email() -> str | None:
    return session.get(SESSION_USER)


def current_tenant_id() -> str | None:
    return session.get(SESSION_TENANT)


def login_user(email: str) -> None:
    session[SESSION_USER] = email
    session.pop(SESSION_TENANT, None)


def select_tenant(tenant_id: str) -> None:
    session[SESSION_TENANT] = tenant_id


def logout() -> None:
    session.pop(SESSION_USER, None)
    session.pop(SESSION_TENANT, None)
