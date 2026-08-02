"""テナントとユーザーの管理画面（管理者専用）。

管理者がテナントを作り、ユーザーを作り、どのテナントに何のロールで入れるかを
決める。ロールは所属（memberships）が持つため、同じ人がテナントごとに
一般／管理者を使い分けられる。

クロール対象サイトへのログイン（web/routes/login.py）とは無関係。
"""

from __future__ import annotations

from flask import Blueprint, g, redirect, render_template, request
from werkzeug.wrappers import Response as BaseResponse

from web.auth import (
    SYSTEM_SELECT_PATH,
    auth_enabled,
    create_user_from_payload,
    mock_auth_enabled,
    require_admin,
)
from web.services.auth_store import (
    ROLE_ADMIN,
    ROLE_LABELS,
    ROLE_MEMBER,
    AuthError,
    get_auth_store,
)

bp = Blueprint("tenant_admin", __name__)

JsonResult = tuple[dict, int] | dict


def _actor_id() -> str:
    user = getattr(g, "auth_user", None)
    return str(user.get("id", "")) if isinstance(user, dict) else ""


def _snapshot() -> dict:
    store = get_auth_store()
    return {
        "tenants": store.list_tenants(),
        "users": store.list_all_users(),
        "roles": [
            {"value": ROLE_MEMBER, "label": ROLE_LABELS[ROLE_MEMBER]},
            {"value": ROLE_ADMIN, "label": ROLE_LABELS[ROLE_ADMIN]},
        ],
        "mock_auth": mock_auth_enabled(),
    }


# --- 画面 ---------------------------------------------------------------


@bp.get("/admin/console")
def console_page() -> BaseResponse | str:
    if not auth_enabled():
        # 認証オフではテナントもユーザーも意味を持たない
        return redirect("/auth/setup")
    user = getattr(g, "auth_user", None)
    if user is None:
        return redirect("/auth/login?next=/admin/console")
    if user.get("role") != ROLE_ADMIN:
        return redirect(SYSTEM_SELECT_PATH)
    return render_template("admin/console.html", user=user, tenant=getattr(g, "tenant", None))


# --- API ----------------------------------------------------------------


@bp.before_request
def _guard() -> BaseResponse | None:
    """API は管理者のみ。画面ルートは自前でリダイレクトするので除外する。"""
    if request.endpoint == "tenant_admin.console_page":
        return None
    return require_admin()


@bp.get("/api/admin/tenancy")
def api_snapshot() -> dict:
    return _snapshot()


@bp.post("/api/admin/tenancy/tenants")
def api_create_tenant() -> JsonResult:
    payload = request.get_json(silent=True) or {}
    try:
        tenant = get_auth_store().create_tenant(
            str(payload.get("name", "")),
            str(payload.get("slug", "")),
            actor_id=_actor_id(),
        )
    except AuthError as exc:
        return {"error": str(exc), "code": exc.code}, 400
    return {"ok": True, "tenant": tenant, **_snapshot()}


@bp.patch("/api/admin/tenancy/tenants/<tenant_id>")
def api_rename_tenant(tenant_id: str) -> JsonResult:
    payload = request.get_json(silent=True) or {}
    try:
        tenant = get_auth_store().rename_tenant(
            tenant_id, str(payload.get("name", "")), actor_id=_actor_id()
        )
    except AuthError as exc:
        return {"error": str(exc), "code": exc.code}, 400
    return {"ok": True, "tenant": tenant, **_snapshot()}


@bp.delete("/api/admin/tenancy/tenants/<tenant_id>")
def api_delete_tenant(tenant_id: str) -> JsonResult:
    try:
        tenant = get_auth_store().delete_tenant(tenant_id, actor_id=_actor_id())
    except AuthError as exc:
        return {"error": str(exc), "code": exc.code}, 400
    return {
        "ok": True,
        "deleted": tenant,
        # 生成物は消していないことを画面側で伝えるための注記
        "note": f"output/tenants/{tenant['slug']} 配下のファイルは残っています。",
        **_snapshot(),
    }


@bp.post("/api/admin/tenancy/users")
def api_create_user() -> JsonResult:
    payload = request.get_json(silent=True) or {}
    tenant_id = str(payload.get("tenant_id", "")).strip() or None
    try:
        user = create_user_from_payload(payload, tenant_id=tenant_id, actor_id=_actor_id())
    except AuthError as exc:
        return {"error": str(exc), "code": exc.code}, 400
    return {"ok": True, "user": user, **_snapshot()}


@bp.put("/api/admin/tenancy/users/<user_id>/memberships")
def api_set_memberships(user_id: str) -> JsonResult:
    payload = request.get_json(silent=True) or {}
    entries = payload.get("memberships")
    if not isinstance(entries, list):
        return {"error": "memberships は配列で指定してください。", "code": "invalid_request"}, 400
    try:
        memberships = get_auth_store().set_memberships(
            user_id, [e for e in entries if isinstance(e, dict)], actor_id=_actor_id()
        )
    except AuthError as exc:
        return {"error": str(exc), "code": exc.code}, 400
    return {"ok": True, "memberships": memberships, **_snapshot()}


@bp.patch("/api/admin/tenancy/users/<user_id>")
def api_update_user(user_id: str) -> JsonResult:
    """アカウントの有効/無効化（全テナントに効く）。"""
    payload = request.get_json(silent=True) or {}
    is_active = payload.get("is_active")
    if not isinstance(is_active, bool):
        return {"error": "is_active は真偽値で指定してください。", "code": "invalid_request"}, 400
    try:
        get_auth_store().set_user_active(user_id, is_active, actor_id=_actor_id())
    except AuthError as exc:
        return {"error": str(exc), "code": exc.code}, 400
    return {"ok": True, **_snapshot()}


@bp.delete("/api/admin/tenancy/users/<user_id>")
def api_delete_user(user_id: str) -> JsonResult:
    if user_id == _actor_id():
        return {"error": "自分自身は削除できません。", "code": "self_delete"}, 400
    try:
        get_auth_store().delete_user(user_id, actor_id=_actor_id())
    except AuthError as exc:
        return {"error": str(exc), "code": exc.code}, 400
    return {"ok": True, **_snapshot()}
