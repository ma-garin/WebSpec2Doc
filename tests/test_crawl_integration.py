"""crawl_page() の統合テスト（Playwright をモック）。"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from crawler.page_crawler import FieldData, FormData


class TestCrawlPageIntegration:
    """crawl_page() の統合テスト（Playwright をモック）。"""

    def _make_mock_page(self, url: str, title: str = "Test Page") -> MagicMock:
        """モック Playwright Page を生成する。"""
        page = MagicMock()
        page.url = url
        page.title.return_value = title
        page.content.return_value = "<html><body><h1>Test</h1></body></html>"
        page.eval_on_selector_all.return_value = []
        page.query_selector.return_value = None
        page.screenshot.return_value = b"\x89PNG\r\n"  # fake PNG
        # goto() returns a response-like mock
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {}
        page.goto.return_value = mock_response
        return page

    def _common_patches(self, extra: dict | None = None):
        """crawl_page() が内部で呼ぶ依存をまとめてパッチするコンテキスト。"""
        base = {
            "crawler.page_crawler.extract_forms_including_frames": [],
            "crawler.page_crawler.extract_internal_links": [],
            "crawler.page_crawler.extract_headings": ["Test"],
            "crawler.page_crawler.extract_buttons": [],
            "crawler.page_crawler.extract_page_title": "Test Page",
            "crawler.page_crawler.has_password_field": False,
            "crawler.page_crawler.compute_dom_signature": "sig001",
            "analyzer.stack_detector.detect_stack": None,
        }
        if extra:
            base.update(extra)
        return base

    def test_crawl_page_returns_page_data(self, tmp_path: Path) -> None:
        """crawl_page() が PageData を返す基本テスト。"""
        from crawler.page_crawler import crawl_page

        page = self._make_mock_page("https://example.com/")

        # crawl_page() は依存を関数内ローカルでインポートするため
        # 各ソースモジュール側でパッチする
        with (
            patch("crawler.link_extractor.extract_forms_including_frames", return_value=[]),
            patch("crawler.link_extractor.extract_internal_links", return_value=[]),
            patch("crawler.link_extractor.extract_headings", return_value=["Test"]),
            patch("crawler.link_extractor.extract_buttons", return_value=[]),
            patch("crawler.link_extractor.extract_page_title", return_value="Test Page"),
            patch("crawler.link_extractor.compute_dom_signature", return_value="sig001"),
            patch("analyzer.stack_detector.detect_stack", return_value=None),
            patch("crawler.network_interceptor.NetworkCapture.attach"),
            patch("crawler.network_interceptor.NetworkCapture.detach"),
            patch("crawler.network_interceptor.NetworkCapture.finalize", return_value=()),
        ):
            result = crawl_page(page, "https://example.com/", tmp_path)

        assert result is not None
        assert result.url == "https://example.com/"
        assert result.title == "Test Page"

    def test_crawl_page_with_form(self, tmp_path: Path) -> None:
        """crawl_page() がフォームを含む PageData を返す。"""
        from crawler.page_crawler import crawl_page

        page = self._make_mock_page("https://example.com/login")
        page.url = "https://example.com/login"

        form = FormData(
            action="/login",
            method="post",
            fields=(
                FieldData(
                    field_type="text",
                    name="username",
                    placeholder="",
                    required=True,
                    maxlength=None,
                    minlength=None,
                    min_value="",
                    max_value="",
                    pattern="",
                    default="",
                    options=(),
                    element_id="username",
                ),
                FieldData(
                    field_type="password",
                    name="password",
                    placeholder="",
                    required=True,
                    maxlength=None,
                    minlength=None,
                    min_value="",
                    max_value="",
                    pattern="",
                    default="",
                    options=(),
                    element_id="password",
                ),
            ),
        )

        with (
            patch("crawler.link_extractor.extract_forms_including_frames", return_value=[form]),
            patch("crawler.link_extractor.extract_internal_links", return_value=[]),
            patch("crawler.link_extractor.extract_headings", return_value=["ログイン"]),
            patch("crawler.link_extractor.extract_buttons", return_value=["ログイン"]),
            patch("crawler.link_extractor.extract_page_title", return_value="ログインページ"),
            patch("crawler.link_extractor.compute_dom_signature", return_value="sig002"),
            patch("analyzer.stack_detector.detect_stack", return_value=None),
            patch("crawler.network_interceptor.NetworkCapture.attach"),
            patch("crawler.network_interceptor.NetworkCapture.detach"),
            patch("crawler.network_interceptor.NetworkCapture.finalize", return_value=()),
        ):
            result = crawl_page(page, "https://example.com/login", tmp_path)

        assert result is not None
        assert len(result.forms) == 1
        assert result.forms[0].action == "/login"

    def test_crawl_page_is_sensitive_form_detection(self, tmp_path: Path) -> None:
        """_is_sensitive_form() が payment/checkout アクションを検出する。"""
        from crawler.page_crawler import _is_sensitive_form

        payment_form = FormData(action="/checkout/payment", method="post", fields=())
        regular_form = FormData(action="/search", method="get", fields=())

        assert _is_sensitive_form(payment_form) is True
        assert _is_sensitive_form(regular_form) is False
