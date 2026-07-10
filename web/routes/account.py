"""アプリ利用者のログイン・初期セットアップ・アカウント管理ルート。

クロール対象サイトへのログイン（web/routes/login.py, /api/login/*）とは別機能。
こちらは WebSpec2Doc 自体のユーザー認証（/auth/*, /api/auth/*）を担う。
"""

from __future__ import annotations

import json

from flask import Blueprint, g, jsonify, redirect, render_template, request
from werkzeug.wrappers import Response as BaseResponse

from web.auth import (
    auth_enabled,
    clear_session_cookie,
    effective_auth_mode,
    require_admin,
    safe_next_path,
    set_session_cookie,
)
from web.services.auth_store import AuthError, get_auth_store

bp = Blueprint("account", __name__)


# --- 画面 ---------------------------------------------------------------


@bp.get("/auth/login")
def login_page() -> BaseResponse | str:
    store = get_auth_store()
    if effective_auth_mode() == "off":
        return redirect("/")
    if not store.has_any_user():
        return redirect("/auth/setup")
    if getattr(g, "auth_user", None):
        return redirect(safe_next_path(request.args.get("next", "/")))
    return render_template(
        "auth/login.html",
        error=None,
        email="",
        next_path=safe_next_path(request.args.get("next", "/")),
    )


@bp.post("/auth/login")
def login_submit() -> BaseResponse | tuple[str, int]:
    store = get_auth_store()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    next_path = safe_next_path(request.form.get("next", "/"))
    try:
        user = store.authenticate(email, password)
    except AuthError as exc:
        html = render_template("auth/login.html", error=str(exc), email=email, next_path=next_path)
        return html, 401
    token = store.create_session(user["id"])
    return set_session_cookie(redirect(next_path), token)


@bp.post("/auth/logout")
def logout() -> BaseResponse:
    store = get_auth_store()
    from web.auth import SESSION_COOKIE_NAME

    store.revoke_session(request.cookies.get(SESSION_COOKIE_NAME, ""))
    return clear_session_cookie(redirect("/auth/login"))


@bp.get("/auth/setup")
def setup_page() -> BaseResponse | str:
    store = get_auth_store()
    if effective_auth_mode() == "off":
        return redirect("/")
    if store.has_any_user():
        return redirect("/auth/login")
    return render_template("auth/setup.html", error=None, form={})


@bp.post("/auth/setup")
def setup_submit() -> BaseResponse | tuple[str, int]:
    store = get_auth_store()
    if effective_auth_mode() == "off":
        return redirect("/")
    form = {
        "tenant_name": request.form.get("tenant_name", "").strip(),
        "name": request.form.get("name", "").strip(),
        "email": request.form.get("email", "").strip(),
    }
    password = request.form.get("password", "")
    confirm = request.form.get("password_confirm", "")
    try:
        if password != confirm:
            raise AuthError("確認用パスワードが一致しません。", "password_mismatch")
        result = store.setup_initial(
            form["tenant_name"] or "My Workspace",
            form["email"],
            form["name"],
            password,
        )
    except AuthError as exc:
        html = render_template("auth/setup.html", error=str(exc), form=form)
        return html, 400
    token = store.create_session(result["user"]["id"])
    return set_session_cookie(redirect("/"), token)


@bp.get("/auth/account")
def account_page() -> BaseResponse | str:
    if not auth_enabled():
        return redirect("/")
    user = getattr(g, "auth_user", None)
    if user is None:
        return redirect("/auth/login?next=/auth/account")
    store = get_auth_store()
    is_admin = user.get("role") in ("owner", "admin")
    tenant = getattr(g, "tenant", None) or {}
    from web.config import OUTPUT_DIR
    from web.services.governance import usage_snapshot
    from web.tenancy import scoped_output_dir

    return render_template(
        "auth/account.html",
        user=user,
        tenant=tenant,
        is_admin=is_admin,
        usage=usage_snapshot(tenant or None, scoped_output_dir(OUTPUT_DIR)),
        users=store.list_users(tenant.get("id", "")) if is_admin else [],
        api_tokens=store.list_api_tokens(tenant.get("id", "")) if is_admin else [],
    )


# --- API ----------------------------------------------------------------


@bp.get("/api/auth/me")
def api_me() -> dict:
    user = getattr(g, "auth_user", None)
    tenant = getattr(g, "tenant", None)
    return {
        "auth_enabled": auth_enabled(),
        "mode": effective_auth_mode(),
        "user": user,
        "tenant": tenant,
    }


def _require_login_json() -> tuple[BaseResponse, bool]:
    """認証必須APIの共通前提チェック（認証オフ時は 400 で明示的に断る）。"""
    if not auth_enabled():
        resp = jsonify(
            {"error": "認証が無効のためこの操作は使用できません。", "code": "auth_disabled"}
        )
        resp.status_code = 400
        return resp, False
    if getattr(g, "auth_user", None) is None:
        resp = jsonify({"error": "ログインが必要です。", "code": "unauthorized"})
        resp.status_code = 401
        return resp, False
    return jsonify({}), True


