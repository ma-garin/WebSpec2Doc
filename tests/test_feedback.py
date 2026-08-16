"""利用者フィードバック（POST/GET /api/feedback）のテスト。

検証する経路:
- 正常系: 送信 → JSONL に1行 → 管理者が一覧で読める
- 異常系: 種類が不正 / 内容が空 / 長すぎる → 400 で保存しない
- 書き込み失敗: 500 を返し、成功として扱わない
- 権限: 一覧は管理者のみ
- 身元: 送信者・テナントはサーバー側で補い、クライアント申告を信じない
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod

H = {"Host": "127.0.0.1"}

ADMIN_PW = "admin-pass-123"
MEMBER_PW = "member-pass-123"


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch):
    """認証DBとフィードバックの保存先をテストごとに隔離する。"""
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_DB", str(tmp_path / "auth.db"))
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MODE", raising=False)
    monkeypatch.delenv("WEBSPEC2DOC_AUTH_MOCK", raising=False)

    from web.routes import feedback as feedback_routes

    monkeypatch.setattr(feedback_routes, "INSTANCE_DIR", tmp_path / "instance")
    yield


def _client():
    return appmod.app.test_client()


def _store():
    from web.services.auth_store import get_auth_store

    return get_auth_store()


def _setup_admin(client) -> None:
    response = client.post(
        "/auth/setup",
        data={
            "tenant_name": "Tenant A",
            "name": "Admin",
            "email": "admin@example.com",
            "password": ADMIN_PW,
            "password_confirm": ADMIN_PW,
        },
        headers=H,
    )
    assert response.status_code == 302


def _work_as(client, email: str, password: str):
    """ログイン → テナント選択まで済ませ、API を叩ける状態にする。"""
    client.post("/auth/login", data={"email": email, "password": password}, headers=H)
    payload = client.get("/api/auth/tenants", headers=H).get_json() or {}
    tenants = payload.get("tenants", [])
    if tenants:
        client.post("/auth/tenant", data={"tenant_id": tenants[0]["tenant_id"]}, headers=H)
    return client


def _admin_client():
    _setup_admin(_client())
    return _work_as(_client(), "admin@example.com", ADMIN_PW)


def _saved_lines(tmp_path: Path) -> list[dict]:
    """テナントスコープを問わず、保存された全レコードを拾う。"""
    root = tmp_path / "instance"
    if not root.is_dir():
        return []
    lines: list[dict] = []
    for path in sorted(root.rglob("feedback.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                lines.append(json.loads(line))
    return lines


# ---------- 正常系 ----------


def test_submit_writes_one_line(tmp_path: Path) -> None:
    client = _admin_client()
    response = client.post(
        "/api/feedback",
        json={"category": "bug", "message": "保存ボタンが効かない", "view": "ホーム"},
        headers=H,
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True

    saved = _saved_lines(tmp_path)
    assert len(saved) == 1
    assert saved[0]["category"] == "bug"
    assert saved[0]["message"] == "保存ボタンが効かない"
    assert saved[0]["view"] == "ホーム"
    assert saved[0]["user_email"] == "admin@example.com"
    assert saved[0]["tenant_id"]  # テナントが記録される


def test_admin_can_list_newest_first() -> None:
    client = _admin_client()
    for text in ("1件目", "2件目"):
        client.post("/api/feedback", json={"category": "request", "message": text}, headers=H)

    listed = client.get("/api/feedback", headers=H)
    assert listed.status_code == 200
    messages = [item["message"] for item in listed.get_json()["feedback"]]
    assert messages == ["2件目", "1件目"]


def test_identity_is_taken_from_session_not_payload(tmp_path: Path) -> None:
    """クライアントが名乗った送信者を信じない。"""
    client = _admin_client()
    client.post(
        "/api/feedback",
        json={
            "category": "other",
            "message": "なりすまし",
            "user_email": "someone-else@example.com",
            "tenant_id": "forged-tenant",
        },
        headers=H,
    )
    saved = _saved_lines(tmp_path)[0]
    assert saved["user_email"] == "admin@example.com"
    assert saved["tenant_id"] != "forged-tenant"


# ---------- 異常系 ----------


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"category": "unknown", "message": "x"}, "invalid_category"),
        ({"category": "", "message": "x"}, "invalid_category"),
        ({"category": "bug", "message": ""}, "empty_message"),
        ({"category": "bug", "message": "   "}, "empty_message"),
        ({"category": "bug", "message": "あ" * 4001}, "message_too_long"),
    ],
)
def test_invalid_input_is_rejected_and_not_saved(
    payload: dict, code: str, tmp_path: Path
) -> None:
    client = _admin_client()
    response = client.post("/api/feedback", json=payload, headers=H)
    assert response.status_code == 400
    assert response.get_json()["code"] == code
    assert _saved_lines(tmp_path) == []


def test_write_failure_is_reported_as_error(monkeypatch) -> None:
    """保存できなかったものを成功として返さない。"""
    client = _admin_client()

    from web.routes import feedback as feedback_routes

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(feedback_routes, "append_feedback", _boom)
    response = client.post("/api/feedback", json={"category": "bug", "message": "x"}, headers=H)
    assert response.status_code == 500
    assert response.get_json()["code"] == "write_failed"


def test_member_cannot_list_feedback() -> None:
    _setup_admin(_client())
    store = _store()
    tenant_id = store.list_tenants()[0]["id"]
    store.create_user(tenant_id, "member@example.com", "Member", MEMBER_PW)
    member = _work_as(_client(), "member@example.com", MEMBER_PW)

    # 送るのは誰でもできるが、読むのは管理者だけ
    assert (
        member.post("/api/feedback", json={"category": "bug", "message": "x"}, headers=H).status_code
        == 200
    )
    assert member.get("/api/feedback", headers=H).status_code == 403


def test_broken_line_does_not_break_listing(tmp_path: Path) -> None:
    """1行の破損で全件が読めなくならない。"""
    client = _admin_client()
    client.post("/api/feedback", json={"category": "bug", "message": "正常な行"}, headers=H)

    path = next((tmp_path / "instance").rglob("feedback.jsonl"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{壊れたJSON\n")

    listed = client.get("/api/feedback", headers=H).get_json()["feedback"]
    assert [item["message"] for item in listed] == ["正常な行"]
