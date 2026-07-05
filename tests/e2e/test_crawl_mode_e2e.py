"""クロール方法選択（自動クロール／選択したURLのみ）E2E テスト（L3 システムテスト）。

対象（実ユーザーのドッグフーディング報告）:
    「クロール対象URLで画面解析をする際、オートクロールなのか、対象URLのみ
    なのかを選択できるようにしたい」という要望への対応。
    条件設定ステップに「自動クロール（リンクを辿る）」／「選択したURLのみ」の
    ラジオを追加し、自動クロール選択時は深さ・最大ページを編集可能にし、
    画面リストのチェックボックスは不要になるため非表示にする。

実行方法:
    make verify-ui
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

BASE_URL = "http://127.0.0.1:8765"


def _enter_step2_with_discovered(page: Page, urls: list[str]) -> None:
    """画面分析（discover API）を経由せず、直接ウィザードのstep2状態を作る。"""
    page.goto(BASE_URL)
    page.locator("#nav-new-analysis-btn").click()
    page.wait_for_selector("#url-input", state="visible")
    page.fill("#url-input", urls[0])
    page.evaluate(
        """(urls) => {
            discovered = urls.map(u => ({url: u, title: u, login_required: false}));
            renderDiscovered();
            updateTargetPreview();
            showWizardStep(2);
        }""",
        urls,
    )
    page.wait_for_selector("#wizard-p2", state="visible")


class TestCrawlModeSelection:
    def test_default_mode_is_selected_urls_only(self, page: Page) -> None:
        _enter_step2_with_discovered(page, ["https://example.com/", "https://example.com/about"])
        expect(page.locator("#crawl-mode-selected")).to_be_checked()
        expect(page.locator("#discovered-url-panel")).to_be_visible()
        expect(page.locator("#crawl-mode-auto-fields")).to_be_hidden()

    def test_switching_to_auto_hides_url_checklist_and_shows_depth_fields(self, page: Page) -> None:
        _enter_step2_with_discovered(page, ["https://example.com/", "https://example.com/about"])
        page.locator("#crawl-mode-auto").check()
        expect(page.locator("#crawl-mode-auto-fields")).to_be_visible()
        expect(page.locator("#discovered-url-panel")).to_be_hidden()
        expect(page.locator("#crawl-depth")).to_be_visible()
        expect(page.locator("#max-pages")).to_be_visible()

    def test_auto_mode_target_preview_shows_root_url_only(self, page: Page) -> None:
        _enter_step2_with_discovered(page, ["https://example.com/", "https://example.com/about"])
        page.locator("#crawl-mode-auto").check()
        expect(page.locator("#target-preview")).to_contain_text("自動クロール")
        expect(page.locator("#target-preview-list")).to_contain_text("https://example.com/")
        expect(page.locator("#target-preview-list")).not_to_contain_text(
            "https://example.com/about"
        )

    def test_switching_back_to_selected_restores_checklist(self, page: Page) -> None:
        _enter_step2_with_discovered(page, ["https://example.com/", "https://example.com/about"])
        page.locator("#crawl-mode-auto").check()
        page.locator("#crawl-mode-selected").check()
        expect(page.locator("#discovered-url-panel")).to_be_visible()
        expect(page.locator("#crawl-mode-auto-fields")).to_be_hidden()


class TestParallelismAndEtaEstimate:
    """並列数選択と所要時間目安の表示（ドッグフーディング要望: 分析時間を
    短縮したい、への対応）。"""

    def test_eta_estimate_shown_for_selected_urls(self, page: Page) -> None:
        _enter_step2_with_discovered(page, ["https://example.com/", "https://example.com/about"])
        expect(page.locator("#target-preview-eta")).to_contain_text("所要目安")
        expect(page.locator("#target-preview-eta")).to_contain_text("分")

    def test_increasing_parallelism_shortens_eta_estimate(self, page: Page) -> None:
        urls = [f"https://example.com/page{i}" for i in range(20)]
        _enter_step2_with_discovered(page, urls)
        page.locator("#crawl-parallelism").select_option("1")
        eta_slow = page.locator("#target-preview-eta").inner_text()
        page.locator("#crawl-parallelism").select_option("4")
        eta_fast = page.locator("#target-preview-eta").inner_text()
        assert eta_slow != eta_fast, "並列数を上げても目安時間の表示が変化していない"
