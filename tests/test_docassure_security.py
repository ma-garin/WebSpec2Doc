"""Document Assurance API のテナント分離（AC23）と役割の強制（AC22）を、認証オンの実リクエストで検証する。

- 認証オン（WEBSPEC2DOC_AUTH_MODE 未設定＋利用者あり）で 2 テナント・複数利用者を実際にログインさせる。
- 役割は検査の participants（名前→役割）で決まる。perm._context は差し替えず、本物の g.auth_user を使う。
- 認証オフ（AUTH_MODE=off）では perm.can が全操作を許可するため役割は強制されない（検証用の仕様）。
  よって役割のテストは認証オンでのみ成立し、skip/xfail にはしていない。
"""
from __future__ import annotations

import json
from pathlib import Path

import app as appmod
import pytest
from web import config
from web.services.docverify import perm

H = {"Host": "127.0.0.1"}
PW = "member-pass-123"
BASE = "/api/docassure/inspections"
DOC = {"id": "D1", "name": "要件", "type": "requirements",
       "text": "FR-1 システムは利用者がログインできること。\nFR-2 管理者は利用者を削除できる。"}


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MODE", raising=False)
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MOCK", raising=False)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    appmod.app.config["TESTING"] = True
    from web.services.auth_store import get_auth_store
    boot = appmod.app.test_client()
    boot.post("/auth/setup", data={"tenant_name": "TenantA", "name": "Admin", "email": "admin@example.com",
                                   "password": PW, "password_confirm": PW}, headers=H)
    store = get_auth_store()
    ta = store.list_tenants()[0]
    tb = store.create_tenant("TenantB", "tenant-b")
    for em, nm, t in (("alice@example.com", "Alice", ta), ("bob@example.com", "Bob", ta),
                      ("carol@example.com", "Carol", ta), ("dave@example.com", "Dave", ta),
                      ("eve@example.com", "Eve", tb)):
        store.create_user(t["id"], em, nm, PW)
    store.create_user(tb["id"], "adminb@example.com", "AdminB", PW)

    def login(email):
        c = appmod.app.test_client()
        c.post("/auth/login", data={"email": email, "password": PW}, headers=H)
        ts = (c.get("/api/auth/tenants", headers=H).get_json() or {}).get("tenants", [])
        if ts:
            c.post("/auth/tenant", data={"tenant_id": ts[0]["tenant_id"]}, headers=H)
        return c

    clients = {n: login(f"{n}@example.com") for n in ("alice", "bob", "carol", "dave", "eve")}
    return {"tmp": tmp_path, "slug": ta["slug"], "c": clients}


def _set_roles(env, iid: str, roles: dict[str, str]):
    p = env["tmp"] / "tenants" / env["slug"] / "docverify" / iid / "inspection.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    d["participants"] = [{"name": n, "role": r} for n, r in roles.items()]
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def analyzed(env):
    """テナント A（alice=議長）で検査を作り分析・判断まで済ませる。"""
    alice = env["c"]["alice"]
    r = alice.post("/api/docverify/inspections", json={"name": "A社", "goal": "g"}, headers=H)
    assert r.status_code == 201, r.get_data(as_text=True)
    iid = r.get_json()["inspection"]["id"]
    _set_roles(env, iid, {"Alice": "moderator", "Bob": "reviewer", "Carol": "author", "Dave": "approver"})
    a = alice.post(f"{BASE}/{iid}/analyze", json={"documents": [DOC]}, headers=H)
    assert a.status_code == 200, a.get_data(as_text=True)
    return iid


GETS = ["analyzers", "requirements", "findings", "conflicts", "scores", "readiness", "trace", "diff",
        "tests", "report.md", "report.csv", "report.json", "impact", "rewrite/R-1"]
SECRET = "FR-2 管理者は利用者を削除できる"


