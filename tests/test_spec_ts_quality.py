from __future__ import annotations

import json
from pathlib import Path

from web.services.spec_ts_generator import (
    _build_role_based_locator,
    _locator_to_getter_name,
    _url_to_class_name,
    generate_spec_ts,
)


def test_role_based_locator_uses_get_by_label_when_aria_label() -> None:
    result = _build_role_based_locator([], aria_label="メールアドレス", field_type="text")
    assert result == "page.getByLabel('メールアドレス')"


def test_role_based_locator_select_uses_combobox() -> None:
    result = _build_role_based_locator([], field_name="prefecture", field_type="select")
    assert "getByRole('combobox'" in result


def test_role_based_locator_checkbox() -> None:
    result = _build_role_based_locator([], field_name="agree", field_type="checkbox")
    assert "getByRole('checkbox'" in result


def test_role_based_locator_submit_uses_button() -> None:
    result = _build_role_based_locator([], field_name="ログイン", field_type="submit")
    assert "getByRole('button'" in result


def test_role_based_locator_fallback_to_css() -> None:
    result = _build_role_based_locator(['input[name="q"]'], field_type="text")
    assert "page.locator(" in result


def test_url_to_class_name_login() -> None:
    assert _url_to_class_name("https://example.com/login") == "LoginPage"


def test_url_to_class_name_root() -> None:
    assert _url_to_class_name("https://example.com/") == "IndexPage"


def test_url_to_class_name_kebab() -> None:
    assert _url_to_class_name("https://example.com/user-profile") == "UserProfilePage"


def test_locator_to_getter_name_id() -> None:
    assert _locator_to_getter_name("#email") == "emailInput"


def test_locator_to_getter_name_name_attr() -> None:
    assert _locator_to_getter_name('input[name="password"]') == "passwordInput"


def test_locator_to_getter_name_data_testid() -> None:
    assert _locator_to_getter_name('[data-testid="submit-btn"]') == "submitBtnButton"


def test_locator_to_getter_name_unknown() -> None:
    assert _locator_to_getter_name("div.container") == ""


def _make_candidates(tmp_path: Path) -> Path:
    candidates = {
        "candidates": [
            {
                "id": "TC-001",
                "title": "画面表示スモーク",
                "trace_id": "TR-001",
                "automation_status": "automatable",
                "steps": ["page.goto('https://example.com/login')"],
                "locators": ["#email", 'input[name="password"]'],
                "expected": "ログイン画面が表示される",
            }
        ]
    }
    path = tmp_path / "playwright_candidates.json"
    path.write_text(json.dumps(candidates), encoding="utf-8")
    return path


def test_generate_page_object_creates_page_ts(tmp_path: Path) -> None:
    candidates_path = _make_candidates(tmp_path)
    spec_path = tmp_path / "example.com.spec.ts"
    generate_spec_ts("example.com", candidates_path, spec_path, generate_page_object=True)
    page_path = tmp_path / "example.com.page.ts"
    assert page_path.exists()
    content = page_path.read_text(encoding="utf-8")
    assert "import { Page } from '@playwright/test';" in content
    assert "export class LoginPage" in content


def test_generate_page_object_false_no_page_ts(tmp_path: Path) -> None:
    candidates_path = _make_candidates(tmp_path)
    spec_path = tmp_path / "example.com.spec.ts"
    generate_spec_ts("example.com", candidates_path, spec_path)
    assert not (tmp_path / "example.com.page.ts").exists()


def test_page_ts_contains_locator_getters(tmp_path: Path) -> None:
    candidates_path = _make_candidates(tmp_path)
    spec_path = tmp_path / "example.com.spec.ts"
    generate_spec_ts("example.com", candidates_path, spec_path, generate_page_object=True)
    content = (tmp_path / "example.com.page.ts").read_text(encoding="utf-8")
    assert "emailInput" in content
    assert "passwordInput" in content


def test_existing_spec_ts_still_works(tmp_path: Path) -> None:
    candidates_path = _make_candidates(tmp_path)
    spec_path = tmp_path / "example.com.spec.ts"
    result = generate_spec_ts("example.com", candidates_path, spec_path)
    assert result == spec_path
    assert spec_path.exists()
    assert "import { test, expect }" in spec_path.read_text(encoding="utf-8")
