"""アプリ利用者認証ルート（/auth/*, /api/auth/*）と認可ガードの統合テスト。

クロール対象サイトへのログイン（/api/login/*, tests/test_app_login.py）とは別機能。
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
    """テストごとに独立した認証DBを使う（get_auth_store は env 変更に追従する）。"""
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MODE", raising=False)
    yield


def _client():
    return appmod.app.test_client()


def _setup_owner(client, email="owner@example.com", password="secret-pass-123"):
    return client.post(
        "/auth/setup",
        data={
            "tenant_name": "QA Team",
            "name": "Owner",
            "email": email,
            "password": password,
            "password_confirm": password,
        },
        headers=H,
    )


def _login(client, email="owner@example.com", password="secret-pass-123"):
    return client.post(
        "/auth/login", data={"email": email, "password": password, "next": "/"}, headers=H
    )


# ---------- auto モード（既定） ----------


def test_open_access_while_no_user_exists() -> None:
    c = _client()
    assert c.get("/", headers=H).status_code == 200
    assert c.get("/api/history", headers=H).status_code == 200


def test_login_required_after_setup() -> None:
    c = _client()
    res = _setup_owner(c)
    assert res.status_code == 302
    assert "ws2d_session" in (res.headers.get("Set-Cookie") or "")

    anon = _client()
    page = anon.get("/", headers=H)
    assert page.status_code == 302
    assert "/auth/login" in page.headers["Location"]
    # API は JSON 401
    api = anon.get("/api/history", headers=H)
    assert api.status_code == 401
    assert api.get_json()["code"] == "unauthorized"


def test_login_flow_and_logout() -> None:
    c = _client()
    _setup_owner(c)
    anon = _client()
    bad = _login(anon, password="wrong-password")
    assert bad.status_code == 401
    assert "ログインできませんでした" in bad.get_data(as_text=True)
    ok = _login(anon)
    assert ok.status_code == 302 and ok.headers["Location"] == "/"
    me = anon.get("/api/auth/me", headers=H).get_json()
    assert me["user"]["email"] == "owner@example.com"
    assert me["tenant"]["slug"] == "qa-team"
    out = anon.post("/auth/logout", headers=H)
    assert out.status_code == 302
    assert anon.get("/api/history", headers=H).status_code == 401


def test_login_next_open_redirect_blocked() -> None:
    c = _client()
    _setup_owner(c)
    anon = _client()
    res = anon.post(
        "/auth/login",
        data={
            "email": "owner@example.com",
            "password": "secret-pass-123",
            "next": "//evil.example.com/",
        },
        headers=H,
    )
    assert res.status_code == 302
    assert res.headers["Location"] == "/"


def test_setup_page_redirects_to_login_after_setup() -> None:
    c = _client()
    _setup_owner(c)
    res = _client().get("/auth/setup", headers=H)
    assert res.status_code == 302
    assert "/auth/login" in res.headers["Location"]


def test_healthz_exempt_from_auth() -> None:
    c = _client()
    _setup_owner(c)
    res = _client().get("/api/v1/healthz", headers=H)
    assert res.status_code == 200


# ---------- required / off モード ----------


def test_required_mode_redirects_to_setup_when_no_user(monkeypatch) -> None:
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "required")
    c = _client()
    res = c.get("/", headers=H)
    assert res.status_code == 302
    assert "/auth/setup" in res.headers["Location"]


def test_off_mode_disables_auth_even_with_users(monkeypatch) -> None:
    c = _client()
    _setup_owner(c)
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    anon = _client()
    assert anon.get("/", headers=H).status_code == 200
    # ログイン画面はトップへ戻す
    res = anon.get("/auth/login", headers=H)
    assert res.status_code == 302 and res.headers["Location"] == "/"


# ---------- 初回オンボーディング ----------


def test_onboarding_uses_client_storage_when_auth_is_off(monkeypatch) -> None:
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    c = _client()
    data = c.get("/api/onboarding", headers=H).get_json()
    assert data["storage"] == "client"
    assert data["tour_completed"] is None
    assert set(data["checklist"]) == {"site_registered", "first_crawl", "report_available"}


def test_onboarding_auto_tour_is_suppressed_in_e2e_mode(monkeypatch) -> None:
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    previous = appmod.app.config.get("TESTING", False)
    appmod.app.config["TESTING"] = True
    try:
        data = _client().get("/api/onboarding", headers=H).get_json()
    finally:
        appmod.app.config["TESTING"] = previous
    assert data["auto_start"] is False


def test_onboarding_completion_is_persisted_for_logged_in_user() -> None:
    c = _client()
    _setup_owner(c)
    before = c.get("/api/onboarding", headers=H).get_json()
    assert before["storage"] == "server"
    assert before["tour_completed"] is False
    completed = c.post("/api/onboarding/complete", headers=H)
    assert completed.status_code == 200
    after = c.get("/api/onboarding", headers=H).get_json()
    assert after["tour_completed"] is True


# ---------- アカウント管理 API ----------


def test_admin_can_create_and_deactivate_member() -> None:
    c = _client()
    _setup_owner(c)
    res = c.post(
        "/api/auth/users",
        json={
            "email": "member@example.com",
            "name": "Member",
            "password": "member-pass-123",
            "role": "member",
        },
        headers=H,
    )
    assert res.status_code == 200
    user_id = res.get_json()["user"]["id"]

    users = c.get("/api/auth/users", headers=H).get_json()["users"]
    assert {u["email"] for u in users} == {"owner@example.com", "member@example.com"}

    res = c.patch(f"/api/auth/users/{user_id}", json={"is_active": False}, headers=H)
    assert res.status_code == 200
    mc = _client()
    bad = _login(mc, email="member@example.com", password="member-pass-123")
    assert bad.status_code == 401


def test_member_cannot_manage_users_or_settings() -> None:
    c = _client()
    _setup_owner(c)
    c.post(
        "/api/auth/users",
        json={
            "email": "member@example.com",
            "name": "Member",
            "password": "member-pass-123",
            "role": "member",
        },
        headers=H,
    )
    mc = _client()
    _login(mc, email="member@example.com", password="member-pass-123")
    assert mc.get("/api/auth/users", headers=H).status_code == 403
    assert mc.post("/api/auth/users", json={"email": "x@example.com"}, headers=H).status_code == 403
    # 設定変更（OpenAIキー等）も管理者限定
    assert mc.post("/api/settings", data={"api_key": "sk-x"}, headers=H).status_code == 403
    # 参照は可能
    assert mc.get("/api/settings", headers=H).status_code == 200


def test_admin_cannot_create_owner() -> None:
    c = _client()
    _setup_owner(c)
    c.post(
        "/api/auth/users",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "password": "admin-pass-1234",
            "role": "admin",
        },
        headers=H,
    )
    ac = _client()
    _login(ac, email="admin@example.com", password="admin-pass-1234")
    res = ac.post(
        "/api/auth/users",
        json={
            "email": "o2@example.com",
            "name": "O2",
            "password": "owner-pass-1234",
            "role": "owner",
        },
        headers=H,
    )
    assert res.status_code == 403


def test_password_change_forces_relogin() -> None:
    c = _client()
    _setup_owner(c)
    res = c.post(
        "/api/auth/password",
        json={"current": "secret-pass-123", "new": "renewed-pass-456"},
        headers=H,
    )
    assert res.status_code == 200 and res.get_json()["relogin"] is True
    # 旧セッションは失効している
    assert c.get("/api/history", headers=H).status_code == 401


# ---------- /api/v1 Bearer APIトークン ----------


def test_api_v1_accepts_bearer_token() -> None:
    c = _client()
    _setup_owner(c)
    created = c.post("/api/auth/api-tokens", json={"name": "ci"}, headers=H).get_json()["token"]

    anon = _client()
    assert anon.get("/api/v1/sites", headers=H).status_code == 401
    ok = anon.get("/api/v1/sites", headers={**H, "Authorization": f"Bearer {created['token']}"})
    assert ok.status_code == 200
    bad = anon.get("/api/v1/sites", headers={**H, "Authorization": "Bearer ws2d_invalid"})
    assert bad.status_code == 401


def test_revoked_bearer_token_rejected() -> None:
    c = _client()
    _setup_owner(c)
    created = c.post("/api/auth/api-tokens", json={"name": "ci"}, headers=H).get_json()["token"]
    c.delete(f"/api/auth/api-tokens/{created['id']}", headers=H)
    anon = _client()
    res = anon.get("/api/v1/sites", headers={**H, "Authorization": f"Bearer {created['token']}"})
    assert res.status_code == 401


# ---------- アカウントページ ----------


def test_account_page_renders_for_admin() -> None:
    c = _client()
    _setup_owner(c)
    html = c.get("/auth/account", headers=H).get_data(as_text=True)
    assert "プロフィール" in html
    assert "メンバー管理" in html
    assert "APIトークン" in html


def test_topbar_shows_account_chip_when_logged_in() -> None:
    c = _client()
    _setup_owner(c)
    html = c.get("/", headers=H).get_data(as_text=True)
    assert "/auth/account" in html
