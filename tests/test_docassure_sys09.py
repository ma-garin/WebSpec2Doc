"""System06 → System09: 閾値変更の差分が影響分析に入り、候補が返る。未評価・テナント境界・前版なし。"""
import pytest

import app as appmod
from web import config
from web.routes import doc_assure_sys09
from web.services.impact import db
from web.services.impact.repo import documents, systems

ORIGIN = {"Origin": "http://localhost"}
V1 = "- REQ-001 検索結果は5秒以内に表示すること。\n- REQ-002 ログイン画面を表示すること。\n"
V2 = "- REQ-001 検索結果は3秒以内に表示すること。\n- REQ-002 ログイン画面を表示すること。\n"
DESIGN = ("検索結果の表示時間\n検索結果は5秒以内に画面へ表示する。処理は search_service.py が担当し、"
          "/api/search を呼び出す。\n".encode())
TESTS = "検索結果の表示は5秒以内であることを確認する。\n".encode()
BASE = "/api/docassure/inspections"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("FLASK_TESTING", "1")
    monkeypatch.setenv("WEBSPEC2DOC_ALLOW_LOCAL", "1")
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    app = appmod.app
    app.config["TESTING"] = True
    if "doc_assure_sys09" not in app.blueprints:
        app._got_first_request = False  # 本線が登録するまでの間、テスト側で登録する
        app.register_blueprint(doc_assure_sys09.bp)
    return app.test_client()


def _iid(c):
    return c.post("/api/docverify/inspections", json={"name": "t", "goal": "g"}, headers=ORIGIN).get_json()["inspection"]["id"]


def _analyze(c, iid, text):
    r = c.post(f"{BASE}/{iid}/analyze", headers=ORIGIN, json={"documents": [{"id": "D1", "text": text}]})
    assert r.status_code == 200, r.get_json()


def _system(tmp_path, docs=True):
    conn = db.connect()
    try:
        sid = systems.create(conn, "検索システム", "", "local")["id"]
        if docs:
            documents.add(conn, sid, "画面設計書.txt", DESIGN, "local", tmp_path)
            documents.add(conn, sid, "テストケース.txt", TESTS, "local", tmp_path)
        return sid
    finally:
        conn.close()


def _post(c, iid, sid=None):
    return c.post(f"{BASE}/{iid}/system09/analyze", headers=ORIGIN, json={"system_id": sid} if sid else {})


def test_threshold_change_returns_affected_candidates(client, tmp_path):
    sid = _system(tmp_path)
    iid = _iid(client)
    _analyze(client, iid, V1)
    _analyze(client, iid, V2)
    r = _post(client, iid, sid)
    assert r.status_code == 200, r.get_json()
    out = r.get_json()
    assert out["status"] == "CANDIDATES" and out["candidates_only"] is True
    aff = out["affected"]
    assert any(d["document"] == "画面設計書.txt" for d in aff["documents"])
    assert aff["documents"][0]["items"][0]["evidence"]          # 根拠・出所を保持
    assert any(m["module"] == "search_service.py" for m in aff["modules"])
    assert any(x["route"] == "/api/search" for x in aff["routes"])
    assert aff["tests"]
    got = client.get(f"{BASE}/{iid}/system09/impact").get_json()
    assert got["cr_code"] == out["cr_code"]
    assert client.post(f"{BASE}/{iid}/system09/analyze", headers=ORIGIN, json={}).status_code == 200  # system を記憶


def test_no_previous_is_404(client, tmp_path):
    iid = _iid(client)
    _analyze(client, iid, V1)
    r = _post(client, iid, _system(tmp_path))
    assert r.status_code == 404 and r.get_json()["code"] == "no_previous"
    assert client.get(f"{BASE}/{iid}/system09/impact").status_code == 404


def test_empty_corpus_is_not_evaluated_not_no_impact(client, tmp_path):
    sid = _system(tmp_path, docs=False)
    iid = _iid(client)
    _analyze(client, iid, V1)
    _analyze(client, iid, V2)
    out = _post(client, iid, sid).get_json()
    assert out["status"] == "NOT_EVALUATED" and out["affected"]["documents"] == []
    assert any(n["status"] == "NOT_EVALUATED" for n in out["not_evaluated"])
    assert "影響なし" not in str(out["status"])


def test_unrelated_corpus_is_no_finding(client, tmp_path):
    conn = db.connect()
    sid = systems.create(conn, "別系", "", "local")["id"]
    documents.add(conn, sid, "経理設計書.txt", "月次の仕訳を締める処理を行う。\n".encode(), "local", tmp_path)
    conn.close()
    iid = _iid(client)
    _analyze(client, iid, V1)
    _analyze(client, iid, V2)
    out = _post(client, iid, sid).get_json()
    assert out["status"] in ("NO_FINDING", "CANDIDATES")
    if out["status"] == "NO_FINDING":
        assert any(n["status"] == "NO_FINDING" for n in out["not_evaluated"])


def test_missing_system_and_unknown_system(client, tmp_path):
    iid = _iid(client)
    _analyze(client, iid, V1)
    _analyze(client, iid, V2)
    assert _post(client, iid).get_json()["code"] == "no_system"
    assert _post(client, iid, "ffffffffffff").status_code == 404


def test_cross_tenant_rejected(client, tmp_path, monkeypatch):
    from web import tenancy
    cur = {"slug": "ta"}
    monkeypatch.setattr(tenancy, "current_tenant", lambda: {"slug": cur["slug"]})
    sid = _system(tmp_path)
    iid = _iid(client)
    _analyze(client, iid, V1)
    _analyze(client, iid, V2)
    assert _post(client, iid, sid).status_code == 200
    cur["slug"] = "tb"
    assert client.get(f"{BASE}/{iid}/system09/impact").status_code == 404
    assert _post(client, iid, sid).status_code == 404
    assert not (tmp_path / "tenants" / "tb" / "docverify" / iid).exists()
