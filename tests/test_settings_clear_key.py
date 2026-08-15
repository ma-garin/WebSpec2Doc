"""API キー削除エンドポイントのテスト。

参照実装（UX_Auto_Reviewer）の「APIキーを削除」に相当。
空欄保存では既存キーを保持する仕様のため、キーを消す手段を別に用意する。
"""

from __future__ import annotations

from pathlib import Path

import app as appmod
import pytest
import web.env_store as env_store


def _client():
    return appmod.app.test_client()


@pytest.fixture
def env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / ".env"
    monkeypatch.setattr(env_store, "ENV_FILE", path)
    return path


def test_clear_key_removes_saved_key(env_file: Path) -> None:
    env_file.write_text("OPENAI_API_KEY=sk-secret\n", encoding="utf-8")

    response = _client().post("/api/settings/clear-key")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "openai_key_set": False}
    # 実際に .env から消えていること（残骸を残さない）
    assert "sk-secret" not in env_file.read_text(encoding="utf-8")


def test_clear_key_is_idempotent_when_no_key(env_file: Path) -> None:
    response = _client().post("/api/settings/clear-key")

    assert response.status_code == 200
    assert response.get_json()["openai_key_set"] is False


def test_clear_key_keeps_other_settings(env_file: Path) -> None:
    """キー削除で他の設定（Slack 等）まで消さないこと。"""
    env_file.write_text(
        "OPENAI_API_KEY=sk-secret\nSLACK_WEBHOOK_URL=https://hooks.slack/x\n",
        encoding="utf-8",
    )

    _client().post("/api/settings/clear-key")

    content = env_file.read_text(encoding="utf-8")
    assert "sk-secret" not in content
    assert "https://hooks.slack/x" in content
