"""Sprint 3 レーンD（UI統合）の E2E テスト。

対象:
    - 技法別設計（MBT）サブタブ: 技法チップ → 対象画面 → モーダル（BVA/DT/PW/ST）
    - カバレッジヒートマップ サブタブ: iframe 描画（解析/AutoRun）
    - 履歴・差分の比較モード切替（現新比較 / 簡易ドリフト差分）
    - 設定「テスト設計」タブ: 保存往復
    - 既存6タブ構成が不変であること（回帰）

実行方法:
    make verify-ui
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")
FIXTURE_DOMAIN = "e2e-sprint3-ui.example.com"
ROOT = Path(__file__).parent.parent.parent
FIXTURE_DIR = ROOT / "output" / FIXTURE_DOMAIN

FIXTURE_SCREENS = [
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
                        "name": "name",
                        "field_type": "text",
                        "required": True,
                        "maxlength": "50",
                        "locators": ["#name"],
                        "test_conditions": ["必須入力"],
                    },
                ],
            }
        ],
        "transitions": {"to": [], "from": ["P001"]},
    },
]

FIXTURE_REPORT = {
    "meta": {
        "target_url": f"https://{FIXTURE_DOMAIN}/",
        "crawled_at": "2026-07-06 09:00",
        "crawl_depth": 1,
        "max_pages": 5,
        "screen_count": 2,
    },
    "screens": FIXTURE_SCREENS,
}


@pytest.fixture(scope="module", autouse=True)
def report_fixture() -> Generator[None, None, None]:
    """report.json と 2 スナップショットを配置し、テスト後に削除する。"""
    (FIXTURE_DIR / "snapshots").mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "report.json").write_text(
        json.dumps(FIXTURE_REPORT, ensure_ascii=False), encoding="utf-8"
    )
    # 現新比較モードの radio は snapshots >= 2 件で表示される
    for ts in ("20260706-090000", "20260706-093000"):
        (FIXTURE_DIR / "snapshots" / f"{ts}.json").write_text(
            json.dumps(FIXTURE_SCREENS, ensure_ascii=False), encoding="utf-8"
        )
    yield
    shutil.rmtree(FIXTURE_DIR, ignore_errors=True)


def _open_report(page: Page, suffix: str = "") -> None:
    page.goto(f"{BASE_URL}/#report/{FIXTURE_DOMAIN}{suffix}")
    expect(page.locator("#result-panel")).to_be_visible()
    expect(page.locator("#r-domain")).to_have_text(FIXTURE_DOMAIN)


class TestRegressionTabsUnchanged:
    def test_six_top_tabs_preserved(self, page: Page) -> None:
        """サブタブ追加後も上位タブは6のまま（doc-fusion は非表示）。"""
        _open_report(page)
        expect(page.locator(".result-tabs .result-tab:visible")).to_have_count(6)


class TestMbtSubtab:
    def test_mbt_subtab_shows_chips_and_modal(self, page: Page) -> None:
        js_errors: list[str] = []
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        _open_report(page)
        page.locator('.result-tab[data-tab="test-design"]').click()
        page.locator('#rp-test-design .result-subtab[data-sub="mbt"]').click()
        # 技法チップが描画される（/api/test-design を取得後）
        expect(page.locator("#rp-test-design-mbt .mbt-chip").first).to_be_visible()
        # 既定 active（bva）の対象画面 P002（email maxlength=100 の境界値）
        first_row = page.locator("#rp-test-design-mbt .mbt-screen-row").first
        expect(first_row).to_be_visible()
        first_row.click()
        # モーダルが開き、設計テーブルが表示される
        expect(page.locator(".mbt-modal-overlay")).to_be_visible()
        expect(page.locator(".mbt-modal .mbt-modal-body")).to_be_visible()
        page.locator(".mbt-modal-close").click()
        expect(page.locator(".mbt-modal-overlay")).to_have_count(0)
        assert js_errors == [], f"JavaScript エラー: {js_errors}"


class TestCoverageHeatmapSubtab:
    def test_coverage_subtab_renders_iframe(self, page: Page) -> None:
        _open_report(page)
        page.locator('.result-tab[data-tab="screens"]').click()
        page.locator('#rp-screens .result-subtab[data-sub="coverage"]').click()
        # 解析カバレッジの iframe が描画される
        expect(page.locator("#cov-frame iframe")).to_be_visible()
        # AutoRun へ切替
        page.locator('input[name="cov-kind"][value="autorun"]').check()
        expect(page.locator("#cov-frame iframe")).to_be_visible()


class TestComparisonModeToggle:
    def test_history_has_comparison_mode_radios(self, page: Page) -> None:
        _open_report(page, "/history")
        # snapshots 2 件 → 比較モードの radio（現新比較/簡易ドリフト差分）が出る
        expect(page.locator('input[name="tl-mode"][value="comparison"]')).to_be_visible()
        expect(page.locator('input[name="tl-mode"][value="diff"]')).to_be_visible()
        # 既定は現新比較
        expect(page.locator('input[name="tl-mode"][value="comparison"]')).to_be_checked()
        # 簡易ドリフト差分へ切替できる
        page.locator('input[name="tl-mode"][value="diff"]').check()
        expect(page.locator('input[name="tl-mode"][value="diff"]')).to_be_checked()


class TestSettingsTestDesignTab:
    def test_test_design_settings_save_roundtrip(self, page: Page) -> None:
        page.goto(BASE_URL)
        page.locator('.app-nav-item[data-view="settings"]').first.click()
        page.locator('.set-tab[data-tab="test-design"]').click()
        expect(page.locator("#set-panel-test-design")).to_be_visible()
        # 値を変更して保存
        page.locator("#td-bva-offset").fill("2")
        page.locator("#td-pw-strength").select_option("3")
        page.locator("#save-test-design").click()
        msg = page.locator("#test-design-msg")
        expect(msg).to_be_visible()
        expect(msg).to_contain_text("保存")
