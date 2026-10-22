"""System06 ⇔ System02 往復: 登録・冪等・実行結果の反映・未実行は None・テナント境界。"""
import pytest
from flask import Flask, g

from web import config
from web.routes import doc_assure_sys02
from web.services import ta2_store
from web.services.docassure import coverage, integrations, links_sys02, pipeline, store
from web.services.docverify import store as dv

TEXT = "- REQ-001 検索結果は適切に表示すること。\n- REQ-002 管理者のみ編集できる。不正な入力は拒否する。\n"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "out")
    app = Flask(__name__)
    app.testing = True
    state = {"slug": "acme"}

    @app.before_request
    def _t():
        g.tenant = {"slug": state["slug"]}

    with app.test_request_context("/"):
        g.tenant = {"slug": state["slug"]}
        yield app, state


def _setup():
    iid = dv.save(dv.new("t"))["id"]
    res = pipeline.analyze([{"id": "D1", "name": "要件", "type": "other", "text": TEXT}])
    store.save(iid, res)
    cands = [c for c in integrations.test_candidates(res["requirements"]) if c.get("candidate_id")]
    return iid, cands


def test_roundtrip_idempotent_and_truth(env):
    iid, cands = _setup()
    assert cands
    r1 = links_sys02.push_candidates(iid, cands)
    assert len(r1["created"]) == len(cands)
    r2 = links_sys02.push_candidates(iid, cands)
    assert not r2["created"] and len(r2["already_registered"]) == len(cands)
    tests = ta2_store.load(links_sys02.domain_of(iid))["tests"]
    assert len(tests) == len(cands)
    assert all(t["state"] == "GENERATED" and t["execution"] == "NOT_EXECUTED"
               and t["verification"] == "NOT_VERIFIED" for t in tests)
    rid = cands[0]["requirement_id"]
    st = links_sys02.pull_status(iid, [rid])[rid]
    assert st["designed"] and st["generated"]
    assert st["executed"] is None and st["result"] == "NONE" and st["verified"] is None
    ex = links_sys02.as_execution(iid)
    assert all(v["status"] == "NOT_EXECUTED" for v in ex.values())


def test_result_reflected_and_coverage(env):
    iid, cands = _setup()
    links_sys02.push_candidates(iid, cands)
    dom = links_sys02.domain_of(iid)
    ids = {t["case_id"]: t["id"] for t in ta2_store.load(dom)["tests"]}
    rid = cands[0]["requirement_id"]
    mine = [c for c in cands if c["requirement_id"] == rid]
    ta2_store.apply_run_result(dom, {"cases": {c["candidate_id"]: {"status": "passed", "duration_ms": 5}
                                               for c in mine}})
    st = links_sys02.pull_status(iid, [rid])[rid]
    assert st["executed"] is True and st["result"] == "PASSED" and st["verified"] is None
    ta2_store.apply_run_result(dom, {"cases": {mine[0]["candidate_id"]: {"status": "failed", "error": "x"}}})
    assert links_sys02.pull_status(iid, [rid])[rid]["result"] == "FAILED"
    graph_reqs = store.load(iid)["requirements"]
    assert graph_reqs and ids
    ex = links_sys02.as_execution(iid)
    assert any(v["status"] == "PASSED" for v in ex.values()) or any(v["status"] == "FAILED" for v in ex.values())
    assert coverage.compute({"nodes": [], "edges": []}, ex)["execution"]["total"] == 0


def test_no_candidate_for_clarification(env):
    iid, _ = _setup()
    r = links_sys02.push_candidates(iid, [{"candidate_id": None, "requirement_id": "R", "required_clarification": True}])
    assert not r["created"] and r["not_registered_requirements"] == ["R"]


def test_other_tenant_denied(env):
    app, state = env
    iid, cands = _setup()
    links_sys02.push_candidates(iid, cands)
    state["slug"] = "other"
    g.tenant = {"slug": "other"}
    with pytest.raises(KeyError):
        links_sys02.pull_status(iid)
    with pytest.raises(KeyError):
        links_sys02.push_candidates(iid, cands)


def test_blueprint_name():
    assert doc_assure_sys02.bp.name == "doc_assure_sys02"


def test_analyze_feeds_system02_results_into_coverage(tmp_path, monkeypatch):
    """System02 の実行結果が trace.coverage に反映される。未実行のテスト案は Executed に数えない。"""
    import app as appmod
    from web import config
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("FLASK_TESTING", "1")
    monkeypatch.setenv("WEBSPEC2DOC_ALLOW_LOCAL", "1")
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    c = appmod.app.test_client()
    h = {"Origin": "http://localhost"}
    iid = c.post("/api/docverify/inspections", json={"name": "t", "goal": "g"}, headers=h).get_json()["inspection"]["id"]
    docs = [{"id": "R", "text": "- REQ-001 ログインは5回失敗で30分ロックすること。\n"},
            {"id": "D", "text": "- REQ-001 ログイン画面で認証する。\n"}]
    c.post(f"/api/docassure/inspections/{iid}/analyze", headers=h, json={"documents": docs})
    c.post(f"/api/docassure/inspections/{iid}/system02/push", headers=h, json={})
    r = c.post(f"/api/docassure/inspections/{iid}/analyze", headers=h, json={"documents": docs}).get_json()
    cov = r["trace"]["coverage"]
    assert cov["test_designed"]["count"] >= 1          # テスト案は設計済みとして数える
    assert cov["execution"] is None or cov["execution"]["count"] == 0   # 実行していないものは実行済みにしない