def test_cross_tenant_reads_are_404_and_leak_nothing(env, analyzed):
    """AC23: テナント B から A の検査 ID を直接叩いても 404/403 で、A の内容は一切返らない。"""
    eve = env["c"]["eve"]
    own = eve.get(f"{BASE}/{analyzed}/requirements", headers=H)  # 自テナントでの存在確認（疎通）
    assert own.status_code == 404
    for path in GETS:
        r = eve.get(f"{BASE}/{analyzed}/{path}", headers=H)
        assert r.status_code in (403, 404), f"{path}: {r.status_code}"
        assert SECRET not in r.get_data(as_text=True), path
        assert analyzed not in r.get_data(as_text=True) or r.status_code == 404


def test_cross_tenant_writes_are_rejected_and_do_not_change_a(env, analyzed):
    """AC23/(4): テナント B は A の検査へ analyze/review/decisions/alignment できず、A の決定も増えない。"""
    eve, alice = env["c"]["eve"], env["c"]["alice"]
    dec = {"target": "ISS-1", "decision": "accepted", "reason": "x"}
    for method, path, body in (("post", "analyze", {"documents": [DOC]}), ("post", "review", {}),
                               ("post", "decisions", dec), ("post", "alignment", {"observed": []})):
        r = getattr(eve, method)(f"{BASE}/{analyzed}/{path}", json=body, headers=H)
        assert r.status_code in (403, 404), f"{path}: {r.status_code}"
    from web.services.docassure import store
    sidecar = env["tmp"] / "tenants" / env["slug"] / "docverify" / analyzed / "assurance.json"
    assert json.loads(sidecar.read_text(encoding="utf-8")).get("decisions") == []
    assert not (env["tmp"] / "tenants" / "tenant-b" / "docverify" / analyzed).exists()
    assert alice.get(f"{BASE}/{analyzed}/readiness", headers=H).status_code == 200
    assert store  # import 確認


@pytest.mark.parametrize("bad", ["..%2Fx", "ABCDEF123456", "abc", "abcdef1234567", "zzzzzzzzzzzz", "../x"])
def test_invalid_inspection_id_is_404(env, bad):
    """(2) 不正な検査 ID（トラバーサル・大文字・長さ違い・16進以外）は 404。"""
    alice = env["c"]["alice"]
    for path in ("requirements", "report.md", "diff"):
        assert alice.get(f"{BASE}/{bad}/{path}", headers=H).status_code == 404
    assert alice.post(f"{BASE}/{bad}/analyze", json={"documents": [DOC]}, headers=H).status_code == 404
    assert alice.post(f"{BASE}/{bad}/decisions", json={"target": "a", "decision": "accepted"},
                      headers=H).status_code == 404


def test_import_doc_role_enforced_on_analyze(env, analyzed):
    """(3) analyze は import_doc（author/moderator）。reviewer と approver は 403、author と moderator は 200。"""
    body = {"documents": [DOC]}
    for who in ("bob", "dave"):
        r = env["c"][who].post(f"{BASE}/{analyzed}/analyze", json=body, headers=H)
        assert r.status_code == 403, who
        assert r.get_json()["code"] == "forbidden" and "権限" in r.get_json()["error"]
    for who in ("alice", "carol"):
        assert env["c"][who].post(f"{BASE}/{analyzed}/analyze", json=body, headers=H).status_code == 200, who


def test_finding_edit_role_enforced_on_decisions_and_review(env, analyzed):
    """(3) decisions/review は finding_edit（moderator/reviewer/scribe）。author・approver は 403、reviewer・moderator は 2xx 系。"""
    amb = {"documents": [{"id": "D1", "text": "- REQ-001 検索結果は適切に表示すること。\n"}]}
    fid = env["c"]["alice"].post(f"{BASE}/{analyzed}/analyze", json=amb, headers=H).get_json()["findings"][0]["finding_id"]
    dec = {"target": fid, "decision": "accepted", "reason": "確認済み"}
    for who in ("carol", "dave"):
        assert env["c"][who].post(f"{BASE}/{analyzed}/decisions", json=dec, headers=H).status_code == 403, who
        assert env["c"][who].post(f"{BASE}/{analyzed}/review", json={}, headers=H).status_code == 403, who
    for who in ("alice", "bob"):
        assert env["c"][who].post(f"{BASE}/{analyzed}/decisions", json=dec, headers=H).status_code == 201, who
        r = env["c"][who].post(f"{BASE}/{analyzed}/review", json={}, headers=H)
        assert r.status_code in (200, 409), (who, r.status_code)  # 409 は外部送信の同意待ち（権限は通過）


