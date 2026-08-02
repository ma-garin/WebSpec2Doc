"""アプリ利用者のログイン・初期セットアップ・アカウント管理ルート。

クロール対象サイトへのログイン（web/routes/login.py, /api/login/*）とは別機能。
こちらは WebSpec2Doc 自体のユーザー認証（/auth/*, /api/auth/*）を担う。
"""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, redirect, render_template, request
from werkzeug.wrappers import Response as BaseResponse

from web.auth import (
    SESSION_COOKIE_NAME,
    SYSTEM_SELECT_PATH,
    TENANT_SELECT_PATH,
    USER_SELECT_PATH,
    auth_enabled,
    clear_session_cookie,
    create_user_from_payload,
    effective_auth_mode,
    mock_auth_enabled,
    require_admin,
    set_session_cookie,
)
from web.services.auth_store import ROLE_ADMIN, ROLE_MEMBER, AuthError, get_auth_store

bp = Blueprint("account", __name__)

# ログイン後の遷移は常に ログイン → ユーザー選択 → テナント選択 → システム選択。
# 元のURL（next）へは戻さない。認証ガードが付ける next は "/" のことが多く、
# システム選択を飛ばしてドキュメント作成の画面へ直行してしまうため。
# 選択画面はログイン必須。個々のハンドラで判定を繰り返さず、ここで一括で弾く。
_SELECTION_ENDPOINTS = frozenset(
    {
        "account.user_page",
        "account.user_select",
        "account.tenant_page",
        "account.tenant_select",
    }
)

# 各選択画面に出すエラー。クエリ文字列の値をそのまま表示しないための対応表。
_TENANT_ERRORS = {
    "not_member": "そのテナントに所属していません。管理者に追加を依頼してください。",
    "missing": "テナントを選択してください。",
}
_USER_ERRORS = {
    "not_switchable": "そのユーザーには切り替えられません。"
    "パスワードが設定されているか、無効化されています。",
}


@bp.before_request
def _require_login_for_selection_screens() -> BaseResponse | None:
    if request.endpoint not in _SELECTION_ENDPOINTS:
        return None
    if not auth_enabled():
        return redirect("/")
    if getattr(g, "auth_user", None) is None:
        return redirect("/auth/login")
    return None


def _login_page_context(error: str | None, email: str) -> dict:
    return {"error": error, "email": email, "mock_auth": mock_auth_enabled()}


def _start_session(user: dict, target: str) -> BaseResponse:
    """ログイン成立後のセッションを発行する。テナントは未選択のまま始める。"""
    token = get_auth_store().create_session(user["id"])
    return set_session_cookie(redirect(target), token)


# --- 画面 ---------------------------------------------------------------


@bp.get("/auth/login")
def login_page() -> BaseResponse | str:
    store = get_auth_store()
    if effective_auth_mode() == "off":
        return redirect("/")
    if not store.has_any_user():
        return redirect("/auth/setup")
    if getattr(g, "auth_user", None):
        return redirect(USER_SELECT_PATH)
    return render_template("auth/login.html", **_login_page_context(None, ""))


@bp.post("/auth/login")
def login_submit() -> BaseResponse | tuple[str, int]:
    store = get_auth_store()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    try:
        # モックでもパスワードが入力されていれば通常の認証を通す。
        # 初期管理者（admin / password）のようにパスワードを持つアカウントは
        # パスワード照合を必ず経る。
        if mock_auth_enabled() and not password:
            user = store.authenticate_passwordless(email)
        else:
            user = store.authenticate(email, password)
    except AuthError as exc:
        return render_template("auth/login.html", **_login_page_context(str(exc), email)), 401
    target = USER_SELECT_PATH if mock_auth_enabled() else TENANT_SELECT_PATH
    return _start_session(user, target)


@bp.get(USER_SELECT_PATH)
def user_page() -> BaseResponse | str:
    """モックのユーザー選択。誰として作業するかをここで決める。"""
    if not mock_auth_enabled():
        return redirect(TENANT_SELECT_PATH)
    return render_template(
        "auth/user.html",
        user=g.auth_user,
        candidates=get_auth_store().list_login_candidates(),
        error=_USER_ERRORS.get(request.args.get("error", "")),
    )


@bp.post(USER_SELECT_PATH)
def user_select() -> BaseResponse:
    if not mock_auth_enabled():
        return redirect(TENANT_SELECT_PATH)
    current = g.auth_user
    user_id = request.form.get("user_id", "").strip()
    # 空、または自分自身なら切り替えずそのまま進む
    if not user_id or user_id == current.get("id"):
        return redirect(TENANT_SELECT_PATH)
    token = get_auth_store().switch_session_user(
        request.cookies.get(SESSION_COOKIE_NAME, ""), user_id
    )
    if token is None:
        return redirect(f"{USER_SELECT_PATH}?error=not_switchable")
    return set_session_cookie(redirect(TENANT_SELECT_PATH), token)


@bp.get("/auth/signup")
def signup_page() -> BaseResponse | str:
    if effective_auth_mode() == "off":
        return redirect("/")
    store = get_auth_store()
    if not store.has_any_user():
        return redirect("/auth/setup")
    if getattr(g, "auth_user", None):
        return redirect(SYSTEM_SELECT_PATH)
    return render_template("auth/signup.html", error=None, form={}, mock_auth=mock_auth_enabled())


