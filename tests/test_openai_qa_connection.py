from __future__ import annotations

import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
import web.env_store as env_store
from web.services.openai_qa import test_openai_connection as check_openai_connection


@pytest.fixture()
def env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / ".env"
    monkeypatch.setattr(env_store, "ENV_FILE", path)
    return path


def test_no_api_key_returns_false(env_file: Path) -> None:
    ok, message = check_openai_connection()
    assert ok is False
    assert "OPENAI_API_KEY" in message


def test_successful_connection_returns_true(env_file: Path) -> None:
    env_file.write_text("OPENAI_API_KEY=sk-test123\n", encoding="utf-8")

    class _FakeResponse:
        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"data": []}'

    with patch("urllib.request.urlopen", return_value=_FakeResponse()) as mock_urlopen:
        ok, message = check_openai_connection()
    assert ok is True
    assert "成功" in message
    assert mock_urlopen.called


def test_http_error_returns_false_with_status(env_file: Path) -> None:
    env_file.write_text("OPENAI_API_KEY=sk-test123\n", encoding="utf-8")

    error = urllib.error.HTTPError(
        url="https://api.openai.com/v1/models",
        code=401,
        msg="Unauthorized",
        hdrs=None,  # type: ignore[arg-type]
        fp=BytesIO(b'{"error": "invalid_api_key"}'),
    )
    with patch("urllib.request.urlopen", side_effect=error):
        ok, message = check_openai_connection()
    assert ok is False
    assert "401" in message


def test_network_error_returns_false(env_file: Path) -> None:
    env_file.write_text("OPENAI_API_KEY=sk-test123\n", encoding="utf-8")

    with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
        ok, message = check_openai_connection()
    assert ok is False
    assert "接続に失敗" in message
