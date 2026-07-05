from __future__ import annotations

import json
from pathlib import Path

import pytest
import web.services.test_design_settings as test_design_settings
from web.services.test_design_settings import (
    DEFAULT_VALUE_CATALOG,
    get_test_design_settings,
    save_test_design_settings,
)


@pytest.fixture()
def settings_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "test_design_settings.json"
    monkeypatch.setattr(test_design_settings, "TEST_DESIGN_SETTINGS_FILE", path)
    return path


def test_get_creates_default_file_when_missing(settings_file: Path) -> None:
    assert not settings_file.exists()
    settings = get_test_design_settings()
    assert settings_file.is_file()
    assert settings["value_catalog"]["email"] == DEFAULT_VALUE_CATALOG["email"]


def test_default_email_catalog_covers_required_boundary_labels(settings_file: Path) -> None:
    """R1-19: メールの上限値/上限値+1/空白/2byte/RFC違反/未登録/解約済みを網羅すること。"""
    settings = get_test_design_settings()
    labels = {entry["label"] for entry in settings["value_catalog"]["email"]}
    required = {"上限値", "上限値+1", "空白", "RFC違反", "未登録", "解約済み"}
    assert required <= labels
    assert any("2byte" in label or "全角" in label for label in labels)


def test_save_and_reload_round_trips(settings_file: Path) -> None:
    custom = {
        "value_catalog": {"email": [{"label": "カスタム", "value": "x@example.com", "note": "n"}]}
    }
    saved = save_test_design_settings(custom)
    assert saved == custom

    reloaded = get_test_design_settings()
    assert reloaded["value_catalog"]["email"][0]["label"] == "カスタム"

    on_disk = json.loads(settings_file.read_text(encoding="utf-8"))
    assert on_disk["value_catalog"]["email"][0]["label"] == "カスタム"


def test_save_without_value_catalog_falls_back_to_defaults(settings_file: Path) -> None:
    saved = save_test_design_settings({})
    assert saved["value_catalog"]["email"] == DEFAULT_VALUE_CATALOG["email"]


def test_get_returns_defaults_when_file_is_corrupt(settings_file: Path) -> None:
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text("{not json", encoding="utf-8")
    settings = get_test_design_settings()
    assert settings["value_catalog"]["email"] == DEFAULT_VALUE_CATALOG["email"]


def test_get_returns_defaults_when_value_catalog_missing_key(settings_file: Path) -> None:
    settings_file.parent.mkdir(parents=True, exist_ok=True)
    settings_file.write_text(json.dumps({"other": 1}), encoding="utf-8")
    settings = get_test_design_settings()
    assert "value_catalog" in settings


def test_default_catalog_includes_sqli_label(settings_file: Path) -> None:
    """R3-22: SQLi値カタログ追加。email/name カテゴリに提示のみの SQLi 値を追加し、
    既存7カテゴリ構造は不変であること。"""
    settings = get_test_design_settings()
    catalog = settings["value_catalog"]

    assert set(catalog.keys()) == {
        "email",
        "phone_jp",
        "name",
        "date",
        "price",
        "quantity",
        "password",
    }

    for category in ("email", "name"):
        entries = {entry["label"]: entry for entry in catalog[category]}
        assert "SQLインジェクション" in entries
        sqli_entry = entries["SQLインジェクション"]
        assert sqli_entry["value"] == "' OR '1'='1"
        # 攻撃実行はしない・値の提示のみであることを明記した note を持つこと
        assert "値の提示のみ" in sqli_entry["note"]