def test_non_participant_has_no_role(env, analyzed):
    """(3) 参加者でない利用者（eve を除く同テナントの別名）は役割なしで 403。"""
    _set_roles(env, analyzed, {"Alice": "moderator"})
    r = env["c"]["bob"].post(f"{BASE}/{analyzed}/decisions",
                             json={"target": "ISS-1", "decision": "accepted"}, headers=H)
    assert r.status_code == 403


def test_auth_off_does_not_enforce_roles(tmp_path, monkeypatch):
    """AUTH_MODE=off は perm.can が全許可（検証用の仕様）。役割テストが認証オンでしか成立しない根拠を固定する。"""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("FLASK_TESTING", "1")
    monkeypatch.setenv("WEBSPEC2DOC_ALLOW_LOCAL", "1")
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    appmod.app.config["TESTING"] = True
    c = appmod.app.test_client()
    iid = c.post("/api/docverify/inspections", json={"name": "x", "goal": "g"},
                 headers={"Origin": "http://localhost"}).get_json()["inspection"]["id"]
    assert perm.can("import_doc", set(), auth_on=False) is True
    assert perm.can("import_doc", {"reviewer"}, auth_on=True) is False
    r = c.post(f"{BASE}/{iid}/analyze", json={"documents": [DOC]}, headers={"Origin": "http://localhost"})
    assert r.status_code == 200


def test_analyze_size_limits(env, analyzed):
    """(5) 文書 21 件は 413、巨大本文は 413、長すぎる ID は 400。"""
    alice = env["c"]["alice"]
    many = [{"id": f"D{i}", "name": "n", "type": "other", "text": "FR-1 x"} for i in range(21)]
    assert alice.post(f"{BASE}/{analyzed}/analyze", json={"documents": many}, headers=H).status_code in (400, 413)
    huge = [{"id": "D1", "name": "n", "type": "other", "text": "あ" * 2_000_001}]
    assert alice.post(f"{BASE}/{analyzed}/analyze", json={"documents": huge}, headers=H).status_code in (400, 413)
    longid = [{"id": "x" * 65, "name": "n", "type": "other", "text": "FR-1 x"}]
    assert alice.post(f"{BASE}/{analyzed}/analyze", json={"documents": longid}, headers=H).status_code == 400


def test_responses_never_expose_source_texts(env, analyzed):
    """(6) analyze 応答・report.json・全 GET に source_texts と原文が含まれない（保存ファイルには残る）。"""
    alice = env["c"]["alice"]
    a = alice.post(f"{BASE}/{analyzed}/analyze", json={"documents": [DOC]}, headers=H)
    assert "source_texts" not in a.get_json()
    rj = alice.get(f"{BASE}/{analyzed}/report.json", headers=H)
    assert rj.status_code == 200 and "source_texts" not in rj.get_json()
    assert "source_texts" not in rj.get_data(as_text=True)
    for path in ("requirements", "findings", "scores", "readiness", "trace"):
        assert "source_texts" not in alice.get(f"{BASE}/{analyzed}/{path}", headers=H).get_data(as_text=True), path
    sidecar = env["tmp"] / "tenants" / env["slug"] / "docverify" / analyzed / "assurance.json"
    assert "source_texts" in json.loads(sidecar.read_text(encoding="utf-8"))
