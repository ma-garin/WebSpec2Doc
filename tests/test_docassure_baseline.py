"""baseline・回帰・feedback・policy API。"""
import pytest

import app as appmod
from web import config
from web.services.docassure import baseline, regression, policy

ORIGIN = {"Origin": "http://localhost"}
V1 = "- REQ-001 検索結果は適切に表示すること。\n- REQ-002 ログイン失敗の場合はエラーを表示すること。\n"
V2 = "- REQ-001 検索結果は適切に表示すること。\n- REQ-002 ログイン画面を表示すること。\n"
V3 = "- REQ-001 検索結果を3秒以内に表示すること。\n- REQ-002 ログイン画面を表示すること。\n"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("FLASK_TESTING", "1")
    monkeypatch.setenv("WEBSPEC2DOC_ALLOW_LOCAL", "1")
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _iid(c):
    return c.post("/api/docverify/inspections", json={"name": "t", "goal": "g"}, headers=ORIGIN).get_json()["inspection"]["id"]


def _analyze(c, iid, text):
    r = c.post(f"/api/docassure/inspections/{iid}/analyze", headers=ORIGIN, json={"documents": [{"id": "D1", "text": text}]})
    assert r.status_code == 200, r.get_json()


def _u(prefix):
    return f"/api/docassure/inspections/{prefix}"


def test_regression_no_previous_404(client):
    iid = _iid(client)
    _analyze(client, iid, V1)
    r = client.get(_u(f"{iid}/regression"))
    assert r.status_code == 404 and r.get_json()["code"] == "no_previous"


def test_regression_flags_lost_condition_candidate(client):
    iid = _iid(client)
    _analyze(client, iid, V1)
    _analyze(client, iid, V2)
    r = client.get(_u(f"{iid}/regression"))
    assert r.status_code == 200
    cands = r.get_json()["missing_candidates"]
    assert cands and cands[0]["status"] == "CANDIDATE" and "エラー" in cands[0]["lost_terms"]


def _f(rule, req, fp, sev="medium"):
    return {"finding_id": f"{rule}:{req}:1", "rule_id": rule, "severity": sev, "title": "t", "requirement_id": req,
            "result": "FAIL", "location": {"snippet_hash": "h"}}


def test_compare_classification_new_existing_resolved_regressed():
    reqs = [{"requirement_id": "R1", "fingerprint": "fa"}, {"requirement_id": "R2", "fingerprint": "fb"}]
    r1 = {"requirements": reqs, "findings": [_f("AMBIG", "R1", "fa"), _f("TBD", "R2", "fb")]}
    base = {"findings": {k: baseline._slim(f) for k, f in baseline.keyed(r1).items()}, "resolved_keys": []}
    # R2 の指摘が解消、R1 は位置が動いても同一、R3 が新規
    r2 = {"requirements": reqs + [{"requirement_id": "R3", "fingerprint": "fc"}],
          "findings": [_f("AMBIG", "R1", "fa"), _f("AMBIG", "R3", "fc")]}
    c = baseline.compare(base, r2)
    assert c["counts"] == {"NEW": 1, "EXISTING": 1, "RESOLVED": 1, "REGRESSED": 0}
    # R2 の指摘が再発
    base2 = {"findings": {k: baseline._slim(f) for k, f in baseline.keyed(r2).items()},
             "resolved_keys": [k for k in baseline.keyed(r1) if k.startswith("TBD")]}
    r3 = {"requirements": reqs, "findings": [_f("AMBIG", "R1", "fa"), _f("TBD", "R2", "fb")]}
    assert baseline.compare(base2, r3)["counts"]["REGRESSED"] == 1


def test_regression_review_severity_and_trace():
    reqs = [{"requirement_id": "R1", "fingerprint": "fa"}]
    b = {"requirements": reqs, "findings": [_f("AMBIG", "R1", "fa", "low")], "scores": {"Traceability": {"value": 80}}}
    a = {"requirements": reqs, "findings": [_f("AMBIG", "R1", "fa", "high")], "scores": {"Traceability": {"value": 60}}}
    r = regression.review(b, a)
    assert r["severity_changed"][0]["after"] == "high" and r["trace_degradation"]["delta"] == -20


