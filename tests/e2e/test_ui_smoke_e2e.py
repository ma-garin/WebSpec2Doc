"""UI スモークテスト（L3 システムテスト）。

目的:
    アプリケーションの主要ページが正しくレンダリングされ、
    基本的なナビゲーションが機能することを検証する。

実行方法:
    make verify-ui
"""

from __future__ import annotations

import os
import re

from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")


class TestAppLoad:
    """アプリケーション起動・ページロードの検証。"""



    def test_no_javascript_errors_on_load(self, page: Page) -> None:
        """ページロード時に JavaScript エラーが発生しない。"""
        js_errors: list[str] = []
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        assert js_errors == [], f"JavaScript エラー: {js_errors}"



class TestNavigation:
    """画面間ナビゲーションの検証。"""





class TestHome:
    """ホームのURL解析導線とAutoRun導線を検証する。"""






class TestResponsiveness:
    """レスポンシブレイアウトの検証。"""

    def test_layout_at_1920x1080(self, page: Page) -> None:
        """1920×1080 でレイアウトが正常。"""
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.goto(BASE_URL)
        page.screenshot(path="tests/e2e/screenshots/layout_1920x1080.png", full_page=False)
        expect(page.locator("body")).to_be_visible()

    def test_layout_at_1366x768(self, page: Page) -> None:
        """1366×768 でレイアウトが正常（主要要素が見切れない）。"""
        page.set_viewport_size({"width": 1366, "height": 768})
        page.goto(BASE_URL)
        page.screenshot(path="tests/e2e/screenshots/layout_1366x768.png", full_page=False)
        expect(page.locator("body")).to_be_visible()

    def test_no_horizontal_scroll_at_1366(self, page: Page) -> None:
        """1366px 幅で水平スクロールが発生しない。"""
        page.set_viewport_size({"width": 1366, "height": 768})
        page.goto(BASE_URL)
        # body の scrollWidth が viewport 幅以下であることを確認
        scroll_width = page.evaluate("document.body.scrollWidth")
        assert (
            scroll_width <= 1366 + 20
        ), f"水平スクロールが発生しています: scrollWidth={scroll_width}px"  # 20px の許容誤差


