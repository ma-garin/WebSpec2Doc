"""System 06 R4 を既存ルートにつないだ部分の受入基準（wire_R4 の 3-変更3・変更5・5）。

FR-06-149: 指摘・採否・承認の保存直後に操作記録が残る。
FR-06-006 / 142: 種別ありは入口基準未達なら取り込んでも個別レビューへ進まない。旧形式は従来どおり進む。
FR-06-140: 画面の新規作成（R4 の作成 API）で種別が入る。
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

import app as appmod
from web import config
from web.services.docverify import perm, process

ORIGIN = {"Origin": "http://localhost"}
DOC = "システムは、要件 1 を満たすこと。\nシステムは、要件 2 を満たすこと。\n".encode("utf-8")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("FLASK_TESTING", "1")
    monkeypatch.setenv("WEBSPEC2DOC_ALLOW_LOCAL", "1")
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def _create_legacy(client) -> str:
    r = client.post("/api/docverify/inspections", json={"name": "旧形式", "goal": "g"}, headers=ORIGIN)
    assert r.status_code == 201
    return r.get_json()["inspection"]["id"]


def _create_r4(client, rtype="inspection") -> str:
    r = client.post("/api/docverify/r4/inspections", json={"name": "種別あり", "review_type": rtype}, headers=ORIGIN)
    assert r.status_code == 201
    return r.get_json()["id"]


def _upload(client, iid):
    return client.post(f"/api/docverify/inspections/{iid}/document", headers=ORIGIN,
                       data={"file": (io.BytesIO(DOC), "要件.txt")}, content_type="multipart/form-data")


def _audit_ops() -> list[tuple[str, str]]:
    with appmod.app.test_request_context():
        path = Path(perm._audit_path())
    if not path.is_file():
        return []
    rows = [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [(r["op"], r["target"]) for r in rows]


def test_finding_triage_approval_are_recorded(client):
    """Given 文書を取り込んだ検査 When 指摘追加・採否変更・承認を保存 Then 各操作が 1 行ずつ記録され検算が通る。"""
    iid = _create_legacy(client)
    insp = _upload(client, iid).get_json()["inspection"]
    pid = insp["passages"][0]["id"]
    r = client.post(f"/api/docverify/inspections/{iid}/findings", headers=ORIGIN,
                    json={"passage_id": pid, "severity": "major", "viewpoint": "正確性", "message": "曖昧"})
    assert r.status_code == 201
    fid = r.get_json()["inspection"]["findings"][-1]["id"]
    r = client.post(f"/api/docverify/inspections/{iid}/findings/{fid}", headers=ORIGIN, json={"status": "rejected"})
    assert r.status_code == 200
    r = client.patch(f"/api/docverify/inspections/{iid}", headers=ORIGIN,
                     json={"approval": {"approver": "承認者", "decided_at": "2026-10-15T10:00"}})
    assert r.status_code == 200
    ops = _audit_ops()
    assert ("finding", f"{iid}/{fid}") in ops
    assert ("finding_update", f"{iid}/{fid}") in ops
    assert ("approval", iid) in ops
    with appmod.app.test_request_context():
        assert perm.verify_log()["ok"] is True


def test_entry_criteria_block_auto_advance_and_legacy_advances(client):
    """Given 種別ありで必須役割が未割当 When 文書を取り込む Then 計画のまま・理由を返す。旧形式は個別レビューへ進む。"""
    iid = _create_r4(client, "inspection")
    r = _upload(client, iid)
    assert r.status_code == 200
    body = r.get_json()
    assert body["inspection"].get("phase", "plan") == "plan"
    assert body.get("entry_errors") and any("割り当てられていません" in e for e in body["entry_errors"])

    legacy = _create_legacy(client)
    r = _upload(client, legacy)
    assert r.status_code == 200
    assert r.get_json()["inspection"]["phase"] == "individual" and "entry_errors" not in r.get_json()


def test_new_review_from_screen_has_type(client):
    """Given 画面の新規作成（R4 の作成 API・既定の種別） When 作成 Then 種別が保存され作成者が参加者に入る。"""
    js = (Path(__file__).resolve().parents[1] / "static/js/docverify-global.js").read_text(encoding="utf-8")
    assert "'/api/docverify/r4/inspections'" in js and "review_type" in js
    iid = _create_r4(client, "informal")
    insp = client.get(f"/api/docverify/inspections/{iid}", headers=ORIGIN).get_json()["inspection"]
    info = process.type_info(insp)
    assert info["legacy"] is False and info["type"] == "informal"
    # 非公式レビューは作成者が必須。作った人を作成者として入れる（議長にすると取り込み後に計画で止まる）
    assert [p["role"] for p in insp["participants"]] == ["author"]