@bp.post("/auth/signup")
def signup_submit() -> BaseResponse | tuple[str, int]:
    if effective_auth_mode() == "off":
        return redirect("/")
    store = get_auth_store()
    form = {
        "name": request.form.get("name", "").strip(),
        "email": request.form.get("email", "").strip(),
    }
    try:
        # 所属なしで作る。どのテナントに入れるかは管理者が決める。
        # モックではテンプレートがパスワード欄を出さないので、空 = パスワードなしになる。
        user = store.create_user(
            None,
            form["email"],
            form["name"],
            request.form.get("password", ""),
            role=ROLE_MEMBER,
            enforce_password_policy=not mock_auth_enabled(),
        )
    except AuthError as exc:
        html = render_template(
            "auth/signup.html", error=str(exc), form=form, mock_auth=mock_auth_enabled()
        )
        return html, 400
    # 作った本人として続けるので、ユーザー選択は挟まずテナント選択へ送る
    return _start_session(user, TENANT_SELECT_PATH)


@bp.get(TENANT_SELECT_PATH)
def tenant_page() -> BaseResponse | str:
    user = g.auth_user
    store = get_auth_store()
    return render_template(
        "auth/tenant.html",
        user=user,
        memberships=store.list_memberships(user["id"]),
        current_tenant=getattr(g, "tenant", None),
        mock_auth=mock_auth_enabled(),
        error=_TENANT_ERRORS.get(request.args.get("error", "")),
    )


@bp.post(TENANT_SELECT_PATH)
def tenant_select() -> BaseResponse:
    tenant_id = request.form.get("tenant_id", "").strip()
    if not tenant_id:
        return redirect(f"{TENANT_SELECT_PATH}?error=missing")
    token = request.cookies.get(SESSION_COOKIE_NAME, "")
    if not get_auth_store().bind_session_tenant(token, tenant_id):
        return redirect(f"{TENANT_SELECT_PATH}?error=not_member")
    return redirect(SYSTEM_SELECT_PATH)


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
    return render_template(
        "auth/setup.html", error=None, form={}, mock_auth=mock_auth_enabled()
    )


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
    mock = mock_auth_enabled()
    password = request.form.get("password", "")
    try:
        if password != request.form.get("password_confirm", ""):
            raise AuthError("確認用パスワードが一致しません。", "password_mismatch")
        result = store.setup_initial(
            form["tenant_name"] or "My Workspace",
            form["email"],
            form["name"],
            password,
            enforce_password_policy=not mock,
        )
    except AuthError as exc:
        html = render_template("auth/setup.html", error=str(exc), form=form, mock_auth=mock)
        return html, 400
    token = store.create_session(result["user"]["id"], result["tenant"]["id"])
    return set_session_cookie(redirect(SYSTEM_SELECT_PATH), token)


@bp.get("/auth/account")
def account_page() -> BaseResponse | str:
    if not auth_enabled():
        return redirect("/")
    user = getattr(g, "auth_user", None)
    if user is None:
        return redirect("/auth/login?next=/auth/account")
    store = get_auth_store()
    is_admin = user.get("role") == ROLE_ADMIN
    tenant = getattr(g, "tenant", None) or {}
    return render_template(
        "auth/account.html",
        user=user,
        tenant=tenant,
        is_admin=is_admin,
        memberships=store.list_memberships(user["id"]),
        mock_auth=mock_auth_enabled(),
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
        "mock_auth": mock_auth_enabled(),
        "user": user,
        "tenant": tenant,
        "memberships": get_auth_store().list_memberships(user["id"]) if user else [],
    }


@bp.get("/api/auth/tenants")
def api_my_tenants() -> tuple[dict, int] | dict:
    """ログイン中ユーザーの所属テナント一覧（テナント選択のデータ源）。"""
    user = getattr(g, "auth_user", None)
    if user is None:
        return {"error": "ログインが必要です。", "code": "unauthorized"}, 401
    return {
        "tenants": get_auth_store().list_memberships(user["id"]),
        "current": getattr(g, "tenant", None),
    }


def _onboarding_checklist() -> dict[str, bool]:
    from web.config import OUTPUT_DIR
    from web.tenancy import TENANTS_DIR_NAME, scoped_output_dir

    output_dir = scoped_output_dir(OUTPUT_DIR)
    domains = []
    if output_dir.is_dir():
        domains = [
            item
            for item in output_dir.iterdir()
            if item.is_dir() and not item.name.startswith(".") and item.name != TENANTS_DIR_NAME
        ]
    return {
        "site_registered": bool(domains),
        "first_crawl": any((domain / "snapshots").is_dir() for domain in domains),
        "report_available": any((domain / "report.html").is_file() for domain in domains),
    }


@bp.get("/api/onboarding")
def api_onboarding() -> dict:
    user = getattr(g, "auth_user", None)
    server_storage = auth_enabled() and user is not None
    tour_completed = bool(user.get("tour_completed_at")) if user is not None else None
    return {
        "storage": "server" if server_storage else "client",
        "tour_completed": tour_completed if server_storage else None,
        # 既存E2Eの操作を初回ツアーが遮らないよう、自動起動のみ抑止する。
        # 設定画面の「操作ツアーを再表示」はテストモードでも利用できる。
        "auto_start": not current_app.testing,
        "checklist": _onboarding_checklist(),
    }


@bp.post("/api/onboarding/complete")
def api_onboarding_complete() -> dict | tuple[dict, int]:
    user = getattr(g, "auth_user", None)
    if auth_enabled():
        if user is None:
            return {"error": "ログインが必要です。", "code": "unauthorized"}, 401
        try:
            completed = get_auth_store().complete_tour(user["id"])
        except AuthError as exc:
            return {"error": str(exc), "code": exc.code}, 400
        return {"ok": True, "storage": "server", "tour_completed": True, "user": completed}
    return {"ok": True, "storage": "client", "tour_completed": True}


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
    try:
        user = create_user_from_payload(
            request.get_json(silent=True) or {},
            tenant_id=g.tenant["id"],
            actor_id=g.auth_user["id"],
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
