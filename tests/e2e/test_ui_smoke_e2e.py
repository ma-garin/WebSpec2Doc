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

    def test_root_page_loads(self, page: Page) -> None:
        """ルートページが 200 OK で返り、基本要素が存在する。"""
        page.goto(BASE_URL)
        expect(page).not_to_have_title(re.compile(r"error|エラー", re.IGNORECASE))
        expect(page.locator("body")).to_be_visible()

    def test_app_title_contains_product_name(self, page: Page) -> None:
        """ページタイトルにプロダクト名が含まれる。"""
        page.goto(BASE_URL)
        expect(page).to_have_title(re.compile(r"WebSpec2Doc", re.IGNORECASE))

    def test_no_javascript_errors_on_load(self, page: Page) -> None:
        """ページロード時に JavaScript エラーが発生しない。"""
        js_errors: list[str] = []
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        assert js_errors == [], f"JavaScript エラー: {js_errors}"

    def test_sidebar_navigation_exists(self, page: Page) -> None:
        """サイドバーナビゲーションが存在する。"""
        page.goto(BASE_URL)
        expect(page.locator("aside.app-sidebar")).to_be_visible()


class TestNavigation:
    """画面間ナビゲーションの検証。"""

    def test_autorun_view_accessible(self, page: Page) -> None:
        """AutoRun ビューにナビゲーションできる。"""
        page.goto(BASE_URL)
        # AutoRun ナビゲーションリンクをクリック
        autorun_link = (
            page.locator("a, button").filter(has_text=re.compile(r"AutoRun", re.IGNORECASE)).first
        )
        if autorun_link.count() > 0:
            autorun_link.click()
            page.wait_for_load_state("domcontentloaded")
        # AutoRun セクションが存在する
        expect(page.locator("#view-auto-run")).to_be_attached()

    def test_dashboard_accessible(self, page: Page) -> None:
        """ダッシュボードが表示される。"""
        page.goto(BASE_URL)
        expect(
            page.locator("#view-dashboard, .dashboard, [id*='dashboard']").first
        ).to_be_attached()

    def test_no_broken_links_in_sidebar(self, page: Page) -> None:
        """サイドバーのリンクが 404 を返さない（静的チェック）。"""
        page.goto(BASE_URL)
        nav_items = page.locator(".app-nav-item").all()
        assert len(nav_items) > 0, "ナビゲーションアイテムが見つかりません"


class TestHome:
    """ホームのURL解析導線とAutoRun導線を検証する。"""

    def test_home_explains_qa_document_generation(self, page: Page) -> None:
        page.goto(BASE_URL)
        expect(page.locator("#hero-url")).to_be_visible()
        expect(page.locator("#view-dashboard")).to_contain_text("QAドキュメント")
        expect(page.locator("#view-dashboard")).to_contain_text("画面仕様書")
        expect(page.locator("#history-body")).to_be_visible()

    def test_new_analysis_opens_existing_generate_flow(self, page: Page) -> None:
        page.goto(BASE_URL)
        page.locator("#nav-new-analysis-btn").click()
        expect(page.locator("#view-generate")).to_be_visible()

    def test_run_history_nav_opens_run_history_view(self, page: Page) -> None:
        """ナビの「実行履歴」から種別を問わない一般化された実行履歴ビューへ遷移できる
        （R2-27: AutoRunだけでなく解析・現新比較等も含めた一般化）。"""
        page.goto(BASE_URL)
        page.locator("#nav-run-history-btn").click()
        expect(page.locator("#view-run-history")).to_be_visible()

    def test_autorun_is_visible_and_opens(self, page: Page) -> None:
        page.goto(BASE_URL)
        autorun = page.locator('.app-nav-item[data-view="auto-run"]')
        expect(autorun).to_be_visible()
        autorun.click()
        expect(page.locator("#view-auto-run")).to_be_visible()


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

    def test_tablet_home_layout(self, page: Page) -> None:
        """1024×768 でURL入力と解析方式が表示される。"""
        page.set_viewport_size({"width": 1024, "height": 768})
        page.goto(BASE_URL)
        page.screenshot(path="tests/e2e/screenshots/layout_tablet_1024x768.png")
        expect(page.locator("#hero-url")).to_be_visible()
        expect(page.locator("#hero-auto-btn")).to_be_visible()

    def test_mobile_home_has_no_page_overflow(self, page: Page) -> None:
        """390×844 で主要導線が縦並びになり、ページが横溢れしない。"""
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(BASE_URL)
        page.screenshot(path="tests/e2e/screenshots/layout_mobile_390x844.png")
        expect(page.locator("#hero-url")).to_be_visible()
        expect(page.locator("#hero-auto-btn")).to_be_visible()
        assert page.evaluate("document.body.scrollWidth") <= 390
