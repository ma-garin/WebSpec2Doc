"""System 06 トレーサビリティ API（web/routes/doc_verify_trace.py）と画面の読み込み対象の回帰テスト。"""
from __future__ import annotations

import io
import re

import app as appmod
import pytest
from web import config

ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setenv("FLASK_TESTING", "1")
    monkeypatch.setenv("WEBSPEC2DOC_ALLOW_LOCAL", "1")
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    return appmod.app.test_client()


def _create(client) -> str:
    r = client.post("/api/docverify/inspections", json={"name": "追跡", "goal": "確認"}, headers=ORIGIN)
    assert r.status_code == 201
    return r.get_json()["inspection"]["id"]


def test_state_of_new_inspection_and_unknown_id(client):
    iid = _create(client)
    r = client.get(f"/api/docverify/inspections/{iid}/tier")
    assert r.status_code == 200 and isinstance(r.get_json(), dict)
    assert client.get("/api/docverify/inspections/000000000000/tier").status_code == 404


def test_documents_require_file_and_reject_unknown_format(client):
    iid = _create(client)
    r = client.post(f"/api/docverify/inspections/{iid}/tier/documents", headers=ORIGIN, data={},
                    content_type="multipart/form-data")
    assert r.status_code == 400 and r.get_json()["error"]
    r = client.post(f"/api/docverify/inspections/{iid}/tier/documents", headers=ORIGIN,
                    data={"file": (io.BytesIO(b"x"), "a.exe")}, content_type="multipart/form-data")
    body = r.get_json()
    assert any(x["name"] == "a.exe" for x in body.get("rejected", [])) or r.status_code == 400


def test_md_document_is_registered(client):
    iid = _create(client)
    md = "# 要件\n\nREQ-001 システムは、利用者がログインできること。\n".encode()
    r = client.post(f"/api/docverify/inspections/{iid}/tier/documents", headers=ORIGIN,
                    data={"file": (io.BytesIO(md), "要件.md")}, content_type="multipart/form-data")
    assert r.status_code == 201, r.get_json()
    assert len(client.get(f"/api/docverify/inspections/{iid}/tier").get_json()["documents"]) == 1


def test_page_loads_no_generation_named_assets(client):
    """利用者が開く画面は、内部の世代名（r2〜r5・tier）を名前に持つ JS/CSS/部分テンプレートを読まない。"""
    html = client.get("/docverify").get_data(as_text=True)
    assets = re.findall(r'(?:src|href)="([^"]+\.(?:js|css))', html)
    assert any("docverify-trace.js" in a for a in assets) and any("docverify-process.js" in a for a in assets)
    assert not [a for a in assets if re.search(r"docverify-(?:r\d|tier)", a)]
    assert not re.search(r"(?<![A-Za-z0-9_-])(?:R[1-5]|tier-[1-3])(?![A-Za-z0-9])", re.sub(r"<[^>]+>", " ", html))


def test_r1_writes_follow_role_matrix_when_auth_is_on(client, monkeypatch):
    """R1 の更新系も役割×操作の表に従う（R4 の権限を迂回できない）。認証オフは従来どおり全許可。"""
    from web.services.docverify import perm
    iid = _create(client)
    monkeypatch.setattr(perm, "_context", lambda: ("部外者", False, True))
    r = client.patch(f"/api/docverify/inspections/{iid}", json={"phase": "closed"}, headers=ORIGIN)
    assert r.status_code == 403 and r.get_json()["code"] == "forbidden"
    assert client.patch(f"/api/docverify/inspections/{iid}", json={"approval": {"approver": "x"}},
                        headers=ORIGIN).status_code == 403
    assert client.post(f"/api/docverify/inspections/{iid}/findings/F1", json={"status": "verified"},
                       headers=ORIGIN).status_code == 403
    assert client.put("/api/docverify/settings", json={}, headers=ORIGIN).status_code == 403
    assert client.get("/api/docverify/settings").status_code == 200  # 読むのは可
    monkeypatch.setattr(perm, "_context", lambda: ("管理者", True, True))
    assert client.patch(f"/api/docverify/inspections/{iid}", json={"goal": "更新"}, headers=ORIGIN).status_code == 200
