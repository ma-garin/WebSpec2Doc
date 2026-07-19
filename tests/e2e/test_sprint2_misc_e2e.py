"""Sprint 2 小物7件の E2E テスト。

対象:
    - キーボードショートカット拡張（Alt+A/Alt+H/1-9/ /・ヘルプ表記載）
    - テスト観点マップの凡例
    - シナリオ表QA観点の具体化（固定文言→実データ）
    - AutoRun観点セットの目的別グルーピング（推奨/その他）
    - ギャラリーの選択チェックボックス・一括エクスポートUI

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
FIXTURE_DOMAIN = "e2e-sprint2-misc.example.com"
ROOT = Path(__file__).parent.parent.parent
FIXTURE_DIR = ROOT / "output" / FIXTURE_DOMAIN

FIXTURE_REPORT = {
    "meta": {
        "target_url": f"https://{FIXTURE_DOMAIN}/",
        "crawled_at": "2026-07-05 12:00",
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
            "headings": [],
            "buttons": ["ログイン"],
            "forms": [],
            "transitions": {"to": ["P002"], "from": []},
        },
        {
            "page_id": "P002",
            "title": "会員登録",
            "url": f"https://{FIXTURE_DOMAIN}/signup",
            "is_canonical": True,
            "headings": [],
            "buttons": [],
            "forms": [],
            "transitions": {"to": [], "from": ["P001"]},
        },
    ],
}


@pytest.fixture(scope="module", autouse=True)
def report_fixture() -> Generator[None, None, None]:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "report.json").write_text(
        json.dumps(FIXTURE_REPORT, ensure_ascii=False), encoding="utf-8"
    )
    shots_dir = FIXTURE_DIR / "screenshots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    for page_id in ("P001", "P002"):
        (shots_dir / f"{page_id}.png").write_bytes(b"fake-png")
    yield
    shutil.rmtree(FIXTURE_DIR, ignore_errors=True)


def _open_report(page: Page, suffix: str = "") -> None:
    page.goto(f"{BASE_URL}/#report/{FIXTURE_DOMAIN}{suffix}")
    expect(page.locator("#result-panel")).to_be_visible()


class TestKeyboardShortcuts:
    """R2-01: ショートカット拡張。"""

    def test_help_overlay_lists_new_shortcuts(self, page: Page) -> None:
        page.goto(BASE_URL)
        page.keyboard.press("?")
        overlay = page.locator("#shortcut-overlay")
        expect(overlay).to_be_visible()
        expect(overlay).to_contain_text("AutoRunへ移動")
        expect(overlay).to_contain_text("実行履歴へ移動")
        expect(overlay).to_contain_text("検索欄にフォーカス")

    def test_alt_a_navigates_to_auto_run(self, page: Page) -> None:
        page.goto(BASE_URL)
        page.keyboard.press("Alt+a")
        expect(page.locator("#view-auto-run")).to_be_visible()

    def test_alt_h_navigates_to_run_history(self, page: Page) -> None:
        page.goto(BASE_URL)
        page.keyboard.press("Alt+h")
        expect(page.locator("#view-run-history")).to_be_visible()


class TestViewpointMapLegend:
    """R1-05: テスト観点マップに凡例を追加。"""

    def test_legend_shows_category_descriptions(self, page: Page) -> None:
        _open_report(page, "/flow")
        page.locator('button[data-uml="viewpoints"]').click()
        legend = page.locator(".viewpoint-legend")
        expect(legend).to_be_visible()
        expect(legend).to_contain_text("到達性")
        expect(legend).to_contain_text("リンク操作で期待画面へ到達できるか")


class TestScenarioViewpointSpecificity:
    """R2-11: シナリオ表QA観点の具体化（固定文言→実データ利用）。"""

    def test_viewpoint_column_uses_event_detail_and_screen_title(self, page: Page) -> None:
        _open_report(page, "/flow")
        table = page.locator(".uml-linked-table")
        expect(table).to_contain_text("リンククリックを押すと「会員登録」へ遷移する")
        expect(table).not_to_contain_text("リンク操作で期待画面へ到達する")


class TestAutorunViewpointGrouping:
    """R1-09: 観点セットを目的別（推奨/その他）にグルーピング。"""

    def test_options_grouped_when_both_kinds_present(self, page: Page) -> None:
        page.goto(BASE_URL)
        html_result = page.evaluate(
            """() => _autorunViewpointOptionsHtml([
                {id: 's1', name: '既定セット', published_version: 1, is_default: 1},
                {id: 's2', name: 'カスタムセット', published_version: 1, is_default: 0},
            ])"""
        )
        assert '<optgroup label="推奨セット">' in html_result
        assert '<optgroup label="その他のセット">' in html_result
        assert "既定セット" in html_result
        assert "カスタムセット" in html_result

    def test_no_groups_when_only_one_kind(self, page: Page) -> None:
        page.goto(BASE_URL)
        html_result = page.evaluate(
            """() => _autorunViewpointOptionsHtml([
                {id: 's1', name: 'セットA', published_version: 1, is_default: 1},
            ])"""
        )
        assert "<optgroup" not in html_result
        assert "セットA" in html_result


class TestGalleryBulkExport:
    """R2-09: ギャラリー一括エクスポート（チェックボックス・全選択/解除）。"""

    def test_toolbar_and_checkboxes_render(self, page: Page) -> None:
        _open_report(page, "/screens/gallery")
        expect(page.locator("#shots-select-all-btn")).to_be_visible()
        expect(page.locator("#shots-select-none-btn")).to_be_visible()
        expect(page.locator(".shots-select-cb")).to_have_count(2)

    def test_select_all_updates_count_and_none_clears(self, page: Page) -> None:
        _open_report(page, "/screens/gallery")
        page.locator("#shots-select-all-btn").click()
        expect(page.locator("#shots-select-count")).to_have_text("2")
        page.locator("#shots-select-none-btn").click()
        expect(page.locator("#shots-select-count")).to_have_text("0")
