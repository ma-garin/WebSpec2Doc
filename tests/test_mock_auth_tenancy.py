"""ログイン認証とテナント選択・所属管理のテスト。

ログインは「ログインID + パスワード」の1経路だけ。ユーザー選択画面（旧 /auth/user）は
廃止した。モック認証（WEBSPEC2DOC_AUTH_MOCK、既定で有効）が変えるのは
パスワードの長さ要件だけで、認証そのものは省略しない。

対象:
- ログイン → テナント選択 → システム選択の遷移
- 初期管理者（admin / password）でのログイン
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

# モック認証では長さ要件を課さないが、store を直接叩くテストは既定でポリシーが効く。
# 使い分けを意識しなくて済むよう、テスト用のパスワードは常に要件を満たすものにする。
ADMIN_PW = "admin-pass-123"
MEMBER_PW = "member-pass-123"


@pytest.fixture(autouse=True)
def _isolated_auth_db(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MODE", raising=False)
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MOCK", raising=False)  # 既定（有効）で検証する
    yield


def _client():
    return appmod.app.test_client()


def _setup_admin(client, email: str = "admin@example.com") -> None:
    """初期セットアップ。管理者はパスワード付きで作られる。"""
    response = client.post(
        "/auth/setup",
        data={
            "tenant_name": "Tenant A",
            "name": "Admin",
            "email": email,
            "password": ADMIN_PW,
            "password_confirm": ADMIN_PW,
        },
        headers=H,
    )
    assert response.status_code == 302


def _login(client, email: str, password: str = ADMIN_PW):
    """ログインだけ行う（テナントは未選択のまま）。"""
    return client.post("/auth/login", data={"email": email, "password": password}, headers=H)


def _select_first_tenant(client) -> None:
    payload = client.get("/api/auth/tenants", headers=H).get_json() or {}
    tenants = payload.get("tenants", [])
    if tenants:
        client.post("/auth/tenant", data={"tenant_id": tenants[0]["tenant_id"]}, headers=H)


def _login_and_work(client, email: str, password: str = ADMIN_PW):
    """ログイン → テナント選択まで済ませ、作業できる状態にする。"""
    response = _login(client, email, password)
    _select_first_tenant(client)
    return response


def _store():
    from web.services.auth_store import get_auth_store

    return get_auth_store()


# ---------- ログイン ----------


def test_setup_creates_admin_with_password() -> None:
    _setup_admin(_client())
    users = _store().list_all_users()
    assert len(users) == 1
    assert users[0]["has_password"] is True
    assert users[0]["memberships"][0]["role"] == "admin"


def test_user_select_route_is_gone() -> None:
    """ユーザー選択画面は廃止した。経路そのものが残っていないことを確かめる。

    テナント未選択のまま叩くと認証ガードのリダイレクトが先に返るため、
    ルートの不在を見るにはテナント選択まで済ませてから叩く。
    """
    _setup_admin(_client())
    client = _client()
    _login_and_work(client, "admin@example.com")
    assert client.get("/auth/user", headers=H).status_code == 404
    assert client.post("/auth/user", data={"user_id": ""}, headers=H).status_code == 404


def test_login_leads_through_tenant_then_system_select() -> None:
    """期待する順序: ログイン → テナント選択 → システム選択（/systems・2 カード）。"""
    _setup_admin(_client())
    client = _client()
    response = _login(client, "admin@example.com")
    assert response.status_code == 302
    assert response.headers["Location"] == "/auth/tenant"

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
        "/auth/login",
        data={"email": "admin@example.com", "password": ADMIN_PW, "next": "/"},
        headers=H,
    )
    assert response.headers["Location"] == "/auth/tenant"


def test_system_select_hub_shows_cards() -> None:
    """システム選択ハブは復活済み。ドキュメント作成・テスト自動化の 2 カードを出す。"""
    client = _client()
    _setup_admin(client)
    _login_and_work(client, "admin@example.com")
    response = client.get("/systems", headers=H)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "ドキュメント作成" in html
    assert "テスト自動化" in html


def test_login_rejects_unknown_email() -> None:
    _setup_admin(_client())
    response = _login(_client(), "nobody@example.com")
    assert response.status_code == 401


def test_login_rejects_wrong_password() -> None:
    _setup_admin(_client())
    response = _login(_client(), "admin@example.com", "wrong-pass-999")
    assert response.status_code == 401
    assert "正しくありません" in response.get_data(as_text=True)


def test_login_rejects_empty_password() -> None:
    """モックでもパスワードなしでは通さない。"""
    _setup_admin(_client())
    response = _login(_client(), "admin@example.com", "")
    assert response.status_code == 401


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
    assert response.headers["Location"] == "/auth/tenant"

    tenant_id = _store().list_tenants()[0]["id"]
    assert (
        client.post("/auth/tenant", data={"tenant_id": tenant_id}, headers=H).headers["Location"]
        == "/systems"
    )
    me = client.get("/api/auth/me", headers=H).get_json()
    assert me["user"]["role"] == "admin"
    assert me["tenant"]["slug"] == "default"


def test_initial_admin_cannot_log_in_without_password() -> None:
    _store().ensure_initial_admin()
    response = _client().post("/auth/login", data={"email": "admin"}, headers=H)
    assert response.status_code == 401


def test_login_page_shows_initial_admin_credentials() -> None:
    _store().ensure_initial_admin()
    html = _client().get("/auth/login", headers=H).get_data(as_text=True)
    assert "<b>admin</b> / <b>password</b>" in html  # 資格情報の案内は出す
    assert "userpick-item" not in html  # ユーザー選択の一覧は廃止した


def test_login_id_accepts_non_email_identifier() -> None:
    _store().ensure_initial_admin()
    store = _store()
    tenant_id = store.list_tenants()[0]["id"]
    user = store.create_user(tenant_id, "yamada", "山田", MEMBER_PW)
    assert user["email"] == "yamada"
    response = _client().post(
        "/auth/login", data={"email": "yamada", "password": MEMBER_PW}, headers=H
    )
    assert response.status_code == 302


def test_login_id_rejects_garbage() -> None:
    from web.services.auth_store import AuthError

    with pytest.raises(AuthError) as exc:
        _store().create_user(None, "駄目な ID", "X", MEMBER_PW)
    assert exc.value.code == "invalid_email"


def test_create_user_requires_password() -> None:
    """パスワードなしのユーザーは作らせない（作るとログインできないため）。"""
    from web.services.auth_store import AuthError

    with pytest.raises(AuthError) as exc:
        _store().create_user(None, "nopw@example.com", "NoPW", "")
    assert exc.value.code == "password_required"


# ---------- サインアップと所属 ----------


def test_signup_creates_user_without_membership() -> None:
    _setup_admin(_client())
    client = _client()
    response = client.post(
        "/auth/signup",
        data={"name": "New Member", "email": "new@example.com", "password": MEMBER_PW},
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
    client.post(
        "/auth/signup",
        data={"name": "New", "email": "new@example.com", "password": MEMBER_PW},
        headers=H,
    )
    response = client.get("/", headers=H)
    assert response.status_code == 302
    assert response.headers["Location"] == "/auth/tenant"


def test_unassigned_user_gets_json_error_on_api() -> None:
    _setup_admin(_client())
    client = _client()
    client.post(
        "/auth/signup",
        data={"name": "New", "email": "new@example.com", "password": MEMBER_PW},
        headers=H,
    )
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
    user = store.create_user(tenant_a, "multi@example.com", "Multi", MEMBER_PW)
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
    response = _login(client, "multi@example.com", MEMBER_PW)
    assert response.headers["Location"] == "/auth/tenant"

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
    _login(client, "multi@example.com", MEMBER_PW)
    response = client.post("/auth/tenant", data={"tenant_id": outsider}, headers=H)
    assert response.headers["Location"] == "/auth/tenant?error=not_member"
    assert client.get("/api/auth/me", headers=H).get_json()["tenant"] is None


def test_role_follows_selected_tenant() -> None:
    """同じ人がテナントAでは一般、テナントBでは管理者になる。"""
    _setup_admin(_client())
    _, tenant_a, tenant_b = _two_tenant_user()
    client = _client()
    _login(client, "multi@example.com", MEMBER_PW)

    client.post("/auth/tenant", data={"tenant_id": tenant_a}, headers=H)
    assert client.get("/api/auth/me", headers=H).get_json()["user"]["role"] == "member"
    assert client.get("/admin/console", headers=H).headers["Location"] == "/systems"

    client.post("/auth/tenant", data={"tenant_id": tenant_b}, headers=H)
    assert client.get("/api/auth/me", headers=H).get_json()["user"]["role"] == "admin"
    # 管理画面はユーザー管理ビューへ統合済み。管理者は転送され、一般はシステム選択へ戻る
    assert client.get("/admin/console", headers=H).headers["Location"] == "/user-management"


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
        json={
            "name": "山田",
            "email": "yamada@example.com",
            "tenant_id": tenant_id,
            "role": "member",
            "password": MEMBER_PW,
        },
        headers=H,
    )
    assert added.status_code == 200
    users = {u["email"]: u for u in added.get_json()["users"]}
    assert users["yamada@example.com"]["memberships"][0]["role"] == "member"
    # 管理者が発行した初期パスワードを持つ（パスワードなしのユーザーは作れない）
    assert users["yamada@example.com"]["has_password"] is True


def test_admin_cannot_create_user_without_password() -> None:
    client = _admin_client()
    response = client.post(
        "/api/admin/tenancy/users",
        json={"name": "山田", "email": "yamada@example.com", "role": "member"},
        headers=H,
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "password_required"


def test_admin_can_replace_memberships() -> None:
    client = _admin_client()
    store = _store()
    tenant_b = store.create_tenant("Tenant B")["id"]
    user = store.create_user(None, "free@example.com", "Free", MEMBER_PW)

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
    _login(member, "multi@example.com", MEMBER_PW)
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
    store.create_user(tenant_a, "member@example.com", "Member", MEMBER_PW)
    client = _client()
    _login_and_work(client, "member@example.com", MEMBER_PW)
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
