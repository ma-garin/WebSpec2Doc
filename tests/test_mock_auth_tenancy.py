"""モック認証（パスワードなし）とテナント選択・所属管理のテスト。

対象:
- ログイン画面の「用意されているユーザー」一覧とメールだけのログイン
- 所属件数に応じた遷移（0/複数 → テナント選択、1件 → 自動選択）
- テナント未選択の保護ルート、所属外テナントの拒否
- 管理画面（テナント作成・ユーザー作成・所属の一括更新・削除の防御）
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod

H = {"Host": "127.0.0.1"}


@pytest.fixture(autouse=True)
def _isolated_auth_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MODE", raising=False)
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MOCK", raising=False)  # 既定（有効）で検証する
    yield


def _client():
    return appmod.app.test_client()


def _setup_admin(client, email: str = "admin@example.com") -> None:
    """初期セットアップ。モック認証ではパスワードを送らない。"""
    response = client.post(
        "/auth/setup",
        data={"tenant_name": "Tenant A", "name": "Admin", "email": email},
        headers=H,
    )
    assert response.status_code == 302


def _login(client, email: str, password: str = ""):
    """ログインだけ行う（テナントは未選択のまま）。"""
    return client.post(
        "/auth/login", data={"email": email, "password": password}, headers=H
    )


def _select_first_tenant(client) -> None:
    payload = client.get("/api/auth/tenants", headers=H).get_json() or {}
    tenants = payload.get("tenants", [])
    if tenants:
        client.post("/auth/tenant", data={"tenant_id": tenants[0]["tenant_id"]}, headers=H)


def _login_and_work(client, email: str, password: str = ""):
    """ログイン → テナント選択まで済ませ、作業できる状態にする。"""
    response = _login(client, email, password)
    _select_first_tenant(client)
    return response


def _store():
    from web.services.auth_store import get_auth_store

    return get_auth_store()


# ---------- モックログイン ----------


def test_setup_creates_passwordless_admin() -> None:
    _setup_admin(_client())
    users = _store().list_all_users()
    assert len(users) == 1
    assert users[0]["has_password"] is False
    assert users[0]["memberships"][0]["role"] == "admin"


def test_user_select_page_lists_prepared_users() -> None:
    _setup_admin(_client())
    client = _client()
    _login(client, "admin@example.com")
    html = client.get("/auth/user", headers=H).get_data(as_text=True)
    assert "どのユーザーとして使いますか" in html
    assert "admin@example.com" in html


def test_login_leads_through_user_tenant_then_systems() -> None:
    """期待する順序: ログイン → ユーザー選択 → テナント選択 → システム選択。"""
    _setup_admin(_client())
    client = _client()
    response = _login(client, "admin@example.com")
    assert response.status_code == 302
    assert response.headers["Location"] == "/auth/user"

    kept = client.post("/auth/user", data={"user_id": ""}, headers=H)
    assert kept.headers["Location"] == "/auth/tenant"

    tenant_id = _store().list_tenants()[0]["id"]
    selected = client.post("/auth/tenant", data={"tenant_id": tenant_id}, headers=H)
    assert selected.headers["Location"] == "/systems"
    assert client.get("/api/auth/me", headers=H).get_json()["tenant"]["slug"] == "tenant-a"


def test_login_never_lands_on_document_wizard() -> None:
    """認証ガードが付けた next（"/"）でシステム選択を飛ばさない。"""
    _setup_admin(_client())
    client = _client()
    redirected = client.get("/", headers=H)
    assert redirected.status_code == 302
    response = client.post(
        "/auth/login", data={"email": "admin@example.com", "next": "/"}, headers=H
    )
    assert response.headers["Location"] == "/auth/user"


def test_system_select_links_to_each_system_top() -> None:
    """システム選択の各カードは、そのシステムの TOP へ送る（作業画面へ直行しない）。"""
    client = _client()
    _setup_admin(client)
    html = client.get("/systems", headers=H).get_data(as_text=True)
    assert 'href="/dashboard"' in html  # ドキュメント作成の TOP
    assert 'href="/auto-run"' in html  # AutoRun の TOP
    assert 'href="/generate"' not in html  # 「サイトを追加」は入口にしない


def test_user_switch_changes_identity() -> None:
    _setup_admin(_client())
    store = _store()
    tenant_id = store.list_tenants()[0]["id"]
    target = store.create_user(tenant_id, "member@example.com", "Member", "")
    client = _client()
    _login(client, "admin@example.com")
    response = client.post("/auth/user", data={"user_id": target["id"]}, headers=H)
    assert response.headers["Location"] == "/auth/tenant"
    assert client.get("/api/auth/me", headers=H).get_json()["user"]["email"] == "member@example.com"


def test_login_rejects_unknown_email() -> None:
    _setup_admin(_client())
    response = _login(_client(), "nobody@example.com")
    assert response.status_code == 401


def test_login_rejects_user_that_has_password() -> None:
    """モックを有効にしただけで、パスワード保護されたアカウントが素通りしない。"""
    _setup_admin(_client())
    store = _store()
    tenant_id = store.list_tenants()[0]["id"]
    store.create_user(tenant_id, "pw@example.com", "PW", "secret-pass-123")
    response = _login(_client(), "pw@example.com")
    assert response.status_code == 401
    assert "パスワードが必要" in response.get_data(as_text=True)


# ---------- 初期管理者（admin / password） ----------


def test_ensure_initial_admin_creates_admin_and_tenant() -> None:
    from web.services.auth_store import (
        INITIAL_ADMIN_LOGIN_ID,
        INITIAL_TENANT_SLUG,
    )

    created = _store().ensure_initial_admin()
    assert created is not None
    assert created["user"]["email"] == INITIAL_ADMIN_LOGIN_ID
    assert created["tenant"]["slug"] == INITIAL_TENANT_SLUG
    assert created["user"]["role"] == "admin"


def test_ensure_initial_admin_is_idempotent() -> None:
    store = _store()
    store.ensure_initial_admin()
    assert store.ensure_initial_admin() is None
    assert len(store.list_all_users()) == 1


def test_initial_admin_logs_in_with_password() -> None:
    _store().ensure_initial_admin()
    client = _client()
    response = client.post(
        "/auth/login", data={"email": "admin", "password": "password"}, headers=H
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/auth/user"

    assert client.post("/auth/user", data={"user_id": ""}, headers=H).headers[
        "Location"
    ] == "/auth/tenant"
    tenant_id = _store().list_tenants()[0]["id"]
    assert client.post("/auth/tenant", data={"tenant_id": tenant_id}, headers=H).headers[
        "Location"
    ] == "/systems"
    me = client.get("/api/auth/me", headers=H).get_json()
    assert me["user"]["role"] == "admin"
    assert me["tenant"]["slug"] == "default"


def test_initial_admin_cannot_log_in_without_password() -> None:
    """パスワードを持つアカウントは、モックでも素通りさせない。"""
    _store().ensure_initial_admin()
    response = _client().post("/auth/login", data={"email": "admin"}, headers=H)
    assert response.status_code == 401
    assert "パスワードが必要" in response.get_data(as_text=True)


def test_login_page_shows_initial_admin_credentials() -> None:
    _store().ensure_initial_admin()
    html = _client().get("/auth/login", headers=H).get_data(as_text=True)
    assert "<b>admin</b> / <b>password</b>" in html  # 資格情報の案内は出す
    assert "userpick-item" not in html  # 一覧はユーザー選択画面へ移した


def test_cannot_switch_to_password_protected_user() -> None:
    """パスワードを持つアカウントには、選ぶだけでは切り替えられない。"""
    store = _store()
    store.ensure_initial_admin()
    tenant_id = store.list_tenants()[0]["id"]
    store.create_user(tenant_id, "member@example.com", "Member", "")
    client = _client()
    _login(client, "member@example.com")
    response = client.post("/auth/user", data={"user_id": _user_id("admin")}, headers=H)
    assert response.headers["Location"] == "/auth/user?error=not_switchable"
    assert (
        client.get("/api/auth/me", headers=H).get_json()["user"]["email"] == "member@example.com"
    )


def test_login_id_accepts_non_email_identifier() -> None:
    _store().ensure_initial_admin()
    store = _store()
    tenant_id = store.list_tenants()[0]["id"]
    user = store.create_user(tenant_id, "yamada", "山田", "")
    assert user["email"] == "yamada"
    response = _client().post("/auth/login", data={"email": "yamada"}, headers=H)
    assert response.status_code == 302


def test_login_id_rejects_garbage() -> None:
    from web.services.auth_store import AuthError

    with pytest.raises(AuthError) as exc:
        _store().create_user(None, "駄目な ID", "X", "")
    assert exc.value.code == "invalid_email"


# ---------- サインアップと所属 ----------


def test_signup_creates_user_without_membership() -> None:
    _setup_admin(_client())
    client = _client()
    response = client.post(
        "/auth/signup",
        data={"name": "New Member", "email": "new@example.com"},
        headers=H,
    )
    assert response.status_code == 302
    assert response.headers["Location"].startswith("/auth/tenant")

    page = client.get("/auth/tenant", headers=H).get_data(as_text=True)
    assert "まだどのテナントにも所属していません" in page
    assert _store().list_memberships(_user_id("new@example.com")) == []


def test_unassigned_user_is_redirected_from_protected_pages() -> None:
    _setup_admin(_client())
    client = _client()
    client.post("/auth/signup", data={"name": "New", "email": "new@example.com"}, headers=H)
    response = client.get("/systems", headers=H)
    assert response.status_code == 302
    assert response.headers["Location"] == "/auth/tenant"


def test_unassigned_user_gets_json_error_on_api() -> None:
    _setup_admin(_client())
    client = _client()
    client.post("/auth/signup", data={"name": "New", "email": "new@example.com"}, headers=H)
    response = client.get("/api/history", headers=H)
    assert response.status_code == 401
    assert response.get_json()["code"] == "tenant_required"


# ---------- テナント選択 ----------


def _user_id(email: str) -> str:
    for user in _store().list_all_users():
        if user["email"] == email:
            return str(user["id"])
    raise AssertionError(f"user not found: {email}")


def _two_tenant_user() -> tuple[str, str, str]:
    """テナント2つに所属する一般ユーザーを作り、(user_id, tenant_a_id, tenant_b_id) を返す。"""
    store = _store()
    tenant_a = store.list_tenants()[0]["id"]
    tenant_b = store.create_tenant("Tenant B")["id"]
    user = store.create_user(tenant_a, "multi@example.com", "Multi", "")
    store.set_memberships(
        user["id"],
        [
            {"tenant_id": tenant_a, "role": "member"},
            {"tenant_id": tenant_b, "role": "admin"},
        ],
    )
    return str(user["id"]), tenant_a, tenant_b


def test_multi_tenant_user_must_choose() -> None:
    _setup_admin(_client())
    _, tenant_a, _tenant_b = _two_tenant_user()
    client = _client()
    response = _login(client, "multi@example.com")
    assert response.headers["Location"] == "/auth/user"
    client.post("/auth/user", data={"user_id": ""}, headers=H)

    page = client.get("/auth/tenant", headers=H).get_data(as_text=True)
    assert "Tenant A" in page
    assert "Tenant B" in page

    selected = client.post("/auth/tenant", data={"tenant_id": tenant_a}, headers=H)
    assert selected.headers["Location"] == "/systems"
    assert client.get("/api/auth/me", headers=H).get_json()["tenant"]["slug"] == "tenant-a"


def test_cannot_select_tenant_without_membership() -> None:
    _setup_admin(_client())
    _two_tenant_user()
    store = _store()
    outsider = store.create_tenant("Outsider")["id"]
    client = _client()
    _login(client, "multi@example.com")
    response = client.post("/auth/tenant", data={"tenant_id": outsider}, headers=H)
    assert response.headers["Location"] == "/auth/tenant?error=not_member"
    assert client.get("/api/auth/me", headers=H).get_json()["tenant"] is None


def test_role_follows_selected_tenant() -> None:
    """同じ人がテナントAでは一般、テナントBでは管理者になる。"""
    _setup_admin(_client())
    _, tenant_a, tenant_b = _two_tenant_user()
    client = _client()
    _login(client, "multi@example.com")

    client.post("/auth/tenant", data={"tenant_id": tenant_a}, headers=H)
    assert client.get("/api/auth/me", headers=H).get_json()["user"]["role"] == "member"
    assert client.get("/admin/console", headers=H).headers["Location"] == "/systems"

    client.post("/auth/tenant", data={"tenant_id": tenant_b}, headers=H)
    assert client.get("/api/auth/me", headers=H).get_json()["user"]["role"] == "admin"
    assert client.get("/admin/console", headers=H).status_code == 200


# ---------- 管理画面 ----------


def _admin_client():
    _setup_admin(_client())
    client = _client()
    _login_and_work(client, "admin@example.com")
    return client


def test_admin_can_create_tenant_and_user() -> None:
    client = _admin_client()
    created = client.post(
        "/api/admin/tenancy/tenants", json={"name": "決済PJ", "slug": "payment"}, headers=H
    )
    assert created.status_code == 200
    assert created.get_json()["tenant"]["slug"] == "payment"

    tenant_id = created.get_json()["tenant"]["id"]
    added = client.post(
        "/api/admin/tenancy/users",
        json={"name": "山田", "email": "yamada@example.com", "tenant_id": tenant_id, "role": "member"},
        headers=H,
    )
    assert added.status_code == 200
    users = {u["email"]: u for u in added.get_json()["users"]}
    assert users["yamada@example.com"]["memberships"][0]["role"] == "member"
    # パスワードは持たせない（メールアドレスだけでログインする）
    assert users["yamada@example.com"]["has_password"] is False


def test_admin_can_replace_memberships() -> None:
    client = _admin_client()
    store = _store()
    tenant_b = store.create_tenant("Tenant B")["id"]
    user = store.create_user(None, "free@example.com", "Free", "")

    response = client.put(
        f"/api/admin/tenancy/users/{user['id']}/memberships",
        json={"memberships": [{"tenant_id": tenant_b, "role": "admin"}]},
        headers=H,
    )
    assert response.status_code == 200
    assert response.get_json()["memberships"][0]["role"] == "admin"

    cleared = client.put(
        f"/api/admin/tenancy/users/{user['id']}/memberships",
        json={"memberships": []},
        headers=H,
    )
    # Tenant B の管理者が居なくなるため拒否される
    assert cleared.status_code == 400
    assert cleared.get_json()["code"] == "last_admin"


def test_removing_selected_tenant_membership_forces_reselection() -> None:
    client = _admin_client()
    user_id, tenant_a, tenant_b = _two_tenant_user()
    member = _client()
    _login(member, "multi@example.com")
    member.post("/auth/tenant", data={"tenant_id": tenant_a}, headers=H)
    assert member.get("/api/auth/me", headers=H).get_json()["tenant"] is not None

    client.put(
        f"/api/admin/tenancy/users/{user_id}/memberships",
        json={"memberships": [{"tenant_id": tenant_b, "role": "admin"}]},
        headers=H,
    )
    assert member.get("/api/auth/me", headers=H).get_json()["tenant"] is None


def test_last_tenant_cannot_be_deleted() -> None:
    client = _admin_client()
    tenant_id = _store().list_tenants()[0]["id"]
    response = client.delete(f"/api/admin/tenancy/tenants/{tenant_id}", headers=H)
    assert response.status_code == 400
    assert response.get_json()["code"] == "last_tenant"


def test_tenant_delete_keeps_output_files() -> None:
    client = _admin_client()
    created = client.post(
        "/api/admin/tenancy/tenants", json={"name": "Temp"}, headers=H
    ).get_json()["tenant"]
    response = client.delete(f"/api/admin/tenancy/tenants/{created['id']}", headers=H)
    assert response.status_code == 200
    assert "残っています" in response.get_json()["note"]
    assert all(t["id"] != created["id"] for t in response.get_json()["tenants"])


def test_member_cannot_reach_admin_api() -> None:
    _setup_admin(_client())
    store = _store()
    tenant_a = store.list_tenants()[0]["id"]
    store.create_user(tenant_a, "member@example.com", "Member", "")
    client = _client()
    _login_and_work(client, "member@example.com")
    assert client.get("/api/admin/tenancy", headers=H).status_code == 403
    assert (
        client.post("/api/admin/tenancy/tenants", json={"name": "X"}, headers=H).status_code == 403
    )


def test_admin_cannot_delete_self() -> None:
    client = _admin_client()
    admin_id = _user_id("admin@example.com")
    response = client.delete(f"/api/admin/tenancy/users/{admin_id}", headers=H)
    assert response.status_code == 400
    assert response.get_json()["code"] == "self_delete"
