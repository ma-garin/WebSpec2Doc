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


def test_get_allow_local_default_false(env_file: Path) -> None:
    response = _client().get("/api/settings/allow-local")

    assert response.status_code == 200
    assert response.get_json() == {"allow_local": False}


def test_get_allow_local_true_when_env_set(env_file: Path) -> None:
    env_file.write_text("WEBSPEC2DOC_ALLOW_LOCAL=1\n", encoding="utf-8")

    response = _client().get("/api/settings/allow-local")

    assert response.status_code == 200
    assert response.get_json() == {"allow_local": True}


def test_post_allow_local_enable(env_file: Path) -> None:
    response = _client().post("/api/settings/allow-local", json={"enabled": True})

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "allow_local": True}
    assert env_file.read_text(encoding="utf-8") == "WEBSPEC2DOC_ALLOW_LOCAL=1\n"


def test_post_allow_local_disable(env_file: Path) -> None:
    client = _client()
    client.post("/api/settings/allow-local", json={"enabled": True})

    response = client.post("/api/settings/allow-local", json={"enabled": False})

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "allow_local": False}
    assert env_file.read_text(encoding="utf-8") == "WEBSPEC2DOC_ALLOW_LOCAL=\n"


def test_post_allow_local_invalid_json_returns_400(env_file: Path) -> None:
    response = _client().post(
        "/api/settings/allow-local",
        data="not-json",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert not env_file.exists()


@pytest.mark.parametrize("enabled", [1, 0, "true", None])
def test_post_allow_local_rejects_non_boolean(env_file: Path, enabled: object) -> None:
    response = _client().post("/api/settings/allow-local", json={"enabled": enabled})

    assert response.status_code == 400
    assert not env_file.exists()
