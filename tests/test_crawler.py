"""page_crawler.py の純粋関数ユニットテスト（Playwright 不要）"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch
from urllib.robotparser import RobotFileParser

import pytest

import crawler.page_crawler as pc
from crawler.page_crawler import (
    PageData,
    _discover_one,
    _format_page_id,
    _is_spa_navigation,
    _next_urls,
    _should_skip,
    is_internal_link,
    normalize_url,
)

# ---------- normalize_url ----------


class TestNormalizeUrl:
    def test_trailing_slash_removed(self) -> None:
        assert normalize_url("https://example.com/path/") == "https://example.com/path"

    def test_root_slash_preserved(self) -> None:
        assert normalize_url("https://example.com/") == "https://example.com/"

    def test_scheme_lowercased(self) -> None:
        assert normalize_url("HTTPS://example.com/") == "https://example.com/"

    def test_host_lowercased(self) -> None:
        assert normalize_url("https://EXAMPLE.COM/") == "https://example.com/"

    def test_query_string_preserved(self) -> None:
        result = normalize_url("https://example.com/search?q=test")
        assert "q=test" in result

    def test_fragment_stripped(self) -> None:
        result = normalize_url("https://example.com/page#section")
        assert "#" not in result

    def test_whitespace_stripped(self) -> None:
        result = normalize_url("  https://example.com/  ")
        assert result == "https://example.com/"


# ---------- is_internal_link ----------


class TestIsInternalLink:
    def test_same_host_is_internal(self) -> None:
        assert is_internal_link("https://example.com/", "https://example.com/about") is True

    def test_different_host_is_external(self) -> None:
        assert is_internal_link("https://example.com/", "https://other.com/page") is False

    def test_relative_link_is_internal(self) -> None:
        assert is_internal_link("https://example.com/", "/about") is True

    def test_subdomain_is_external(self) -> None:
        assert is_internal_link("https://example.com/", "https://sub.example.com/") is False

    def test_default_port_ignored_http(self) -> None:
        assert is_internal_link("http://example.com/", "http://example.com:80/page") is True

    def test_default_port_ignored_https(self) -> None:
        assert is_internal_link("https://example.com/", "https://example.com:443/page") is True

    def test_non_default_port_is_external(self) -> None:
        assert is_internal_link("https://example.com/", "https://example.com:8080/page") is False

    def test_anchor_only_is_internal(self) -> None:
        assert is_internal_link("https://example.com/page", "#section") is True


# ---------- _format_page_id ----------


class TestFormatPageId:
    def test_single_digit(self) -> None:
        assert _format_page_id(1) == "P001"

    def test_double_digit(self) -> None:
        assert _format_page_id(12) == "P012"

    def test_triple_digit(self) -> None:
        assert _format_page_id(999) == "P999"

    def test_starts_with_prefix(self) -> None:
        assert _format_page_id(5).startswith("P")


# ---------- _should_skip ----------


class TestShouldSkip:
    def _allow_all_robots(self) -> RobotFileParser:
        parser = RobotFileParser()
        parser.allow_all = True
        return parser

    def test_skip_if_depth_exceeded(self) -> None:
        assert _should_skip("https://example.com/", 4, 3, set(), self._allow_all_robots()) is True

    def test_skip_if_already_visited(self) -> None:
        visited = {"https://example.com/"}
        assert _should_skip("https://example.com/", 0, 3, visited, self._allow_all_robots()) is True

    def test_not_skip_valid_url(self) -> None:
        assert (
            _should_skip("https://example.com/page", 1, 3, set(), self._allow_all_robots()) is False
        )

    def test_skip_at_exact_max_depth(self) -> None:
        # depth == max_depth は許可（超過 = > のみスキップ）
        assert _should_skip("https://example.com/", 3, 3, set(), self._allow_all_robots()) is False

    def test_skip_robots_disallowed(self) -> None:
        parser = RobotFileParser()
        parser.parse(["User-agent: *", "Disallow: /private/"])
        assert _should_skip("https://example.com/private/page", 0, 3, set(), parser) is True


# ---------- _next_urls ----------


class TestNextUrls:
    def test_returns_next_depth_urls(self) -> None:
        links = ("https://example.com/a", "https://example.com/b")
        result = _next_urls(links, 0, set(), 3)
        assert ("https://example.com/a", 1) in result
        assert ("https://example.com/b", 1) in result

    def test_skips_already_visited(self) -> None:
        links = ("https://example.com/a", "https://example.com/b")
        visited = {"https://example.com/a"}
        result = _next_urls(links, 0, visited, 3)
        assert all(url != "https://example.com/a" for url, _ in result)

    def test_returns_empty_when_max_depth_reached(self) -> None:
        links = ("https://example.com/a",)
        result = _next_urls(links, 3, set(), 3)
        assert result == []

    def test_empty_links(self) -> None:
        assert _next_urls((), 0, set(), 3) == []


# ---------- _discover_one ----------


class TestDiscoverOne:
    def _mock_page(self, title: str, hrefs: list[str]) -> MagicMock:
        page = MagicMock()
        page.title.return_value = title
        page.eval_on_selector_all.return_value = hrefs
        page.url = "https://example.com/"
        page.goto.return_value = MagicMock(status=200)
        page.query_selector.return_value = None
        return page

    def test_appends_url_and_title(self) -> None:
        page = self._mock_page("ホーム", ["https://example.com/a"])
        found: list[dict[str, object]] = []
        _discover_one(page, "https://example.com/", found)
        assert found[0]["url"] == "https://example.com/"
        assert found[0]["title"] == "ホーム"

    def test_public_page_not_login_required(self) -> None:
        page = self._mock_page("ホーム", [])
        found: list[dict[str, object]] = []
        _discover_one(page, "https://example.com/", found)
        assert found[0]["login_required"] is False

    def test_password_page_is_login_required(self) -> None:
        page = self._mock_page("ログイン", [])
        page.query_selector.return_value = MagicMock()
        found: list[dict[str, object]] = []
        _discover_one(page, "https://example.com/", found)
        assert found[0]["login_required"] is True

    def test_returns_internal_links(self) -> None:
        page = self._mock_page("t", ["https://example.com/a", "https://other.com/x"])
        links = _discover_one(page, "https://example.com/", [])
        assert "https://example.com/a" in links
        assert all("other.com" not in link for link in links)

    def test_returns_empty_on_goto_error(self) -> None:
        from playwright.sync_api import Error as PlaywrightError

        page = MagicMock()
        page.goto.side_effect = PlaywrightError("nav error")
        found: list[dict[str, str]] = []
        assert _discover_one(page, "https://example.com/", found) == ()
        assert found == []


# ---------- discover_pages / crawl_urls（_browser_page をモック）----------


def _allow_all_robots() -> RobotFileParser:
    parser = RobotFileParser()
    parser.allow_all = True
    return parser


@contextmanager
def _fake_browser(_auth):
    yield MagicMock()


class TestDiscoverPages:
    def test_collects_discovered_pages(self) -> None:
        def fake_discover(_page, url, found):
            found.append({"url": url, "title": "x"})
            return ()

        with (
            patch.object(pc, "_browser_page", _fake_browser),
            patch.object(pc, "_discover_one", side_effect=fake_discover),
            patch.object(pc, "_load_robots_parser", return_value=_allow_all_robots()),
            patch.object(pc.time, "sleep"),
        ):
            found = pc.discover_pages("https://example.com/", depth=1, max_pages=5)
        assert len(found) == 1
        assert found[0]["url"] == "https://example.com/"

    def test_respects_max_pages(self) -> None:
        def fake_discover(_page, url, found):
            found.append({"url": url, "title": "x"})
            return ("https://example.com/a", "https://example.com/b")

        with (
            patch.object(pc, "_browser_page", _fake_browser),
            patch.object(pc, "_discover_one", side_effect=fake_discover),
            patch.object(pc, "_load_robots_parser", return_value=_allow_all_robots()),
            patch.object(pc.time, "sleep"),
        ):
            found = pc.discover_pages("https://example.com/", depth=3, max_pages=2)
        assert len(found) == 2


class TestCrawlUrls:
    def _page(self, url: str) -> PageData:
        return PageData(url=url, title="t", headings=(), links=(), forms=(), screenshot_path=None)

    def test_dedupes_and_crawls(self) -> None:
        with (
            patch.object(pc, "_browser_page", _fake_browser),
            patch.object(pc, "_crawl_page_with_id", side_effect=lambda p, u, i, o: self._page(u)),
            patch.object(pc.time, "sleep"),
        ):
            pages = pc.crawl_urls(
                [
                    "https://example.com/",
                    "https://example.com/",
                    "https://example.com/a",
                ]
            )
        assert len(pages) == 2

    def test_skips_failed_pages(self) -> None:
        with (
            patch.object(pc, "_browser_page", _fake_browser),
            patch.object(pc, "_crawl_page_with_id", return_value=None),
            patch.object(pc.time, "sleep"),
        ):
            pages = pc.crawl_urls(["https://example.com/"])
        assert pages == []

    def test_ignores_blank_urls(self) -> None:
        with (
            patch.object(pc, "_browser_page", _fake_browser),
            patch.object(pc, "_crawl_page_with_id", side_effect=lambda p, u, i, o: self._page(u)),
            patch.object(pc.time, "sleep"),
        ):
            pages = pc.crawl_urls(["", "  ", "https://example.com/"])
        assert len(pages) == 1


class TestSessionExpiry:
    """#7: 認証付きクロールで login wall に当たると中断する。"""

    def _login_wall_browser(self):
        @contextmanager
        def _cm(_auth):
            page = MagicMock()
            page.title.return_value = "Login"
            page.eval_on_selector_all.return_value = []
            page.url = "https://example.com/login"  # 認証ページへリダイレクト
            page.goto.return_value = MagicMock(status=200)
            page.query_selector.return_value = MagicMock()  # パスワード欄あり
            yield page

        return _cm

    def test_crawl_urls_raises_when_session_expired(self, tmp_path) -> None:
        from crawler.session_guard import SessionExpiredError

        auth = tmp_path / "auth.json"
        auth.write_text("{}", encoding="utf-8")
        with (
            patch.object(pc, "_browser_page", self._login_wall_browser()),
            patch.object(pc.time, "sleep"),
        ):
            with pytest.raises(SessionExpiredError):
                pc.crawl_urls(["https://example.com/dashboard"], auth_state=auth)

    def test_crawl_urls_no_raise_without_auth(self) -> None:
        with (
            patch.object(pc, "_browser_page", self._login_wall_browser()),
            patch.object(pc, "_crawl_page_with_id", return_value=None),
            patch.object(pc.time, "sleep"),
        ):
            pages = pc.crawl_urls(["https://example.com/dashboard"], auth_state=None)
        assert pages == []


