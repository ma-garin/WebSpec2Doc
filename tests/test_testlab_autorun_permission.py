"""System 02 の API は管理者だけ（画面と同じ判定）。System 03 のジョブは起動者か管理者だけが操作できる。
認証オフは従来どおり制限しない。"""
from __future__ import annotations

from pathlib import Path

import app as appmod
import pytest
from web import config
from web.routes import auto_run
from web.services.auto_run_job import AutoRunJob

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
    from web.services.auth_store import get_auth_store

    boot = appmod.app.test_client()
    boot.post("/auth/setup", data={"tenant_name": "T", "name": "Admin", "email": "admin@example.com",
                                   "password": PW, "password_confirm": PW}, headers=H)
    store = get_auth_store()
    tid = store.list_tenants()[0]["id"]
    store.create_user(tid, "alice@example.com", "Alice", PW)
    store.create_user(tid, "bob@example.com", "Bob", PW)
    return {n: _login(f"{n}@example.com") for n in ("admin", "alice", "bob")}


def test_ta2_api_is_admin_only_when_auth_on():
    users = _users()
    body = {"domain": "nosite.example", "ids": []}
    assert users["alice"].post("/api/ta2/run", json=body, headers=H).status_code == 403
    assert users["alice"].post("/api/ta2/recrawl", json={"domain": "nosite.example"}, headers=H).status_code == 403
    # 管理者は判定を通り、業務エラー（対象なし）に進む
    assert users["admin"].post("/api/ta2/run", json=body, headers=H).status_code in (400, 404)


def test_ta2_api_is_open_when_auth_off():
    client = appmod.app.test_client()
    assert client.post("/api/ta2/run", json={"domain": "nosite.example", "ids": []}, headers=H).status_code in (400, 404)


def test_autorun_job_is_operable_only_by_owner_or_admin(monkeypatch):
    users = _users()
    jobs: dict = {}
    monkeypatch.setattr(auto_run, "_JOBS", jobs)
    job = AutoRunJob(job_id="j1", url="http://127.0.0.1:1/")
    job._tenant_id = (users["alice"].get("/api/auth/tenants", headers=H).get_json()["tenants"][0]["tenant_id"])
    job._owner_id = "someone-else"
    jobs["j1"] = job
    assert users["bob"].post("/api/autorun/cancel", json={"job_id": "j1"}, headers=H).status_code == 403
    assert users["admin"].post("/api/autorun/cancel", json={"job_id": "j1"}, headers=H).status_code == 200


def test_autorun_job_of_other_tenant_is_hidden(monkeypatch):
    users = _users()
    jobs: dict = {}
    monkeypatch.setattr(auto_run, "_JOBS", jobs)
    job = AutoRunJob(job_id="j2", url="http://127.0.0.1:1/")
    job._tenant_id = "other-tenant"
    job._owner_id = "x"
    jobs["j2"] = job
    assert users["admin"].post("/api/autorun/cancel", json={"job_id": "j2"}, headers=H).status_code == 404
    assert users["alice"].get("/api/autorun/jobs", headers=H).get_json()["jobs"] == []
