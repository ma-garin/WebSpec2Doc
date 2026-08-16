"""アプリ利用者のログイン・初期セットアップ・アカウント管理ルート。

クロール対象サイトへのログイン（web/routes/login.py, /api/login/*）とは別機能。
こちらは WebSpec2Doc 自体のユーザー認証（/auth/*, /api/auth/*）を担う。
"""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, redirect, render_template, request
from werkzeug.wrappers import Response as BaseResponse

from web.auth import (
    ACCOUNT_VIEW_PATH,
    SESSION_COOKIE_NAME,
    SYSTEM_SELECT_PATH,
    TENANT_SELECT_PATH,
    auth_enabled,
    clear_session_cookie,
    create_user_from_payload,
    effective_auth_mode,
    mock_auth_enabled,
    require_admin,
    set_session_cookie,
)
from web.services.auth_store import ROLE_MEMBER, AuthError, get_auth_store

bp = Blueprint("account", __name__)

# ログイン後の遷移は常に ログイン → テナント選択 → システム選択。
# 元のURL（next）へは戻さない。認証ガードが付ける next は "/" のことが多く、
# システム選択を飛ばしてドキュメント作成の画面へ直行してしまうため。
# 選択画面はログイン必須。個々のハンドラで判定を繰り返さず、ここで一括で弾く。
_SELECTION_ENDPOINTS = frozenset(
    {
        "account.tenant_page",
        "account.tenant_select",
    }
)

# 各選択画面に出すエラー。クエリ文字列の値をそのまま表示しないための対応表。
_TENANT_ERRORS = {
    "not_member": "そのテナントに所属していません。管理者に追加を依頼してください。",
    "missing": "テナントを選択してください。",
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
        return redirect(TENANT_SELECT_PATH)
    return render_template("auth/login.html", **_login_page_context(None, ""))


@bp.post("/auth/login")
def login_submit() -> BaseResponse | tuple[str, int]:
    """ログインID＋パスワードでのみ認証する。

    ユーザー選択画面（旧 /auth/user）は廃止した。誰として使うかはログインで決まる。
    初期管理者は admin / password（web.services.auth_store.ensure_initial_admin）。
    """
    store = get_auth_store()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    try:
        user = store.authenticate(email, password)
    except AuthError as exc:
        return render_template("auth/login.html", **_login_page_context(str(exc), email)), 401
    return _start_session(user, TENANT_SELECT_PATH)


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
        # パスワードは必須。モックで緩むのは長さ要件だけ。
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
    # 作った本人として続けるのでテナント選択へ送る
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
def account_page() -> BaseResponse:
    """旧アカウント専用ページ。アプリ内の個人設定ビュー（/account）へ送る。

    表示方法を他のメニュー項目（ユーザーガイド等）と揃えるため画面内ビューへ移した。
    ブックマークや外部からのリンクを壊さないよう、この経路は残して転送する。
    """
    if not auth_enabled():
        return redirect("/")
    if getattr(g, "auth_user", None) is None:
        return redirect("/auth/login?next=/account")
    return redirect(ACCOUNT_VIEW_PATH)


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
