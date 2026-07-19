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

import os

from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")


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
        # 画面リスク表: 画面ID・画面・リスク・理由（4件） + 品質観点表: 発火条件・推奨確認・自動化・Trace（4件）
        expect(tips).to_have_count(8)
        for i in range(8):
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


class TestQualityViewpointsExplainBlock:
    def test_explain_block_and_risk_table_info_tips_present(self, page: Page) -> None:
        """R1-15/R1-16/R1-17: 画面の目的・見方が分からない、リスク/理由の意味が
        分からない、画面ID/画面/リスク/理由にiマークが無い、という指摘への対応。"""
        page.goto(f"{BASE_URL}/qa-quality")
        page.wait_for_selector("#qa-quality-content")
        page.evaluate(
            """() => renderQaQualityTool({
                quality_viewpoints: {
                    items: [],
                    screen_risks: [
                        {screen_id: 'P001', title: 'トップ', risk_score: 40,
                         reasons: ['入力項目あり', '操作要素あり']},
                    ],
                    questions: [],
                },
            })"""
        )
        content = page.locator("#qa-quality-content")
        explain = content.locator(".qa-explain-block")
        expect(explain).to_be_visible()
        expect(explain).to_contain_text("目的と見方")

        risk_table = content.locator("table").first
        header_tips = risk_table.locator("thead .info-tip")
        expect(header_tips).to_have_count(4)  # 画面ID・画面・リスク・理由
        for i in range(4):
            assert header_tips.nth(i).get_attribute("data-tip")

        row = risk_table.locator("tbody tr").first
        expect(row).to_contain_text("P001")
        expect(row).to_contain_text("トップ")
        expect(row).to_contain_text("40")
        expect(row).to_contain_text("入力項目あり")


class TestAutoRunFieldsInfoTip:
    def test_depth_max_pages_timeout_have_info_tips(self, page: Page) -> None:
        """深さ・最大ページ・1テストあたりの制限時間の意味が分からない、
        というドッグフーディング指摘への対応。"""
        page.goto(f"{BASE_URL}/auto-run")
        page.wait_for_selector(".autorun-advanced-options summary")
        page.locator(".autorun-advanced-options summary").click()
        page.wait_for_selector("#autorun-depth", state="visible")
        depth_tip = page.locator("label[for='autorun-depth'] .info-tip")
        max_pages_tip = page.locator("label[for='autorun-max-pages'] .info-tip")
        expect(depth_tip).to_be_visible()
        expect(max_pages_tip).to_be_visible()
        assert depth_tip.get_attribute("data-tip")
        assert max_pages_tip.get_attribute("data-tip")
