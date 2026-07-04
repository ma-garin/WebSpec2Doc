"""ログイン対応（storage_state）のユニットテスト（実ブラウザ不要・全て mock）"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from crawler.auth import capture_auth_state
from crawler.page_crawler import crawl_site


def _mock_playwright(mock_sync_playwright: MagicMock) -> MagicMock:
    playwright = mock_sync_playwright.return_value.__enter__.return_value
    browser = playwright.chromium.launch.return_value
    return browser


# ---------- crawl_site: storage_state 配線 ----------


class TestCrawlSiteAuthState:
    @patch("crawler.page_crawler._load_robots_parser")
    @patch("crawler.page_crawler.sync_playwright")
    def test_passes_storage_state_when_auth_given(
        self, mock_sp: MagicMock, _mock_robots: MagicMock
    ) -> None:
        browser = _mock_playwright(mock_sp)
        # max_pages=0 でクロールループを実行せず、context 生成だけ検証する
        crawl_site("https://example.com", max_pages=0, auth_state=Path("auth.json"))
        browser.new_context.assert_called_once()
        kwargs = browser.new_context.call_args.kwargs
        assert kwargs["storage_state"] == "auth.json"

    @patch("crawler.page_crawler._load_robots_parser")
    @patch("crawler.page_crawler.sync_playwright")
    def test_storage_state_none_when_no_auth(
        self, mock_sp: MagicMock, _mock_robots: MagicMock
    ) -> None:
        browser = _mock_playwright(mock_sp)
        crawl_site("https://example.com", max_pages=0)
        kwargs = browser.new_context.call_args.kwargs
        assert kwargs["storage_state"] is None

    @patch("crawler.page_crawler._load_robots_parser")
    @patch("crawler.page_crawler.sync_playwright")
    def test_browser_uses_japanese_locale(
        self, mock_sp: MagicMock, _mock_robots: MagicMock
    ) -> None:
        """日本語ロケール（validation メッセージ実測の日本語化）が配線されている。"""
        from crawler.page_crawler import BROWSER_LOCALE

        playwright = mock_sp.return_value.__enter__.return_value
        browser = playwright.chromium.launch.return_value
        crawl_site("https://example.com", max_pages=0)
        # context に locale を渡している
        assert browser.new_context.call_args.kwargs["locale"] == BROWSER_LOCALE
        # launch 引数で UI 言語も指定している
        launch_kwargs = playwright.chromium.launch.call_args.kwargs
        assert any(BROWSER_LOCALE in str(arg) for arg in launch_kwargs.get("args", []))


# ---------- capture_auth_state ----------


class TestCaptureAuthState:
    @patch("builtins.input")
    @patch("crawler.auth.sync_playwright")
    def test_saves_storage_state_to_output_path(
        self, mock_sp: MagicMock, mock_input: MagicMock
    ) -> None:
        browser = _mock_playwright(mock_sp)
        context = browser.new_context.return_value

        result = capture_auth_state("https://example.com/login", Path("/tmp/auth.json"))

        context.storage_state.assert_called_once_with(path="/tmp/auth.json")
        mock_input.assert_called_once()
        assert result == Path("/tmp/auth.json")

    @patch("builtins.input")
    @patch("crawler.auth.sync_playwright")
    def test_navigates_to_login_url(self, mock_sp: MagicMock, mock_input: MagicMock) -> None:
        browser = _mock_playwright(mock_sp)
        page = browser.new_context.return_value.new_page.return_value

        capture_auth_state("https://example.com/login", Path("/tmp/auth.json"))

        page.goto.assert_called_once_with("https://example.com/login")
