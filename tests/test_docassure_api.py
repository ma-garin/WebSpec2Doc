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


def _analyzed_fid(client, iid):
    r = client.post(f"/api/docassure/inspections/{iid}/analyze", headers=ORIGIN,
                    json={"documents": [{"id": "D1", "text": TEXT}]}).get_json()
    return r["findings"][0]["finding_id"]


def test_decision_validation_and_waiver_needs_expiry(client):
    iid = _iid(client)
    fid = _analyzed_fid(client, iid)
    base = f"/api/docassure/inspections/{iid}/decisions"
    # 存在しない対象への判断は記録しない
    assert client.post(base, headers=ORIGIN, json={"decision": "accepted", "target": "NO-SUCH"}).status_code == 404
    assert client.post(base, headers=ORIGIN, json={"decision": "x", "target": "a"}).status_code == 400
    assert client.post(base, headers=ORIGIN, json={"decision": "accepted"}).status_code == 400
    assert client.post(base, headers=ORIGIN, json={"decision": "waived", "target": fid}).status_code == 400
    ok = client.post(base, headers=ORIGIN, json={"decision": "waived", "target": fid, "reason": "r", "expiry": "2027-01-01"})
    assert ok.status_code == 201 and ok.get_json()["decision"]["source"] == "human"


def test_decisions_survive_reanalyze_and_legacy_inspection_untouched(client):
    iid = _iid(client)
    fid = _analyzed_fid(client, iid)
    before = client.get(f"/api/docverify/inspections/{iid}").get_json()
    client.post(f"/api/docassure/inspections/{iid}/decisions", headers=ORIGIN, json={"decision": "accepted", "target": fid})
    client.post(f"/api/docassure/inspections/{iid}/analyze", headers=ORIGIN, json={"documents": [{"text": TEXT}]})
    after = client.get(f"/api/docverify/inspections/{iid}").get_json()
    assert before["inspection"]["findings"] == after["inspection"]["findings"]
    from web.services.docassure import store
    assert [d["target"] for d in store.decisions(iid)] == [fid]


def test_report_formats_and_csv_injection_guard(client):
    iid = _iid(client)
    client.post(f"/api/docassure/inspections/{iid}/analyze", headers=ORIGIN,
                json={"documents": [{"id": "D1", "text": "- REQ-001 =cmd|calc 適切に表示すること。\n"}]})
    md = client.get(f"/api/docassure/inspections/{iid}/report.md")
    assert md.status_code == 200 and "Document Assurance Report" in md.get_data(as_text=True)
    csvr = client.get(f"/api/docassure/inspections/{iid}/report.csv").get_data(as_text=True)
    assert all(not ln.split(",")[0].startswith("=") for ln in csvr.splitlines())
    assert client.get(f"/api/docassure/inspections/{iid}/report.json").status_code == 200
    assert client.get(f"/api/docassure/inspections/{iid}/report.exe").status_code == 400


def test_review_requires_consent_for_openai_and_ignores_client_text(client, monkeypatch):
    from web.services.docassure import review_board
    from web.services.docverify import llm_settings
    iid = _iid(client)
    client.post(f"/api/docassure/inspections/{iid}/analyze", headers=ORIGIN,
                json={"documents": [{"id": "D1", "text": "- REQ-001 検索は適切に表示すること。\n"}]})
    monkeypatch.setattr(llm_settings, "load", lambda: {"destination": "openai"})
    monkeypatch.setattr(llm_settings, "client_for", lambda cfg: object())
    seen = {}
    monkeypatch.setattr(review_board, "run", lambda units, docs, c, **k: seen.update(docs=docs) or {"mode": "OK", "findings": []})
    r = client.post(f"/api/docassure/inspections/{iid}/review", headers=ORIGIN, json={})
    assert r.status_code == 409 and r.get_json()["code"] == "consent_required"
    ok = client.post(f"/api/docassure/inspections/{iid}/review", headers=ORIGIN,
                     json={"confirm_send": True, "documents": [{"id": "D1", "text": "偽の本文"}]})
    assert ok.status_code == 200
    assert "偽の本文" not in str(seen["docs"]) and "適切に" in str(seen["docs"])


def test_source_texts_not_exposed(client):
    iid = _iid(client)
    r = client.post(f"/api/docassure/inspections/{iid}/analyze", headers=ORIGIN,
                    json={"documents": [{"id": "D1", "text": "- REQ-001 秘密の本文 すること。\n"}]})
    assert "source_texts" not in r.get_json()
    assert "source_texts" not in client.get(f"/api/docassure/inspections/{iid}/report.json").get_data(as_text=True)


def test_decision_keeps_policy_findings_and_does_not_reanalyze(client, monkeypatch):
    """B-1: 判断を 1 件記録しても、組織ポリシーで出た指摘など判断対象以外の指摘は変わらない。M-5: 再分析しない。"""
    iid = _iid(client)
    client.put(f"/api/docassure/inspections/{iid}/policy", headers=ORIGIN, json={"ambiguous_terms": ["ウルトラ迅速"]})
    r = client.post(f"/api/docassure/inspections/{iid}/analyze", headers=ORIGIN,
                    json={"documents": [{"id": "D1", "text": "- REQ-001 ウルトラ迅速に処理すること。\n- REQ-002 結果は適切に表示すること。\n"},
                                        {"id": "D2", "text": "- REQ-001 処理画面で処理する。\n"}]}).get_json()
    before = {f["finding_id"] for f in r["findings"]}
    assert len(before) >= 2
    from web.services.docassure import pipeline
    monkeypatch.setattr(pipeline, "analyze", lambda *a, **k: (_ for _ in ()).throw(AssertionError("再分析した")))
    target = sorted(before)[0]
    ok = client.post(f"/api/docassure/inspections/{iid}/decisions", headers=ORIGIN,
                     json={"decision": "rejected", "target": target, "reason": "誤検出"})
    assert ok.status_code == 201
    after = client.get(f"/api/docassure/inspections/{iid}/issues").get_json()["findings"]
    assert {f["finding_id"] for f in after} == before
    st = {f["finding_id"]: f["status"] for f in after}
    assert st[target] == "REJECTED" and all(v == "CANDIDATE" for k, v in st.items() if k != target)
