"""/api/login/start・/api/login/finish ルートのテスト（subprocess をモック）"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
from registry.session_store import session_path, signal_path


def _client():
    return appmod.app.test_client()


def test_login_start_spawns_subprocess(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(appmod, "OUTPUT_DIR", tmp_path)
    appmod._LOGIN_PROCS.clear()
    with patch.object(appmod.subprocess, "Popen", return_value=MagicMock()) as popen:
        data = _client().post(
            "/api/login/start",
            data={"url": "https://example.com/login", "domain": "example.com"},
        ).get_json()
    assert data["ok"] is True
    assert popen.called
    assert "example.com" in appmod._LOGIN_PROCS


def test_login_start_rejects_missing_domain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(appmod, "OUTPUT_DIR", tmp_path)
    res = _client().post("/api/login/start", data={"url": "https://x.com/login"})
    assert res.status_code == 400


def test_login_finish_writes_signal_and_reports_saved(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(appmod, "OUTPUT_DIR", tmp_path)
    # サブプロセス完了でセッションが保存された状態を模倣
    proc = MagicMock()
    proc.wait.return_value = 0
    proc.returncode = 0
    appmod._LOGIN_PROCS["example.com"] = proc
    auth = session_path("example.com", tmp_path)
    auth.parent.mkdir(parents=True, exist_ok=True)
    auth.write_text("{}", encoding="utf-8")
    data = _client().post("/api/login/finish", data={"domain": "example.com"}).get_json()
    assert data["session_saved"] is True
    assert signal_path("example.com", tmp_path).exists()


def test_login_finish_without_start_returns_409(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(appmod, "OUTPUT_DIR", tmp_path)
    appmod._LOGIN_PROCS.clear()
    res = _client().post("/api/login/finish", data={"domain": "example.com"})
    assert res.status_code == 409
