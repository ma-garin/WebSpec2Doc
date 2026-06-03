"""/api/login/scrape・/api/login/submit ルートのテスト（subprocess をモック）"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.login as login_mod


def _client():
    return appmod.app.test_client()


# ---------- /api/login/scrape ----------


def test_scrape_returns_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    payload = json.dumps(
        {
            "ok": True,
            "fields": [
                {
                    "name": "username",
                    "field_type": "text",
                    "label": "ユーザーID",
                    "placeholder": "",
                    "required": True,
                    "element_id": "",
                }
            ],
            "current_url": "https://example.com/login",
            "error": "",
        }
    )
    proc = MagicMock()
    proc.stdout = payload
    proc.returncode = 0
    with patch.object(login_mod.subprocess, "run", return_value=proc):
        data = (
            _client()
            .post(
                "/api/login/scrape",
                data={"url": "https://example.com/login", "domain": "example.com"},
            )
            .get_json()
        )
    assert data["ok"] is True
    assert len(data["fields"]) == 1
    assert data["fields"][0]["name"] == "username"


def test_scrape_rejects_missing_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    res = _client().post("/api/login/scrape", data={"domain": "example.com"})
    assert res.status_code == 400


def test_scrape_rejects_invalid_domain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    res = _client().post(
        "/api/login/scrape", data={"url": "https://x.com/login", "domain": "../etc"}
    )
    assert res.status_code == 400


def test_scrape_timeout_returns_504(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    import subprocess

    with patch.object(
        login_mod.subprocess, "run", side_effect=subprocess.TimeoutExpired("cmd", 30)
    ):
        res = _client().post(
            "/api/login/scrape", data={"url": "https://x.com/login", "domain": "x.com"}
        )
    assert res.status_code == 504


# ---------- /api/login/submit ----------


def test_submit_success_saves_session(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    auth = tmp_path / "example.com" / "auth.json"
    auth.parent.mkdir(parents=True, exist_ok=True)
    auth.write_text("{}", encoding="utf-8")
    payload = json.dumps(
        {
            "success": True,
            "needs_more_fields": False,
            "fields": [],
            "current_url": "https://example.com/",
            "error": "",
        }
    )
    proc = MagicMock()
    proc.stdout = payload
    proc.returncode = 0
    with patch.object(login_mod.subprocess, "run", return_value=proc):
        data = (
            _client()
            .post(
                "/api/login/submit",
                data={
                    "domain": "example.com",
                    "current_url": "https://example.com/login",
                    "fields_json": '{"username": "u", "password": "p"}',
                },
            )
            .get_json()
        )
    assert data["success"] is True
    assert "auth_path" in data


def test_submit_mfa_returns_new_fields(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    payload = json.dumps(
        {
            "success": False,
            "needs_more_fields": True,
            "fields": [
                {
                    "name": "otp",
                    "field_type": "text",
                    "label": "OTP",
                    "placeholder": "",
                    "required": True,
                    "element_id": "",
                }
            ],
            "current_url": "https://example.com/mfa",
            "error": "",
        }
    )
    proc = MagicMock()
    proc.stdout = payload
    proc.returncode = 0
    with patch.object(login_mod.subprocess, "run", return_value=proc):
        data = (
            _client()
            .post(
                "/api/login/submit",
                data={
                    "domain": "example.com",
                    "current_url": "https://example.com/login",
                    "fields_json": '{"username": "u", "password": "p"}',
                },
            )
            .get_json()
        )
    assert data["needs_more_fields"] is True
    assert data["fields"][0]["name"] == "otp"


def test_submit_rejects_missing_domain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    res = _client().post(
        "/api/login/submit", data={"current_url": "https://x.com/login", "fields_json": "{}"}
    )
    assert res.status_code == 400


def test_submit_rejects_invalid_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    res = _client().post(
        "/api/login/submit",
        data={"domain": "x.com", "current_url": "https://x.com/login", "fields_json": "not-json"},
    )
    assert res.status_code == 400


def test_simple_login_success(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    payload = json.dumps(
        {
            "success": True,
            "needs_more_fields": False,
            "fields": [],
            "current_url": "https://x.com/",
            "error": "",
        }
    )
    proc = MagicMock()
    proc.stdout = payload
    proc.returncode = 0
    with patch.object(login_mod.subprocess, "run", return_value=proc):
        data = (
            _client()
            .post(
                "/api/login/simple",
                data={
                    "domain": "x.com",
                    "login_url": "https://x.com/login",
                    "username": "user",
                    "password": "pass",
                },
            )
            .get_json()
        )
    assert data["success"] is True
    assert "auth_path" in data


def test_simple_login_credentials_via_stdin(tmp_path: Path, monkeypatch) -> None:
    """パスワードはstdin経由で渡され、コマンドライン引数に含まれない。"""
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    captured = {}

    def fake_run(cmd, input=None, **kwargs):
        captured["input"] = input
        captured["cmd"] = cmd
        return MagicMock(
            stdout=json.dumps(
                {
                    "success": True,
                    "needs_more_fields": False,
                    "fields": [],
                    "current_url": "",
                    "error": "",
                }
            )
        )

    with patch.object(login_mod.subprocess, "run", side_effect=fake_run):
        _client().post(
            "/api/login/simple",
            data={
                "domain": "x.com",
                "login_url": "https://x.com/login",
                "username": "user",
                "password": "secret",
            },
        )
    assert "secret" in captured["input"]
    assert not any("secret" in str(a) for a in captured["cmd"])


def test_simple_login_rejects_missing_login_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    res = _client().post(
        "/api/login/simple", data={"domain": "x.com", "username": "u", "password": "p"}
    )
    assert res.status_code == 400


def test_submit_fields_passed_via_stdin(tmp_path: Path, monkeypatch) -> None:
    """パスワード等のフィールド値はstdin経由で渡され、コマンドライン引数に含まれない。"""
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    captured = {}

    def fake_run(cmd, input=None, **kwargs):
        captured["input"] = input
        captured["cmd"] = cmd
        proc = MagicMock()
        proc.stdout = json.dumps(
            {
                "success": True,
                "needs_more_fields": False,
                "fields": [],
                "current_url": "",
                "error": "",
            }
        )
        return proc

    with patch.object(login_mod.subprocess, "run", side_effect=fake_run):
        _client().post(
            "/api/login/submit",
            data={
                "domain": "x.com",
                "current_url": "https://x.com/login",
                "fields_json": '{"password": "secret"}',
            },
        )
    assert "secret" in captured["input"]
    assert not any("secret" in str(arg) for arg in captured["cmd"])
