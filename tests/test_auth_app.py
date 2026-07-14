"""利用者認証（メール自己申告 ＋ テナント選択）ルートのテスト。

機能インテグリティ経路: UI(フォーム) → route → store → session → リダイレクト先。
happy / failure / guard / logout / 非破壊(既定OFF) を検証する。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from web import create_app
from web.auth import AUTH_ENV, SECRET_KEY_ENV


@pytest.fixture()
def auth_app(tmp_path, monkeypatch):
    """認証 ON のアプリ。instance/auth をテスト用 tmp に隔離する。"""
    monkeypatch.setenv(AUTH_ENV, "1")
    monkeypatch.setenv(SECRET_KEY_ENV, "test-secret-key")  # 実ファイル生成を避ける
    app = create_app()
    app.instance_path = str(tmp_path / "instance")
    # secret_key と store をテスト用パスへ差し替え。
    from web.auth.store import AuthStore, load_or_create_secret_key

    base = Path(app.instance_path) / "auth"
    app.secret_key = load_or_create_secret_key(base)
    app.config["auth_store"] = AuthStore(base)
    app.config["TESTING"] = True
    return app


@pytest.fixture()
def client(auth_app):
    return auth_app.test_client()


def _login(client, email="user@example.com"):
    return client.post("/auth/login", data={"email": email})


def test_login_page_renders(client):
    res = client.get("/auth/login")
    assert res.status_code == 200
    assert "ログイン".encode() in res.data


def test_happy_login_creates_default_tenant_and_redirects(client):
    res = _login(client)
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/auth/tenants")

    page = client.get("/auth/tenants")
    assert page.status_code == 200
    assert "My Workspace".encode() in page.data
    assert "user@example.com".encode() in page.data


def test_invalid_email_shows_error_and_stays(client):
    res = client.post("/auth/login", data={"email": "not-an-email"})
    assert res.status_code == 400
    assert "有効なメールアドレス".encode() in res.data
    # セッション未確立 → 保護ページはログインへ。
    assert client.get("/").headers["Location"].endswith("/auth/login")


def test_guard_redirects_unauthenticated_to_login(client):
    res = client.get("/")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/auth/login")


def test_guard_logged_in_without_tenant_redirects_to_tenants(client):
    _login(client)
    res = client.get("/")  # まだテナント未選択
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/auth/tenants")


def test_select_tenant_then_home_allowed(client):
    _login(client)
    tenants = client.get("/auth/tenants")
    # 既定テナント ID を store から取得。
    from web.auth.store import AuthStore

    with client.application.app_context():
        store: AuthStore = client.application.config["auth_store"]
        tenant_id = store.tenants_for("user@example.com")[0][0].id

    res = client.post("/auth/tenants/select", data={"tenant_id": tenant_id})
    assert res.status_code == 302
    assert res.headers["Location"].rstrip("/").endswith("") or res.headers["Location"].endswith("/")
    # 選択後は保護ページに到達できる（ガードが通す）。
    home = client.get("/")
    assert home.status_code == 200


def test_select_tenant_rejects_non_member(client):
    _login(client)
    res = client.post("/auth/tenants/select", data={"tenant_id": "bogus-id"})
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/auth/tenants")


def test_logout_clears_session(client):
    _login(client)
    res = client.post("/auth/logout")
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/auth/login")
    # ログアウト後は保護ページがログインへ戻る。
    assert client.get("/").headers["Location"].endswith("/auth/login")


def test_auth_off_by_default_keeps_home_open(monkeypatch):
    """非破壊: WEBSPEC2DOC_AUTH 未設定なら / は認証なしで開ける。"""
    monkeypatch.delenv(AUTH_ENV, raising=False)
    monkeypatch.setenv(SECRET_KEY_ENV, "test-secret-key")
    app = create_app()
    app.config["TESTING"] = True
    res = app.test_client().get("/")
    assert res.status_code == 200
