"""共通 I/F v1（リスク・判断・承認・取消・証跡）の受入テスト。契約 A2 §3.2・§4.3。"""

from __future__ import annotations

import json

import pytest
from flask import g, request

from web import config, create_app
from web.routes import common_decisions_api

CID = "cs_0123456789ab"
TARGET = {"type": "docverify.inspection", "tenant": "_none", "id": "a1b2c3d4e5f6", "basis": "document"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    app = create_app()
    app.config["TESTING"] = True
    if "common_decisions_api" not in app.blueprints:
        app.register_blueprint(common_decisions_api.bp)

    @app.before_request
    def _as_user():  # 認証済み主体の代わり（ヘッダで切替。ゲストはヘッダ無し）
        uid = request.headers.get("X-Test-User")
        if uid:
            g.auth_user = {"id": uid, "username": uid}

    cases = tmp_path / "common" / "_none" / "cases"
    cases.mkdir(parents=True)
    (cases / f"{CID}.json").write_text(json.dumps({"id": CID}), encoding="utf-8")
    return app.test_client()


def _draft(client, user="u_a", passed=True, key="k1"):
    return client.post(f"/api/common/v1/cases/{CID}/decisions", json={
        "kind": "release", "conclusion": "conditional", "rationale": "Critical 2 件は次版で修正",
        "target": TARGET, "gate": {"passed": passed}},
        headers={"Idempotency-Key": key, **({"X-Test-User": user} if user else {})})


def test_draft_approve_revoke_is_recorded_in_chain(client):
    dc = _draft(client).get_json()["data"]
    assert dc["state"] == "drafted" and dc["drafted"]["by"]["user_id"] == "u_a"
    r = client.post(f"/api/common/v1/cases/{CID}/decisions/{dc['id']}/approve",
                    json={"rev": 1, "tv": "tv_0123456789ab", "reason": "条件付き受容"},
                    headers={"X-Test-User": "u_b"})
    assert r.status_code == 200 and r.get_json()["data"]["state"] == "approved"
    r = client.post(f"/api/common/v1/cases/{CID}/decisions/{dc['id']}/revoke",
                    json={"rev": 2, "reason": "前提が変わった"}, headers={"X-Test-User": "u_b"})
    assert r.get_json()["data"]["state"] == "revoked"
    ev = client.get(f"/api/common/v1/cases/{CID}/evidence").get_json()["data"]
    assert [row["op"] for row in ev["rows"]] == ["decision.draft", "decision.approve", "decision.revoke"]
    assert ev["rows"][1]["actor"]["user_id"] == "u_b" and ev["chain"]["ok"] is True


def test_approve_forbidden_for_self_guest_and_not_passed(client):
    dc = _draft(client).get_json()["data"]["id"]
    url = f"/api/common/v1/cases/{CID}/decisions/{dc}/approve"
    body = {"rev": 1, "tv": "tv_0123456789ab", "reason": "x"}
    assert client.post(url, json=body, headers={"X-Test-User": "u_a"}).status_code == 403
    assert client.post(url, json=body).status_code == 403
    failed = _draft(client, passed=False, key="k2").get_json()["data"]["id"]
    r = client.post(f"/api/common/v1/cases/{CID}/decisions/{failed}/approve", json=body,
                    headers={"X-Test-User": "u_b"})
    assert r.status_code == 403 and r.get_json()["error"]["code"] == "forbidden"


def test_stale_rev_conflict_and_unknown_case(client):
    dc = _draft(client).get_json()["data"]["id"]
    r = client.post(f"/api/common/v1/cases/{CID}/decisions/{dc}/approve",
                    json={"rev": 9, "tv": "tv_0123456789ab", "reason": "x"}, headers={"X-Test-User": "u_b"})
    assert r.status_code == 409 and r.get_json()["error"]["detail"]["actual_rev"] == 1
    assert client.get("/api/common/v1/cases/cs_ffffffffffff/decisions").status_code == 404


def test_risk_create_is_idempotent_and_rejects_score(client):
    body = {"title": "決済の二重計上", "cause": "再送", "impact": "過請求", "condition": "通信断",
            "mitigation": "冪等キー", "severity": "critical", "priority": "high", "basis": "document",
            "evidence_needed": ["再送試験"], "sources": [TARGET], "tests": []}
    url = f"/api/common/v1/cases/{CID}/risks"
    a = client.post(url, json=body, headers={"Idempotency-Key": "r1"}).get_json()["data"]
    b = client.post(url, json=body, headers={"Idempotency-Key": "r1"}).get_json()["data"]
    assert a["id"] == b["id"] and len(client.get(url).get_json()["data"]) == 1
    assert client.post(url, json={**body, "score": 9}, headers={"Idempotency-Key": "r2"}).status_code == 400
    r = client.patch(f"{url}/{a['id']}", json={"rev": 5, "priority": "low"})
    assert r.status_code == 409
