"""列見出し・設定項目の「ⓘ」ツールチップ E2E テスト（L3 システムテスト）。

対象（実ユーザーのドッグフーディング報告）:
    品質観点画面の列見出し（発火条件・推奨確認・自動化・Trace 等）が専門用語で
    意味が分からない → 見出しに ⓘ アイコンを追加し、ホバー/フォーカスで説明を
    表示するツールチップパターンを新設（static/js/core.js の infoTip・
    static/js/qa-tools.js）。

実行方法:
    make verify-ui
"""

from __future__ import annotations

from playwright.sync_api import Page, expect

BASE_URL = "http://127.0.0.1:8765"


class TestQualityViewpointsInfoTip:
    def test_column_headers_have_info_tip_with_explanation(self, page: Page) -> None:
        page.goto(f"{BASE_URL}/qa-quality")
        page.wait_for_selector("#qa-quality-content")
        page.evaluate(
            """() => renderQaQualityTool({
                quality_viewpoints: {
                    items: [
                        {id: 'V1', viewpoint: '必須未入力', category: '入力検証',
                         trigger: '未入力のまま送信', recommendation: 'エラー表示',
                         automation: '自動', trace_id: 'P001'},
                    ],
                    screen_risks: [],
                    questions: [],
                },
            })"""
        )
        content = page.locator("#qa-quality-content")
        tips = content.locator(".info-tip")
        expect(tips).to_have_count(4)  # 発火条件・推奨確認・自動化・Trace
        for i in range(4):
            tip_text = tips.nth(i).get_attribute("data-tip")
            assert tip_text, f"info-tip {i} has no data-tip explanation"

    def test_info_tip_is_keyboard_focusable(self, page: Page) -> None:
        """マウス操作前提にせず、Tabフォーカスでも説明が読めること。"""
        page.goto(f"{BASE_URL}/qa-quality")
        page.wait_for_selector("#qa-quality-content")
        page.evaluate(
            """() => renderQaQualityTool({
                quality_viewpoints: {
                    items: [
                        {id: 'V1', viewpoint: '必須未入力', category: '入力検証',
                         trigger: '未入力のまま送信', recommendation: 'エラー表示',
                         automation: '自動', trace_id: 'P001'},
                    ],
                    screen_risks: [],
                    questions: [],
                },
            })"""
        )
        first_tip = page.locator("#qa-quality-content .info-tip").first
        first_tip.focus()
        expect(first_tip).to_be_focused()


class TestAutoRunFieldsInfoTip:
    def test_depth_max_pages_timeout_have_info_tips(self, page: Page) -> None:
        """深さ・最大ページ・1テストあたりの制限時間の意味が分からない、
        というドッグフーディング指摘への対応。"""
        page.goto(f"{BASE_URL}/auto-run")
        page.wait_for_selector("#autorun-depth")
        depth_tip = page.locator("label[for='autorun-depth'] .info-tip")
        max_pages_tip = page.locator("label[for='autorun-max-pages'] .info-tip")
        expect(depth_tip).to_be_visible()
        expect(max_pages_tip).to_be_visible()
        assert depth_tip.get_attribute("data-tip")
        assert max_pages_tip.get_attribute("data-tip")
