"""アプリ利用者の認証ルート（メール自己申告 ＋ テナント選択）。

既存 web.routes.login（/api/login/*：サイト認証）とは別物。混同を避けるため
利用者認証は auth ブループリント（/auth/*）に置く。
設計: docs/design/auth-tenant-integration.md
"""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, url_for

from web.auth import DEFAULT_TENANT_NAME
from web.auth.session import (
    current_user_email,
    get_store,
    login_user,
    logout,
    select_tenant,
)
from web.auth.store import is_valid_email, normalize_email

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.get("/login")
def login_page() -> str:
    return render_template("auth/login.html", error=None, email="")


@bp.post("/login")
def login_submit():
    raw = request.form.get("email", "")
    if not is_valid_email(raw):
        return (
            render_template(
                "auth/login.html",
                error="有効なメールアドレスを入力してください。",
                email=raw,
            ),
            400,
        )
    email = normalize_email(raw)
    store = get_store()
    store.upsert_login(email)
    # 初回は既定テナントを自動作成して owner を付与する。
    store.ensure_default_tenant(email, DEFAULT_TENANT_NAME)
    login_user(email)
    return redirect(url_for("auth.tenants_page"))


@bp.get("/tenants")
def tenants_page():
    email = current_user_email()
    if email is None:
        return redirect(url_for("auth.login_page"))
    store = get_store()
    pairs = store.tenants_for(email)
    tenants = [
        {"id": tenant.id, "name": tenant.name, "role": membership.role}
        for tenant, membership in pairs
    ]
    return render_template("auth/tenants.html", email=email, tenants=tenants)


@bp.post("/tenants/select")
def tenants_select():
    email = current_user_email()
    if email is None:
        return redirect(url_for("auth.login_page"))
    tenant_id = request.form.get("tenant_id", "").strip()
    store = get_store()
    if not tenant_id or not store.has_membership(email, tenant_id):
        return redirect(url_for("auth.tenants_page"))
    select_tenant(tenant_id)
    return redirect(url_for("pages.index"))


@bp.post("/logout")
def logout_action():
    logout()
    return redirect(url_for("auth.login_page"))