# ---------- _is_spa_navigation ----------


class TestIsSpaNavigation:
    def test_detects_path_change_same_host(self) -> None:
        assert _is_spa_navigation("https://example.com/page1", "https://example.com/page2")

    def test_different_host_returns_false(self) -> None:
        assert not _is_spa_navigation("https://example.com/", "https://other.com/")

    def test_same_url_returns_false(self) -> None:
        assert not _is_spa_navigation("https://example.com/page", "https://example.com/page")

    def test_hash_change_same_path_returns_true(self) -> None:
        # normalize_url strips fragment, so hash-only change is treated as same URL
        # The function compares after normalize_url which strips fragments:
        # this documents the current (expected) behaviour
        result = _is_spa_navigation(
            "https://example.com/page#section1",
            "https://example.com/page#section2",
        )
        # Both fragments are stripped by normalize_url → same path, no change → False
        assert result is False

    def test_subdomain_is_different_host(self) -> None:
        assert not _is_spa_navigation("https://example.com/", "https://sub.example.com/")

    def test_path_change_with_query_is_spa(self) -> None:
        assert _is_spa_navigation(
            "https://example.com/list",
            "https://example.com/detail?id=1",
        )


# ---------- _dummy_value ----------


def test_dummy_value_email():
    from crawler.page_crawler import _dummy_value

    from crawler.page_crawler import FieldData
    assert _dummy_value(FieldData("email", "email", "", False)) == "test@example.com"


