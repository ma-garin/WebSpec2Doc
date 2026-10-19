"""書き込み API の操作者・権限（C-P0-2）。System 07 は案件メンバーだけが書ける・操作者を記録する。
System 09 の旧 API（/api/impact/jobs 系）は管理者だけ。認証オフは従来どおり制限しない。"""
from __future__ import annotations

from pathlib import Path

import app as appmod
import pytest
from web import config

H = {"Host": "127.0.0.1"}
PW = "member-pass-123"


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MODE", raising=False)
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MOCK", raising=False)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    yield


def _login(email: str):
    client = appmod.app.test_client()
    client.post("/auth/login", data={"email": email, "password": PW}, headers=H)
    tenants = (client.get("/api/auth/tenants", headers=H).get_json() or {}).get("tenants", [])
    if tenants:
        client.post("/auth/tenant", data={"tenant_id": tenants[0]["tenant_id"]}, headers=H)
    return client


def _users():
    """admin・alice・bob の 3 人。認証オンで各人のクライアントを返す。"""
    from web.services.auth_store import get_auth_store

    boot = appmod.app.test_client()
    boot.post("/auth/setup", data={"tenant_name": "T", "name": "Admin", "email": "admin@example.com",
                                   "password": PW, "password_confirm": PW}, headers=H)
    store = get_auth_store()
    tid = store.list_tenants()[0]["id"]
    store.create_user(tid, "alice@example.com", "Alice", PW)
    store.create_user(tid, "bob@example.com", "Bob", PW)
    return {n: _login(f"{n}@example.com") for n in ("admin", "alice", "bob")}


def test_s07_non_member_write_is_403_and_actor_is_recorded():
    users = _users()
    alice, bob, admin = users["alice"], users["bob"], users["admin"]
    created = alice.post("/api/batch-test/jobs", json={"name": "月次"}, headers=H)
    assert created.status_code == 201
    jid = created.get_json()["job"]["id"]
    job = alice.get(f"/api/batch-test/jobs/{jid}", headers=H).get_json()["job"]
    assert job["members"] == {"alice@example.com": "owner"} and job["created_by"] == "alice@example.com"

    denied = bob.patch(f"/api/batch-test/jobs/{jid}", json={"name": "乗っ取り"}, headers=H)
    assert denied.status_code == 403 and "権限" in denied.get_json()["error"]
    assert bob.delete(f"/api/batch-test/jobs/{jid}", headers=H).status_code == 403
    assert bob.get(f"/api/batch-test/jobs/{jid}", headers=H).status_code == 200  # 読むのは可

    ok = alice.patch(f"/api/batch-test/jobs/{jid}", json={"name": "月次2"}, headers=H)
    assert ok.status_code == 200
    job = alice.get(f"/api/batch-test/jobs/{jid}", headers=H).get_json()["job"]
    assert job["name"] == "月次2" and job["updated_by"] == "alice@example.com"
    assert job["audit"][-1]["actor"] == "alice@example.com" and job["audit"][-1]["op"].startswith("PATCH")
    assert admin.patch(f"/api/batch-test/jobs/{jid}", json={"name": "管理"}, headers=H).status_code == 200
    assert alice.delete(f"/api/batch-test/jobs/{jid}", headers=H).status_code == 200


def test_s09_legacy_write_api_is_admin_only():
    users = _users()
    alice, admin = users["alice"], users["admin"]
    assert alice.post("/api/impact/jobs", json={"name": "旧"}, headers=H).status_code == 403
    assert alice.post("/api/impact/sample", headers=H).status_code == 403
    assert alice.delete("/api/impact/library/x.txt", headers=H).status_code == 403
    assert alice.get("/api/impact/jobs", headers=H).status_code == 200  # 読むのは可
    r = admin.post("/api/impact/jobs", json={"name": "旧"}, headers=H)
    assert r.status_code == 201


def test_auth_off_keeps_working(monkeypatch):
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    c = appmod.app.test_client()
    r = c.post("/api/batch-test/jobs", json={"name": "開発"}, headers=H)
    assert r.status_code == 201
    jid = r.get_json()["job"]["id"]
    assert c.patch(f"/api/batch-test/jobs/{jid}", json={"name": "開発2"}, headers=H).status_code == 200
    job = c.get(f"/api/batch-test/jobs/{jid}", headers=H).get_json()["job"]
    assert job["updated_by"] == "local"
    assert c.post("/api/impact/jobs", json={"name": "旧"}, headers=H).status_code == 201
