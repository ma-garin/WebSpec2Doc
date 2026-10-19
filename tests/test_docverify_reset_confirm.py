"""System 06 トレーサビリティ「やり直す」の権限と操作記録（C-P0-1）。確認行は画面側、ここは確認なしの API 直叩きでも守られることを見る。"""
from __future__ import annotations

import json
from pathlib import Path

import app as appmod
import pytest
from web import config
from web.services.docverify import perm

ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("FLASK_TESTING", "1")
    monkeypatch.setenv("WEBSPEC2DOC_ALLOW_LOCAL", "1")
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _create(client) -> str:
    r = client.post("/api/docverify/inspections", json={"name": "やり直し", "goal": "g"}, headers=ORIGIN)
    assert r.status_code == 201
    return r.get_json()["inspection"]["id"]


def _audit_rows() -> list[dict]:
    with appmod.app.test_request_context():
        path = Path(perm._audit_path())
    if not path.is_file():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _reset(client, iid, to=1):
    return client.post(f"/api/docverify/inspections/{iid}/tier/reset", json={"to": to}, headers=ORIGIN)


def test_reset_forbidden_for_non_editor_when_auth_on(client, monkeypatch):
    """Given 認証オンで検査の議長でも管理者でもない利用者 When 確認なしで reset を直叩き Then 403・利用者向け文言・記録なし。"""
    iid = _create(client)
    monkeypatch.setattr(perm, "_context", lambda: ("他人", False, True))
    r = _reset(client, iid)
    assert r.status_code == 403
    assert "権限" in r.get_json()["error"]
    assert not [x for x in _audit_rows() if x["op"] == "tier_reset"]


def test_reset_records_actor_for_moderator(client, monkeypatch):
    """Given 認証オンで検査の議長 When reset Then 200・操作者と戻り先が操作記録に残り、検算が通る。"""
    iid = _create(client)
    monkeypatch.setattr(perm, "_context", lambda: ("ゲスト", False, True))
    r = _reset(client, iid, 1)
    assert r.status_code == 200
    rows = [x for x in _audit_rows() if x["op"] == "tier_reset"]
    assert len(rows) == 1 and rows[0]["actor"] == "ゲスト" and rows[0]["target"] == iid
    assert rows[0]["detail"]["to"] == 1
    with appmod.app.test_request_context():
        assert perm.verify_log()["ok"] is True


def test_reset_allowed_for_tenant_admin_and_bad_target_not_recorded(client, monkeypatch):
    """Given 認証オンのテナント管理者 When reset Then 200。不正な戻り先は 400 で記録しない。"""
    iid = _create(client)
    monkeypatch.setattr(perm, "_context", lambda: ("管理者", True, True))
    assert _reset(client, iid, 2).status_code == 200
    assert _reset(client, iid, 9).status_code == 400
    assert len([x for x in _audit_rows() if x["op"] == "tier_reset"]) == 1
