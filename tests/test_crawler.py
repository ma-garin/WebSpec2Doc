"""page_crawler.py の純粋関数ユニットテスト（Playwright 不要）"""
from __future__ import annotations

import pytest

from crawler.page_crawler import (
    _format_page_id,
    _next_urls,
    _should_skip,
    is_internal_link,
    normalize_url,
)
from urllib.robotparser import RobotFileParser


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
        assert _should_skip("https://example.com/page", 1, 3, set(), self._allow_all_robots()) is False

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