def test_baseline_api_roundtrip_resolved_then_regressed(client):
    iid = _iid(client)
    assert client.get(_u(f"{iid}/baseline/compare")).status_code in (404,)
    _analyze(client, iid, V1)
    assert client.get(_u(f"{iid}/baseline/compare")).get_json()["code"] == "no_baseline"
    assert client.post(_u(f"{iid}/baseline"), headers=ORIGIN).status_code == 201
    c = client.get(_u(f"{iid}/baseline/compare")).get_json()
    assert c["counts"]["NEW"] == 0 and c["counts"]["EXISTING"] >= 1
    _analyze(client, iid, V3)
    assert client.get(_u(f"{iid}/baseline/compare")).get_json()["counts"]["RESOLVED"] >= 1


def test_feedback_validation_and_stats(client):
    iid = _iid(client)
    assert client.post(_u(f"{iid}/feedback"), headers=ORIGIN, json={}).status_code == 404  # 未分析
    _analyze(client, iid, V1)
    fid = client.get(_u(f"{iid}/issues")).get_json()["findings"][0]["finding_id"]
    for body in ({"finding_id": fid, "kind": "bad"}, {"kind": "useful"}, {"finding_id": "x" * 300, "kind": "useful"}):
        assert client.post(_u(f"{iid}/feedback"), headers=ORIGIN, json=body).status_code == 400
    assert client.post(_u(f"{iid}/feedback"), headers=ORIGIN, json={"finding_id": "nope", "kind": "useful"}).status_code == 404
    assert client.post(_u(f"{iid}/feedback"), headers=ORIGIN, json={"finding_id": fid, "kind": "false_positive"}).status_code == 201
    s = client.get(_u(f"{iid}/feedback/stats")).get_json()
    assert s["rules"][fid.split(":")[0]]["dismiss_rate"] == 1.0 and s["issue_density"] > 0


def test_policy_put_get_and_validation(client):
    iid = _iid(client)
    assert client.get(_u(f"{iid}/policy")).get_json()["policy"] == {}
    assert client.put(_u(f"{iid}/policy"), headers=ORIGIN, json={"evil": ["a"]}).status_code == 400
    assert client.put(_u(f"{iid}/policy"), headers=ORIGIN, json={"ambiguous_terms": ["x" * 101]}).status_code == 400
    assert client.put(_u(f"{iid}/policy"), headers=ORIGIN, json={"ambiguous_terms": "a"}).status_code == 400
    ok = client.put(_u(f"{iid}/policy"), headers=ORIGIN, json={"ambiguous_terms": ["いい感じ"], "project_terms": ["顧客"]})
    assert ok.status_code == 200
    assert client.get(_u(f"{iid}/policy")).get_json()["policy"]["ambiguous_terms"] == ["いい感じ"]
    from web.services.docassure.rules import engine
    assert engine.load_pack("default", policy.as_pack_extra({"ambiguous_terms": ["いい感じ"]}))


def test_unknown_iid_404(client):
    assert client.get(_u("ffffffffffff/regression")).status_code == 404
    assert client.get(_u("ffffffffffff/policy")).status_code == 404


def test_saved_policy_is_applied_to_analysis(client):
    iid = _iid(client)
    doc = {"documents": [{"id": "D1", "text": "- REQ-001 ウルトラ迅速に処理すること。\n"}]}
    before = client.post(f"/api/docassure/inspections/{iid}/analyze", headers=ORIGIN, json=doc).get_json()
    r = client.put(f"/api/docassure/inspections/{iid}/policy", headers=ORIGIN, json={"ambiguous_terms": ["ウルトラ迅速"]})
    assert r.status_code == 200, r.get_json()
    after = client.post(f"/api/docassure/inspections/{iid}/analyze", headers=ORIGIN, json=doc).get_json()
    assert len(after["findings"]) > len(before["findings"])   # 組織固有語が検出される