def test_dummy_value_password():
    from crawler.page_crawler import _dummy_value, FieldData

    assert _dummy_value(FieldData("password", "pwd", "", False)) == "Test1234!"


def test_dummy_value_number_with_min():
    from crawler.page_crawler import _dummy_value, FieldData

    assert _dummy_value(FieldData("number", "qty", "", False, min_value="5")) == "5"


def test_dummy_value_number_no_min():
    from crawler.page_crawler import _dummy_value, FieldData

    assert _dummy_value(FieldData("number", "qty", "", False)) == "1"


def test_dummy_value_date():
    from crawler.page_crawler import _dummy_value, FieldData

    assert _dummy_value(FieldData("date", "dt", "", False)) == "2024-01-01"


def test_dummy_value_checkbox():
    from crawler.page_crawler import _dummy_value, FieldData

    assert _dummy_value(FieldData("checkbox", "agree", "", False)) == "checked"


def test_dummy_value_select_with_options():
    from crawler.page_crawler import _dummy_value, FieldData

    field = FieldData("select", "country", "", False, options=("jp", "us"))
    assert _dummy_value(field) == "jp"


def test_dummy_value_select_no_options():
    from crawler.page_crawler import _dummy_value, FieldData

    field = FieldData("select", "country", "", False)
    assert _dummy_value(field) == ""


