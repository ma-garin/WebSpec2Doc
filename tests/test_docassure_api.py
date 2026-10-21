"""Document Assurance API: 分析→取得、判断の検証、存在しない検査、入力検証、旧データ互換。"""
import pytest

import app as appmod
from web import config

ORIGIN = {"Origin": "http://localhost"}
TEXT = "- REQ-001 検索結果は適切に表示すること。\n- REQ-002 TBD の項目は別途検討する。\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("FLASK_TESTING", "1")
    monkeypatch.setenv("WEBSPEC2DOC_ALLOW_LOCAL", "1")
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _iid(client):
    r = client.post("/api/docverify/inspections", json={"name": "t", "goal": "g"}, headers=ORIGIN)
    return r.get_json()["inspection"]["id"]


def test_analyze_then_get(client):
    iid = _iid(client)
    r = client.post(f"/api/docassure/inspections/{iid}/analyze", headers=ORIGIN,
                    json={"documents": [{"id": "D1", "name": "要件", "text": TEXT}]})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["counts"]["requirements"] >= 2
    for part in ("requirements", "issues", "conflicts", "scores", "readiness"):
        g = client.get(f"/api/docassure/inspections/{iid}/{part}")
        assert g.status_code == 200
    assert client.get(f"/api/docassure/inspections/{iid}/issues").get_json()["findings"]


def test_get_before_analyze_is_404_not_empty_ok(client):
    iid = _iid(client)
    assert client.get(f"/api/docassure/inspections/{iid}/scores").status_code == 404


def test_unknown_or_malformed_id_is_404(client):
    assert client.get("/api/docassure/inspections/ffffffffffff/scores").status_code == 404
    assert client.get("/api/docassure/inspections/..%2f..%2fx/scores").status_code == 404
    assert client.post("/api/docassure/inspections/ffffffffffff/analyze", headers=ORIGIN,
                       json={"documents": [{"text": "a"}]}).status_code == 404


def test_analyze_without_document_is_400(client):
    iid = _iid(client)
    r = client.post(f"/api/docassure/inspections/{iid}/analyze", headers=ORIGIN, json={})
    assert r.status_code == 400


def test_decision_validation_and_waiver_needs_expiry(client):
    iid = _iid(client)
    base = f"/api/docassure/inspections/{iid}/decisions"
    assert client.post(base, headers=ORIGIN, json={"decision": "x", "target": "a"}).status_code == 400
    assert client.post(base, headers=ORIGIN, json={"decision": "accepted"}).status_code == 400
    assert client.post(base, headers=ORIGIN, json={"decision": "waived", "target": "a"}).status_code == 400
    ok = client.post(base, headers=ORIGIN, json={"decision": "waived", "target": "a", "reason": "r", "expiry": "2027-01-01"})
    assert ok.status_code == 201 and ok.get_json()["decision"]["source"] == "human"


def test_decisions_survive_reanalyze_and_legacy_inspection_untouched(client):
    iid = _iid(client)
    before = client.get(f"/api/docverify/inspections/{iid}").get_json()
    client.post(f"/api/docassure/inspections/{iid}/decisions", headers=ORIGIN, json={"decision": "accepted", "target": "F1"})
    client.post(f"/api/docassure/inspections/{iid}/analyze", headers=ORIGIN, json={"documents": [{"text": TEXT}]})
    after = client.get(f"/api/docverify/inspections/{iid}").get_json()
    assert before["inspection"]["findings"] == after["inspection"]["findings"]
    from web.services.docassure import store
    assert [d["target"] for d in store.decisions(iid)] == ["F1"]
