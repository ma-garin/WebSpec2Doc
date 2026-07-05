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


# ─────────────────────── /api/settings/test-design ───────────────────────

import web.services.test_design_settings as test_design_settings  # noqa: E402


@pytest.fixture
def test_design_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "test_design_settings.json"
    monkeypatch.setattr(test_design_settings, "TEST_DESIGN_SETTINGS_FILE", path)
    return path


def test_get_test_design_settings_returns_default_value_catalog(test_design_file: Path) -> None:
    response = _client().get("/api/settings/test-design")

    assert response.status_code == 200
    body = response.get_json()
    assert "email" in body["value_catalog"]
    labels = {entry["label"] for entry in body["value_catalog"]["email"]}
    assert {"上限値", "上限値+1", "空白", "RFC違反", "未登録", "解約済み"} <= labels


def test_post_test_design_settings_saves_and_round_trips(test_design_file: Path) -> None:
    client = _client()
    payload = {"value_catalog": {"email": [{"label": "カスタム", "value": "x@example.com"}]}}

    response = client.post("/api/settings/test-design", json=payload)
    assert response.status_code == 200
    assert response.get_json() == payload

    reloaded = client.get("/api/settings/test-design")
    assert reloaded.get_json()["value_catalog"]["email"][0]["label"] == "カスタム"


def test_post_test_design_settings_invalid_json_returns_400(test_design_file: Path) -> None:
    response = _client().post(
        "/api/settings/test-design",
        data="not-json",
        content_type="application/json",
    )
    assert response.status_code == 400
    assert not test_design_file.exists()