@bp.get("/api/auth/usage")
def api_auth_usage() -> BaseResponse | dict:
    """現在のテナントの使用量と実効上限（レート・月次クォータ・同時実行）。"""
    resp, ok = _require_login_json()
    if not ok:
        return resp
    from web.config import OUTPUT_DIR
    from web.services.governance import usage_snapshot
    from web.tenancy import scoped_output_dir

    return usage_snapshot(getattr(g, "tenant", None), scoped_output_dir(OUTPUT_DIR))


@bp.patch("/api/auth/tenant")
def api_update_tenant() -> BaseResponse | tuple[dict, int] | dict:
    """テナントのプラン・個別上限の変更（オーナー専用）。"""
    resp, ok = _require_login_json()
    if not ok:
        return resp
    if g.auth_user.get("role") != "owner":
        return {"error": "プラン変更はオーナーのみ可能です。", "code": "forbidden"}, 403
    payload = request.get_json(silent=True) or {}
    plan = payload.get("plan")
    limits = payload.get("limits")
    try:
        tenant = get_auth_store().update_tenant_plan(
            g.tenant["id"],
            plan=str(plan) if plan is not None else None,
            limits_json=(
                None
                if limits is None
                else limits if isinstance(limits, str) else json.dumps(limits)
            ),
            actor_id=g.auth_user["id"],
        )
    except AuthError as exc:
        return {"error": str(exc), "code": exc.code}, 400
    return {"ok": True, "tenant": tenant}


@bp.post("/api/auth/password")
def api_change_password() -> BaseResponse | tuple[dict, int] | dict:
    resp, ok = _require_login_json()
    if not ok:
        return resp
    payload = request.get_json(silent=True) or {}
    try:
        get_auth_store().change_password(
            g.auth_user["id"],
            str(payload.get("current", "")),
            str(payload.get("new", "")),
        )
    except AuthError as exc:
        return {"error": str(exc), "code": exc.code}, 400
    # 変更後は全セッション失効するため再ログインを促す
    return {"ok": True, "relogin": True}


@bp.get("/api/auth/users")
def api_list_users() -> BaseResponse | dict:
    resp, ok = _require_login_json()
    if not ok:
        return resp
    denied = require_admin()
    if denied is not None:
        return denied
    return {"users": get_auth_store().list_users(g.tenant["id"])}


@bp.post("/api/auth/users")
def api_create_user() -> BaseResponse | tuple[dict, int] | dict:
    resp, ok = _require_login_json()
    if not ok:
        return resp
    denied = require_admin()
    if denied is not None:
        return denied
    payload = request.get_json(silent=True) or {}
    role = str(payload.get("role", "member"))
    if role == "owner" and g.auth_user.get("role") != "owner":
        return {"error": "オーナーの追加はオーナーのみ可能です。", "code": "forbidden"}, 403
    try:
        user = get_auth_store().create_user(
            g.tenant["id"],
            str(payload.get("email", "")),
            str(payload.get("name", "")),
            str(payload.get("password", "")),
            role=role,
        )
    except AuthError as exc:
        return {"error": str(exc), "code": exc.code}, 400
    return {"ok": True, "user": user}


@bp.patch("/api/auth/users/<user_id>")
def api_update_user(user_id: str) -> BaseResponse | tuple[dict, int] | dict:
    resp, ok = _require_login_json()
    if not ok:
        return resp
    denied = require_admin()
    if denied is not None:
        return denied
    payload = request.get_json(silent=True) or {}
    role = payload.get("role")
    is_active = payload.get("is_active")
    if role == "owner" and g.auth_user.get("role") != "owner":
        return {"error": "オーナーへの昇格はオーナーのみ可能です。", "code": "forbidden"}, 403
    try:
        user = get_auth_store().update_user(
            user_id,
            g.tenant["id"],
            role=str(role) if role is not None else None,
            is_active=bool(is_active) if is_active is not None else None,
            actor_id=g.auth_user["id"],
        )
    except AuthError as exc:
        return {"error": str(exc), "code": exc.code}, 400
    return {"ok": True, "user": user}


@bp.get("/api/auth/api-tokens")
def api_list_tokens() -> BaseResponse | dict:
    resp, ok = _require_login_json()
    if not ok:
        return resp
    denied = require_admin()
    if denied is not None:
        return denied
    return {"tokens": get_auth_store().list_api_tokens(g.tenant["id"])}


@bp.post("/api/auth/api-tokens")
def api_create_token() -> BaseResponse | tuple[dict, int] | dict:
    resp, ok = _require_login_json()
    if not ok:
        return resp
    denied = require_admin()
    if denied is not None:
        return denied
    payload = request.get_json(silent=True) or {}
    try:
        token = get_auth_store().create_api_token(
            g.tenant["id"], str(payload.get("name", "")), created_by=g.auth_user["id"]
        )
    except AuthError as exc:
        return {"error": str(exc), "code": exc.code}, 400
    return {"ok": True, "token": token}


@bp.delete("/api/auth/api-tokens/<token_id>")
def api_revoke_token(token_id: str) -> BaseResponse | tuple[dict, int] | dict:
    resp, ok = _require_login_json()
    if not ok:
        return resp
    denied = require_admin()
    if denied is not None:
        return denied
    changed = get_auth_store().revoke_api_token(
        token_id, g.tenant["id"], actor_id=g.auth_user["id"]
    )
    if not changed:
        return {"error": "トークンが見つかりません。", "code": "not_found"}, 404
    return {"ok": True}
