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


# ---------- /api/login/record/* （認証フローレコーダー・SPEC-3-2） ----------


def test_record_start_launches_subprocess_and_returns_pid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    captured = {}

    class _FakeProc:
        pid = 4242

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeProc()

    with patch.object(login_mod.subprocess, "Popen", side_effect=fake_popen):
        res = _client().post(
            "/api/login/record/start",
            data={"domain": "example.com", "login_url": "https://example.com/login"},
        )
    data = res.get_json()
    assert data["success"] is True
    assert data["pid"] == 4242
    assert "--login-record" in captured["cmd"]
    assert "--login-record-url" in captured["cmd"]
    assert str(tmp_path / "example.com" / "auth.json") in captured["cmd"]


def test_record_start_rejects_missing_login_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    res = _client().post("/api/login/record/start", data={"domain": "example.com"})
    assert res.status_code == 400


def test_record_start_rejects_invalid_domain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    res = _client().post(
        "/api/login/record/start",
        data={"domain": "../etc", "login_url": "https://example.com/login"},
    )
    assert res.status_code == 400


def test_record_start_clears_stale_signal_and_status(tmp_path: Path, monkeypatch) -> None:
    """前回セッションの残骸（シグナル・状態ファイル）を持ち越さない。"""
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    domain_dir = tmp_path / "example.com"
    domain_dir.mkdir(parents=True)
    (domain_dir / ".login_signal").touch()
    (domain_dir / ".login_status.json").write_text('{"phase": "saved"}', encoding="utf-8")

    class _FakeProc:
        pid = 1

    with patch.object(login_mod.subprocess, "Popen", return_value=_FakeProc()):
        _client().post(
            "/api/login/record/start",
            data={"domain": "example.com", "login_url": "https://example.com/login"},
        )
    assert not (domain_dir / ".login_signal").exists()
    assert not (domain_dir / ".login_status.json").exists()


def test_record_status_returns_waiting_when_no_status_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    res = _client().get("/api/login/record/status", query_string={"domain": "example.com"})
    data = res.get_json()
    assert data["success"] is True
    assert data["phase"] == "waiting"
    assert data["verified"] is None


def test_record_status_reads_status_file_and_appends_auth_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    domain_dir = tmp_path / "example.com"
    domain_dir.mkdir(parents=True)
    (domain_dir / "auth.json").write_text("{}", encoding="utf-8")
    (domain_dir / ".login_status.json").write_text(
        json.dumps(
            {
                "phase": "saved",
                "current_url": "https://example.com/",
                "detail": "",
                "verified": True,
            }
        ),
        encoding="utf-8",
    )

    res = _client().get("/api/login/record/status", query_string={"domain": "example.com"})
    data = res.get_json()
    assert data["phase"] == "saved"
    assert data["verified"] is True
    assert data["auth_path"] == str((domain_dir / "auth.json").resolve())


def test_record_status_rejects_invalid_domain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    res = _client().get("/api/login/record/status", query_string={"domain": "../etc"})
    assert res.status_code == 400


def test_record_complete_touches_signal_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    res = _client().post("/api/login/record/complete", data={"domain": "example.com"})
    assert res.get_json()["success"] is True
    assert (tmp_path / "example.com" / ".login_signal").exists()


def test_record_cancel_sends_sigterm_to_pid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    captured = {}

    def fake_kill(pid, sig):
        captured["pid"] = pid
        captured["sig"] = sig

    with patch.object(login_mod.os, "kill", side_effect=fake_kill):
        res = _client().post("/api/login/record/cancel", data={"pid": "1234"})
    assert res.get_json()["success"] is True
    assert captured["pid"] == 1234


def test_record_cancel_missing_process_is_success(tmp_path: Path, monkeypatch) -> None:
    """既に終了済みのプロセスへの cancel はエラーにしない。"""
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    with patch.object(login_mod.os, "kill", side_effect=ProcessLookupError):
        res = _client().post("/api/login/record/cancel", data={"pid": "999999"})
    assert res.get_json()["success"] is True


def test_record_cancel_rejects_missing_pid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(login_mod, "OUTPUT_DIR", tmp_path)
    res = _client().post("/api/login/record/cancel", data={})
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
