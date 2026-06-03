"""auto_login モジュールの単体テスト（Playwright をモック）"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crawler.auto_login import (
    LoginField,
    ScrapeResult,
    SubmitResult,
    _fill,
    _fill_generic,
    _submit,
    _visible_fields,
    scrape_login_fields,
    submit_login_form,
    submit_login_simple,
)
from crawler.page_crawler import FieldData, FormData

# ---------------------------------------------------------------------------
# dataclasses
# ---------------------------------------------------------------------------


def test_login_field_frozen() -> None:
    f = LoginField(
        name="user",
        field_type="text",
        label="ユーザー",
        placeholder="",
        required=True,
        element_id="uid",
    )
    assert f.name == "user"
    assert f.required is True


def test_scrape_result() -> None:
    r = ScrapeResult(ok=True, fields=(), current_url="https://x.com")
    assert r.error == ""


def test_submit_result() -> None:
    r = SubmitResult(success=True, needs_more_fields=False, fields=(), current_url="https://x.com")
    assert r.error == ""


# ---------------------------------------------------------------------------
# _visible_fields
# ---------------------------------------------------------------------------


def _make_page_with_forms(*forms: FormData) -> MagicMock:
    page = MagicMock()
    return page, forms


def test_visible_fields_returns_login_field(monkeypatch) -> None:
    fd = FieldData(
        field_type="text",
        name="username",
        placeholder="ID",
        required=True,
        element_id="uid",
    )
    form = FormData(action="/login", method="post", fields=(fd,))
    page = MagicMock()
    with patch("crawler.auto_login.extract_forms", return_value=[form]):
        result = _visible_fields(page)
    assert len(result) == 1
    assert result[0].name == "username"
    assert result[0].field_type == "text"


def test_visible_fields_excludes_hidden_submit(monkeypatch) -> None:
    fields = tuple(
        FieldData(field_type=t, name=t, placeholder="", required=False)
        for t in ("hidden", "submit", "button", "reset", "image")
    )
    form = FormData(action="/login", method="post", fields=fields)
    page = MagicMock()
    with patch("crawler.auto_login.extract_forms", return_value=[form]):
        result = _visible_fields(page)
    assert result == []


def test_visible_fields_deduplicates_by_name(monkeypatch) -> None:
    fd1 = FieldData(field_type="text", name="user", placeholder="", required=False)
    fd2 = FieldData(field_type="text", name="user", placeholder="dup", required=False)
    form = FormData(action="/login", method="post", fields=(fd1, fd2))
    page = MagicMock()
    with patch("crawler.auto_login.extract_forms", return_value=[form]):
        result = _visible_fields(page)
    assert len(result) == 1


def test_visible_fields_skips_no_key(monkeypatch) -> None:
    fd = FieldData(field_type="text", name="", placeholder="", required=False, element_id="")
    form = FormData(action="/", method="get", fields=(fd,))
    page = MagicMock()
    with patch("crawler.auto_login.extract_forms", return_value=[form]):
        result = _visible_fields(page)
    assert result == []


# ---------------------------------------------------------------------------
# _fill_generic
# ---------------------------------------------------------------------------


def test_fill_generic_fills_username_and_password() -> None:
    page = MagicMock()
    _fill_generic(page, "alice", "secret")
    assert page.locator.call_count >= 2


def test_fill_generic_skips_empty_username() -> None:
    page = MagicMock()
    _fill_generic(page, "", "secret")
    # passwordだけ呼ばれる
    assert page.locator.call_count == 1


def test_fill_generic_skips_empty_password() -> None:
    page = MagicMock()
    _fill_generic(page, "alice", "")
    assert page.locator.call_count == 1


def test_fill_generic_handles_exception() -> None:
    page = MagicMock()
    page.locator.return_value.first.fill.side_effect = Exception("timeout")
    _fill_generic(page, "alice", "secret")  # ログ警告のみ・例外伝播しない


# ---------------------------------------------------------------------------
# _fill
# ---------------------------------------------------------------------------


def test_fill_fills_by_name() -> None:
    page = MagicMock()
    _fill(page, {"username": "alice"})
    page.locator.assert_called_with('[name="username"]')


def test_fill_skips_empty_value() -> None:
    page = MagicMock()
    _fill(page, {"username": ""})
    page.locator.assert_not_called()


def test_fill_falls_back_to_id_on_exception() -> None:
    page = MagicMock()
    page.locator.return_value.first.fill.side_effect = Exception("err")
    _fill(page, {"uid": "val"})  # 例外が伝播しない


def test_fill_both_fallbacks_fail() -> None:
    page = MagicMock()
    page.locator.return_value.first.fill.side_effect = Exception("err")
    _fill(page, {"name": "val"})  # ログ警告のみ


# ---------------------------------------------------------------------------
# _submit
# ---------------------------------------------------------------------------


def test_submit_clicks_button() -> None:
    page = MagicMock()
    _submit(page)
    page.locator.assert_called()


def test_submit_falls_back_to_enter_on_click_fail() -> None:
    page = MagicMock()
    page.locator.return_value.first.click.side_effect = Exception("no button")
    _submit(page)
    page.keyboard.press.assert_called_with("Enter")


def test_submit_handles_enter_fail() -> None:
    page = MagicMock()
    page.locator.return_value.first.click.side_effect = Exception("no button")
    page.keyboard.press.side_effect = Exception("keyboard error")
    _submit(page)  # ログ警告のみ


def test_submit_handles_wait_exception() -> None:
    page = MagicMock()
    page.wait_for_load_state.side_effect = Exception("timeout")
    _submit(page)  # ログ警告のみ


# ---------------------------------------------------------------------------
# scrape_login_fields（playwright をモック）
# ---------------------------------------------------------------------------


def _make_pw_mock(page_mock: MagicMock) -> MagicMock:
    """sync_playwright() コンテキストマネージャのモックを返す。"""
    browser = MagicMock()
    ctx = MagicMock()
    ctx.new_page.return_value = page_mock
    browser.new_context.return_value = ctx
    pw = MagicMock()
    pw.chromium.launch.return_value = browser
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=pw)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def test_scrape_login_fields_success() -> None:
    page = MagicMock()
    page.url = "https://example.com/login"
    fd = FieldData(
        field_type="password",
        name="password",
        placeholder="pw",
        required=True,
        element_id="pw",
    )
    form = FormData(action="/login", method="post", fields=(fd,))
    with (
        patch("crawler.auto_login.sync_playwright", return_value=_make_pw_mock(page)),
        patch("crawler.auto_login.extract_forms", return_value=[form]),
    ):
        result = scrape_login_fields("https://example.com/login")
    # passwordはEXCLUDED_TYPESに含まれないが fields=() でもok=Falseになりうる
    assert isinstance(result, ScrapeResult)
    assert result.current_url == "https://example.com/login"


def test_scrape_login_fields_goto_exception() -> None:
    page = MagicMock()
    page.goto.side_effect = Exception("navigation error")
    with patch("crawler.auto_login.sync_playwright", return_value=_make_pw_mock(page)):
        result = scrape_login_fields("https://example.com/login")
    assert result.ok is False
    assert "navigation error" in result.error


# ---------------------------------------------------------------------------
# submit_login_form（playwright をモック）
# ---------------------------------------------------------------------------


def test_submit_login_form_success(tmp_path: Path) -> None:
    page = MagicMock()
    page.url = "https://example.com/dashboard"
    with (
        patch("crawler.auto_login.sync_playwright", return_value=_make_pw_mock(page)),
        patch("crawler.auto_login.has_password_field", return_value=False),
        patch(
            "crawler.auto_login.detect_login_wall",
            return_value=MagicMock(is_login_required=False),
        ),
    ):
        auth_path = tmp_path / "auth.json"
        result = submit_login_form(
            {"username": "alice", "password": "pw"},
            "https://example.com/login",
            auth_path,
        )
    assert result.success is True


def test_submit_login_form_mfa(tmp_path: Path) -> None:
    page = MagicMock()
    page.url = "https://example.com/mfa"
    fd = FieldData(
        field_type="text", name="otp", placeholder="OTP", required=True, element_id="otp"
    )
    form = FormData(action="/mfa", method="post", fields=(fd,))
    with (
        patch("crawler.auto_login.sync_playwright", return_value=_make_pw_mock(page)),
        patch("crawler.auto_login.has_password_field", return_value=False),
        patch(
            "crawler.auto_login.detect_login_wall",
            return_value=MagicMock(is_login_required=True),
        ),
        patch("crawler.auto_login.extract_forms", return_value=[form]),
    ):
        auth_path = tmp_path / "auth.json"
        temp_path = tmp_path / "temp.json"
        result = submit_login_form(
            {"username": "alice", "password": "pw"},
            "https://example.com/login",
            auth_path,
            temp_path,
        )
    assert result.needs_more_fields is True
    assert len(result.fields) == 1


def test_submit_login_form_fail_no_fields(tmp_path: Path) -> None:
    page = MagicMock()
    page.url = "https://example.com/login"
    with (
        patch("crawler.auto_login.sync_playwright", return_value=_make_pw_mock(page)),
        patch("crawler.auto_login.has_password_field", return_value=True),
        patch(
            "crawler.auto_login.detect_login_wall",
            return_value=MagicMock(is_login_required=True),
        ),
        patch("crawler.auto_login.extract_forms", return_value=[]),
    ):
        auth_path = tmp_path / "auth.json"
        result = submit_login_form(
            {"username": "alice", "password": "wrong"},
            "https://example.com/login",
            auth_path,
        )
    assert result.success is False
    assert result.needs_more_fields is False


def test_submit_login_form_goto_exception(tmp_path: Path) -> None:
    page = MagicMock()
    page.goto.side_effect = Exception("network error")
    with patch("crawler.auto_login.sync_playwright", return_value=_make_pw_mock(page)):
        auth_path = tmp_path / "auth.json"
        result = submit_login_form({"username": "u"}, "https://example.com/login", auth_path)
    assert result.success is False
    assert "network error" in result.error


# ---------------------------------------------------------------------------
# submit_login_simple（playwright をモック）
# ---------------------------------------------------------------------------


def test_submit_login_simple_success(tmp_path: Path) -> None:
    page = MagicMock()
    page.url = "https://example.com/home"
    with (
        patch("crawler.auto_login.sync_playwright", return_value=_make_pw_mock(page)),
        patch("crawler.auto_login.has_password_field", return_value=False),
        patch(
            "crawler.auto_login.detect_login_wall",
            return_value=MagicMock(is_login_required=False),
        ),
    ):
        auth_path = tmp_path / "auth.json"
        result = submit_login_simple("alice", "pw", "https://example.com/login", auth_path)
    assert result.success is True


def test_submit_login_simple_fail(tmp_path: Path) -> None:
    page = MagicMock()
    page.url = "https://example.com/login"
    with (
        patch("crawler.auto_login.sync_playwright", return_value=_make_pw_mock(page)),
        patch("crawler.auto_login.has_password_field", return_value=True),
        patch(
            "crawler.auto_login.detect_login_wall",
            return_value=MagicMock(is_login_required=True),
        ),
    ):
        auth_path = tmp_path / "auth.json"
        result = submit_login_simple("alice", "wrong", "https://example.com/login", auth_path)
    assert result.success is False


def test_submit_login_simple_goto_exception(tmp_path: Path) -> None:
    page = MagicMock()
    page.goto.side_effect = Exception("conn refused")
    with patch("crawler.auto_login.sync_playwright", return_value=_make_pw_mock(page)):
        auth_path = tmp_path / "auth.json"
        result = submit_login_simple("u", "p", "https://example.com/login", auth_path)
    assert result.success is False
    assert "conn refused" in result.error
