"""System06 ← System01 観測 Evidence: 実保存形式（output/<domain>/report.json）→ link → API、テナント境界。"""
from __future__ import annotations

import json
from pathlib import Path

import app as appmod
import pytest
from web import config
from web.services.docassure import links_sys01

H = {"Host": "127.0.0.1"}
PW = "member-pass-123"
BASE = "/api/docassure/inspections"
DOC = {"id": "D1", "name": "要件", "type": "requirements",
       "text": "FR-1 利用者は「ログイン」ボタンでログインできること。\nFR-2 管理者は「監査ログ」を閲覧できる。"}


def _report(path: Path, domain: str):
    d = path / domain
    d.mkdir(parents=True)
    rep = {"meta": {"target_url": f"https://{domain}/", "crawled_at": "2026-10-01", "page_count": 1,
                    "target_url_count": 3, "screen_count": 1, "report_hash": "h1"},
           "screens": [{"page_id": "p1", "url": f"https://{domain}/login", "title": "サインイン",
                        "headings": ["認証"], "buttons": ["ログイン"], "is_canonical": True,
                        "forms": [{"fields": [{"name": "email", "label": "メール"}]}]}]}
    (d / "report.json").write_text(json.dumps(rep, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MODE", raising=False)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "output")
    appmod.app.config["TESTING"] = True
    from web.routes.doc_assure_sys01 import bp as sys01_bp
    if "doc_assure_sys01" not in appmod.app.blueprints:  # 本線が web/__init__.py で登録する
        appmod.app.register_blueprint(sys01_bp)
    from web.services.auth_store import get_auth_store
    boot = appmod.app.test_client()
    boot.post("/auth/setup", data={"tenant_name": "TenantA", "name": "Admin", "email": "admin@example.com",
                                   "password": PW, "password_confirm": PW}, headers=H)
    st = get_auth_store()
    ta = st.list_tenants()[0]
    tb = st.create_tenant("TenantB", "tenant-b")
    st.create_user(ta["id"], "alice@example.com", "Alice", PW)
    st.create_user(tb["id"], "eve@example.com", "Eve", PW)

    def login(email):
        c = appmod.app.test_client()
        c.post("/auth/login", data={"email": email, "password": PW}, headers=H)
        ts = (c.get("/api/auth/tenants", headers=H).get_json() or {}).get("tenants", [])
        if ts:
            c.post("/auth/tenant", data={"tenant_id": ts[0]["tenant_id"]}, headers=H)
        return c

    out = tmp_path / "output"
    _report(out / "tenants" / ta["slug"], "a.example.com")
    _report(out / "tenants" / "tenant-b", "b.example.com")
    return {"alice": login("alice@example.com"), "eve": login("eve@example.com")}


@pytest.fixture
def iid(env):
    r = env["alice"].post("/api/docverify/inspections", json={"name": "A", "goal": "g"}, headers=H)
    i = r.get_json()["inspection"]["id"]
    a = env["alice"].post(f"{BASE}/{i}/analyze", json={"documents": [DOC]}, headers=H)
    assert a.status_code == 200, a.get_data(as_text=True)
    return i


def test_sources_only_own_tenant(env, iid):
    r = env["alice"].get(f"{BASE}/{iid}/system01/sources", headers=H)
    assert [s["source_id"] for s in r.get_json()["sources"]] == ["a.example.com"]


def test_candidates_roundtrip(env, iid):
    r = env["alice"].get(f"{BASE}/{iid}/system01/candidates?source=a.example.com", headers=H)
    assert r.status_code == 200, r.get_data(as_text=True)
    j = r.get_json()
    assert j["confirmed"] is False
    states = {(c["requirement_id"], c["state"]) for c in j["candidates"]}
    reqs = {c["requirement_id"] for c in j["candidates"] if c["state"] == "ALIGNED_CANDIDATE"}
    assert reqs, j
    assert any(s == "NOT_OBSERVED" for _, s in states)  # 「監査ログ」は観測なし
    for c in j["candidates"]:
        assert c["source"] == "System01" and c["limitation"] and c["confirmed"] is False
    assert all("a.example.com" in c["provenance"]["source_id"] for c in j["candidates"])


def test_cross_tenant_source_is_404(env, iid):
    r = env["alice"].get(f"{BASE}/{iid}/system01/candidates?source=b.example.com", headers=H)
    assert r.status_code == 404
    assert env["alice"].get(f"{BASE}/{iid}/system01/candidates?source=nope.example.com", headers=H).status_code == 404
    assert env["alice"].get(f"{BASE}/{iid}/system01/candidates?source=..%2f..", headers=H).status_code == 404


def test_cross_tenant_inspection_is_404(env, iid):
    r = env["eve"].get(f"{BASE}/{iid}/system01/sources", headers=H)
    assert r.status_code == 404


def test_no_observation_is_not_observed_not_defect():
    class U(dict):
        pass
    units = [{"requirement_id": "FR-9", "kind": "functional", "raw_text": "「請求書」を出力できる",
              "fields": {}}]
    out = links_sys01.link(units, [], "s")
    assert [c["state"] for c in out] == ["NOT_OBSERVED"]
    assert "存在しない" in out[0]["limitation"] and out[0]["evidence_id"] == ""
    seen = [{"kind": "button", "label": "請求書", "url": "u", "observed": False, "limitation": "取得失敗"}]
    assert links_sys01.link(units, seen, "s")[0]["state"] == "NOT_OBSERVED"


def test_unmatched_observation_not_assigned():
    out = links_sys01.link([], [{"kind": "button", "label": "謎", "url": "u", "observed": True,
                                 "limitation": ""}], "s")
    assert out[0]["state"] == "UNMATCHED_OBSERVATION" and out[0]["requirement_id"] is None