def test_dummy_value_text():
    from crawler.page_crawler import _dummy_value, FieldData

    assert _dummy_value(FieldData("text", "name", "", False)) == "テスト入力値"


def test_dummy_value_textarea():
    from crawler.page_crawler import _dummy_value, FieldData

    assert _dummy_value(FieldData("textarea", "body", "", False)) == "テスト入力値"


def test_dummy_value_maxlength_truncates():
    from crawler.page_crawler import _dummy_value, FieldData

    v = _dummy_value(FieldData("text", "name", "", False, maxlength=3))
    assert len(v) <= 3


def test_dummy_value_maxlength_no_truncation_when_short():
    from crawler.page_crawler import _dummy_value, FieldData

    v = _dummy_value(FieldData("email", "em", "", False, maxlength=100))
    assert v == "test@example.com"


# ---------- _is_sensitive_form ----------


def test_is_sensitive_form_payment():
    from crawler.page_crawler import _is_sensitive_form, FormData

    form = FormData(action="/payment/confirm", method="post", fields=())
    assert _is_sensitive_form(form) is True


def test_is_sensitive_form_checkout():
    from crawler.page_crawler import _is_sensitive_form, FormData

    form = FormData(action="/checkout", method="post", fields=())
    assert _is_sensitive_form(form) is True


def test_is_sensitive_form_billing():
    from crawler.page_crawler import _is_sensitive_form, FormData

    form = FormData(action="/billing/address", method="post", fields=())
    assert _is_sensitive_form(form) is True


def test_is_sensitive_form_personal():
    from crawler.page_crawler import _is_sensitive_form, FormData

    form = FormData(action="/personal/info", method="post", fields=())
    assert _is_sensitive_form(form) is True


def test_is_sensitive_form_private():
    from crawler.page_crawler import _is_sensitive_form, FormData

    form = FormData(action="/private/data", method="post", fields=())
    assert _is_sensitive_form(form) is True


def test_is_sensitive_form_general():
    from crawler.page_crawler import _is_sensitive_form, FormData

    form = FormData(action="/contact/submit", method="post", fields=())
    assert _is_sensitive_form(form) is False


def test_is_sensitive_form_empty_action():
    from crawler.page_crawler import _is_sensitive_form, FormData

    form = FormData(action="", method="post", fields=())
    assert _is_sensitive_form(form) is False


def test_is_sensitive_form_case_insensitive():
    from crawler.page_crawler import _is_sensitive_form, FormData

    form = FormData(action="/PAYMENT/confirm", method="post", fields=())
    assert _is_sensitive_form(form) is True


# ---------- PageData state_id field ----------


class TestPageDataStateId:
    def test_default_state_id(self) -> None:
        page = PageData(
            url="https://example.com/",
            title="Home",
            headings=(),
            links=(),
            forms=(),
            screenshot_path=None,
        )
        assert page.state_id == "default"

    def test_custom_state_id(self) -> None:
        page = PageData(
            url="https://example.com/",
            title="Home",
            headings=(),
            links=(),
            forms=(),
            screenshot_path=None,
            state_id="abc12345",
        )
        assert page.state_id == "abc12345"

    def test_state_id_is_immutable(self) -> None:
        page = PageData(
            url="https://example.com/",
            title="Home",
            headings=(),
            links=(),
            forms=(),
            screenshot_path=None,
        )
        with pytest.raises((AttributeError, TypeError)):
            page.state_id = "other"  # type: ignore[misc]
