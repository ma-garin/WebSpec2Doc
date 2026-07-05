"""実行結果レポート画面 新タブ基盤（7タブ・永続パネル・ディープリンク）の E2E テスト。

対象:
    - 7タブ構成（overview / screens / test-design / flow / runs / coverage / history）
    - 複合タブのサブタブ切替（test-design: matrix/summary/detail 等）
    - 永続パネルによる状態保持（タブ切替でマトリクスの検索条件が消えない）
    - ディープリンク #report/<domain>/<tab>/<sub> と旧8タブ名の互換リダイレクト

実行方法:
    make verify-ui
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://127.0.0.1:8765"
FIXTURE_DOMAIN = "e2e-report-tabs.example.com"
ROOT = Path(__file__).parent.parent.parent
FIXTURE_DIR = ROOT / "output" / FIXTURE_DOMAIN

FIXTURE_REPORT = {
    "meta": {
        "target_url": f"https://{FIXTURE_DOMAIN}/",
        "crawled_at": "2026-07-01 12:00",
        "crawl_depth": 1,
        "max_pages": 5,
        "screen_count": 2,
    },
    "screens": [
        {
            "page_id": "P001",
            "title": "トップ",
            "url": f"https://{FIXTURE_DOMAIN}/",
            "is_canonical": True,
            "headings": ["ようこそ"],
            "buttons": ["ログイン"],
            "forms": [],
            "transitions": {"to": ["P002"], "from": []},
        },
        {
            "page_id": "P002",
            "title": "お問い合わせ",
            "url": f"https://{FIXTURE_DOMAIN}/contact",
            "is_canonical": True,
            "headings": ["お問い合わせ"],
            "buttons": ["送信"],
            "forms": [
                {
                    "action": "/contact",
                    "method": "post",
                    "fields": [
                        {
                            "name": "email",
                            "field_type": "email",
                            "required": True,
                            "maxlength": "100",
                            "locators": ["#email"],
                            "test_conditions": ["必須入力", "メール形式"],
                        },
                        {
                            "name": "message",
                            "field_type": "textarea",
                            "required": False,
                            "locators": ["#message"],
                            "test_conditions": ["最大長"],
                        },
                    ],
                }
            ],
            "transitions": {"to": [], "from": ["P001"]},
        },
    ],
}


@pytest.fixture(scope="module", autouse=True)
def report_fixture() -> Generator[None, None, None]:
    """最小構成の report.json を output/ に配置し、テスト後に削除する。"""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "report.json").write_text(
        json.dumps(FIXTURE_REPORT, ensure_ascii=False), encoding="utf-8"
    )
    yield
    shutil.rmtree(FIXTURE_DIR, ignore_errors=True)


def _open_report(page: Page, suffix: str = "") -> None:
    page.goto(f"{BASE_URL}/#report/{FIXTURE_DOMAIN}{suffix}")
    expect(page.locator("#result-panel")).to_be_visible()
    expect(page.locator("#r-domain")).to_have_text(FIXTURE_DOMAIN)


class TestTabStructure:
    """6タブ構成とパネルホストの検証。"""

    def test_seven_tabs_present(self, page: Page) -> None:
        """既定表示は7タブ（文書突合タブは doc_fusion.json が無いため非表示）。"""
        _open_report(page)
        visible_tabs = page.locator(".result-tabs .result-tab:visible")
        expect(visible_tabs).to_have_count(7)
        keys = [visible_tabs.nth(i).get_attribute("data-tab") for i in range(7)]
        assert keys == [
            "overview",
            "screens",
            "test-design",
            "flow",
            "runs",
            "coverage",
            "history",
        ]
        expect(page.locator('.result-tab[data-tab="doc-fusion"]')).to_be_hidden()

    def test_no_javascript_errors_on_report(self, page: Page) -> None:
        js_errors: list[str] = []
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        _open_report(page)
        page.wait_for_load_state("networkidle")
        assert js_errors == [], f"JavaScript エラー: {js_errors}"

    def test_overview_renders_inventory(self, page: Page) -> None:
        _open_report(page)
        expect(page.locator("#rp-overview")).to_be_visible()
        expect(page.locator("#rp-overview")).to_contain_text("画面インベントリ")
        expect(page.locator("#rp-overview")).to_contain_text("P001")

    def test_panels_toggle_with_tabs(self, page: Page) -> None:
        _open_report(page)
        page.locator('.result-tab[data-tab="screens"]').click()
        expect(page.locator("#rp-screens")).to_be_visible()
        expect(page.locator("#rp-overview")).to_be_hidden()
        page.locator('.result-tab[data-tab="overview"]').click()
        expect(page.locator("#rp-overview")).to_be_visible()
        expect(page.locator("#rp-screens")).to_be_hidden()


class TestSubTabs:
    """複合タブのサブタブ切替の検証。"""

    def test_test_design_subtabs(self, page: Page) -> None:
        _open_report(page)
        page.locator('.result-tab[data-tab="test-design"]').click()
        expect(page.locator("#rp-test-design-matrix")).to_be_visible()
        expect(page.locator("#mx-search")).to_be_visible()  # 条件マトリクスのツールバー

        page.locator('#rp-test-design .result-subtab[data-sub="summary"]').click()
        expect(page.locator("#rp-test-design-summary")).to_be_visible()
        expect(page.locator("#rp-test-design-matrix")).to_be_hidden()
        expect(page.locator("#rp-test-design-summary")).to_contain_text("テスト設計技法マトリクス")

        page.locator('#rp-test-design .result-subtab[data-sub="detail"]').click()
        expect(page.locator("#rp-test-design-detail")).to_be_visible()
        expect(page.locator("#rp-test-design-detail")).to_contain_text("画面別 推奨技法と根拠")

    def test_screens_gallery_subtab(self, page: Page) -> None:
        """スクリーンショットギャラリーが配線されている（旧デッドコードの復活）。"""
        _open_report(page)
        page.locator('.result-tab[data-tab="screens"]').click()
        expect(page.locator("#rp-screens-spec")).to_be_visible()
        page.locator('#rp-screens .result-subtab[data-sub="gallery"]').click()
        expect(page.locator("#rp-screens-gallery")).to_be_visible()
        # スクショ未生成のフィクスチャなので空メッセージが出る（未配線なら何も描画されない）
        expect(page.locator("#rp-screens-gallery")).to_contain_text("スクリーンショット")

    def test_screens_spec_transitions_show_screen_titles_not_raw_ids(self, page: Page) -> None:
        """遷移先/遷移元は「P002」等の内部IDのままではなく画面名で表示する。"""
        _open_report(page)
        page.locator('.result-tab[data-tab="screens"]').click()
        page.locator("#rpt-list .rpt-list-item").first.click()
        expect(page.locator("#rpt-detail .rpt-transitions")).to_contain_text("お問い合わせ")
        expect(page.locator("#rpt-detail .rpt-transitions")).not_to_contain_text("P002")

    def test_flow_subtabs(self, page: Page) -> None:
        _open_report(page)
        page.locator('.result-tab[data-tab="flow"]').click()
        expect(page.locator("#rp-flow-diagram")).to_be_visible()
        page.locator('#rp-flow .result-subtab[data-sub="table"]').click()
        expect(page.locator("#rp-flow-table")).to_be_visible()
        expect(page.locator("#rp-flow-diagram")).to_be_hidden()

    def test_runs_tab_empty_state_with_autorun_cta(self, page: Page) -> None:
        """テスト実行タブ: 未実行時はリッチ空状態 + AutoRun 導線。"""
        _open_report(page)
        page.locator('.result-tab[data-tab="runs"]').click()
        expect(page.locator("#rp-runs .ui-empty")).to_be_visible()
        expect(page.locator("#rp-runs")).to_contain_text("AutoRun")


class TestRunsTab:
    """テスト実行タブ（AutoRun 結果の一元表示）。"""

    def _write_playwright_report(self, payload: dict) -> Path:
        qa_dir = FIXTURE_DIR / "qa_process"
        qa_dir.mkdir(parents=True, exist_ok=True)
        path = qa_dir / "playwright_report.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return qa_dir

    def test_runs_tab_shows_results_and_pass_rate(self, page: Page) -> None:
        qa_dir = self._write_playwright_report(
            {
                "ok": False,
                "passed": 3,
                "failed": 1,
                "skipped": 0,
                "total": 4,
                "duration_ms": 12000,
                "tests": [
                    {"title": "トップ表示", "status": "passed", "duration_ms": 900, "error": ""},
                    {
                        "title": "フォーム送信",
                        "status": "failed",
                        "duration_ms": 2100,
                        "error": "locator #submit not found",
                    },
                ],
            }
        )
        try:
            _open_report(page, "/runs")
            expect(page.locator("#rp-runs")).to_contain_text("テスト実行結果")
            expect(page.locator("#rp-runs .runs-passrate")).to_be_visible()
            expect(page.locator("#rp-runs")).to_contain_text("75%")
            expect(page.locator("#rp-runs .runs-table")).to_contain_text("フォーム送信")
            # 失敗テストのエラーは折りたたみで確認できる
            page.locator("#rp-runs .runs-error-detail summary").first.click()
            expect(page.locator("#rp-runs")).to_contain_text("locator #submit not found")
        finally:
            shutil.rmtree(qa_dir, ignore_errors=True)

    def test_runs_tab_unavailable_is_warning_not_success(self, page: Page) -> None:
        """Playwright 未セットアップは PASS 0/FAIL 0 の成功表示ではなく警告として描画する。"""
        qa_dir = self._write_playwright_report(
            {
                "ok": False,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "total": 0,
                "tests": [],
                "error": "@playwright/test が見つかりません",
                "unavailable": True,
            }
        )
        try:
            _open_report(page, "/runs")
            expect(page.locator("#rp-runs .runs-unavailable-card")).to_be_visible()
            expect(page.locator("#rp-runs")).to_contain_text("テストを実行できませんでした")
            expect(page.locator("#rp-runs")).to_contain_text("セットアップ手順")
            expect(page.locator("#rp-runs .runs-passrate")).not_to_be_visible()
        finally:
            shutil.rmtree(qa_dir, ignore_errors=True)

    def test_runs_tab_zero_result_with_error_shows_error_not_success(self, page: Page) -> None:
        """AutoRunで188件実行したのに結果が0/0/0で表示された致命的UX破綻の再発防止。
        解析失敗などで error があり total==0 の場合、PASS率リングやカードではなく
        「実行エラー」を明示する。"""
        qa_dir = self._write_playwright_report(
            {
                "ok": False,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "total": 0,
                "tests": [],
                "error": "実行結果を解析できませんでした（終了コード 1）",
            }
        )
        try:
            _open_report(page, "/runs")
            expect(page.locator("#rp-runs")).to_contain_text("実行エラー")
            expect(page.locator("#rp-runs")).to_contain_text("実行結果を解析できませんでした")
            expect(page.locator("#rp-runs .runs-passrate")).not_to_be_visible()
        finally:
            shutil.rmtree(qa_dir, ignore_errors=True)

    def test_runs_tab_interrupted_shows_partial_banner(self, page: Page) -> None:
        """全体タイムアウトで中断され部分結果が回収された場合、中断バナーと
        回収できた分の結果（PASS率・テーブル）の両方を表示する。"""
        qa_dir = self._write_playwright_report(
            {
                "ok": False,
                "passed": 2,
                "failed": 0,
                "skipped": 0,
                "total": 2,
                "tests": [
                    {"title": "トップ表示", "status": "passed", "duration_ms": 900, "error": ""},
                    {"title": "検索", "status": "passed", "duration_ms": 800, "error": ""},
                ],
                "error": "テスト実行が制限時間 600秒 に達したため中断しました。188件中2件まで実行済みです。",
                "interrupted": True,
            }
        )
        try:
            _open_report(page, "/runs")
            expect(page.locator("#rp-runs")).to_contain_text("中断しました")
            expect(page.locator("#rp-runs .runs-passrate")).to_be_visible()
            expect(page.locator("#rp-runs .runs-table")).to_contain_text("トップ表示")
        finally:
            shutil.rmtree(qa_dir, ignore_errors=True)

    def test_overview_kpi_tile_shows_error_not_never_run(self, page: Page) -> None:
        """概要タブのKPIタイルは、error付き0/0/0結果を「未実行」のまま放置しない。"""
        qa_dir = self._write_playwright_report(
            {
                "ok": False,
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "total": 0,
                "tests": [],
                "error": "実行結果を解析できませんでした（終了コード 1）",
            }
        )
        try:
            _open_report(page)
            expect(page.locator("#k-runs-sub")).to_contain_text("実行エラー")
        finally:
            shutil.rmtree(qa_dir, ignore_errors=True)


class TestStatePreservation:
    """永続パネルによる状態保持の検証。"""

    def test_matrix_search_survives_tab_switch(self, page: Page) -> None:
        _open_report(page)
        page.locator('.result-tab[data-tab="test-design"]').click()
        search = page.locator("#mx-search")
        expect(search).to_be_visible()
        search.fill("email")
        # 別タブへ移動して戻る
        page.locator('.result-tab[data-tab="overview"]').click()
        page.locator('.result-tab[data-tab="test-design"]').click()
        expect(page.locator("#mx-search")).to_have_value("email")


class TestDeepLink:
    """ディープリンクと旧タブ名互換の検証。"""

    def test_hash_updates_on_tab_switch(self, page: Page) -> None:
        _open_report(page)
        page.locator('.result-tab[data-tab="test-design"]').click()
        page.wait_for_function("() => location.hash.includes('/test-design/matrix')")

    def test_deep_link_opens_subtab(self, page: Page) -> None:
        _open_report(page, "/test-design/detail")
        expect(page.locator("#rp-test-design-detail")).to_be_visible()
        expect(page.locator('#rp-test-design .result-subtab[data-sub="detail"]')).to_have_class(
            re.compile(r"is-active")
        )

    def test_legacy_tab_names_redirect(self, page: Page) -> None:
        """旧8タブ時代の共有URL（#report/<domain>/matrix 等）が新タブへ解決される。"""
        _open_report(page, "/matrix")
        expect(page.locator("#rp-test-design-matrix")).to_be_visible()
        page.wait_for_function("() => location.hash.includes('/test-design/matrix')")

    def test_legacy_transition_table_redirect(self, page: Page) -> None:
        _open_report(page, "/transition-table")
        expect(page.locator("#rp-flow-table")).to_be_visible()

    def test_unknown_tab_falls_back_to_overview(self, page: Page) -> None:
        _open_report(page, "/no-such-tab")
        expect(page.locator("#rp-overview")).to_be_visible()
