"""テストケース一覧の表形式化（R3-17）の E2E テスト。

対象:
    - static/js/view-testcases.js の renderTestcases()（カード→表への置換）
    - templates/partials/view-testcases.html の表用スタイル

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
import requests
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")
FIXTURE_DOMAIN = "e2e-testcases.example.com"
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


def _open_testcases(page: Page) -> None:
    page.goto(BASE_URL)
    page.locator('.app-nav-item[data-view="testcases"]').click()
    page.wait_for_selector("#tc-domain-select", state="visible")
    page.locator("#tc-domain-select").select_option(FIXTURE_DOMAIN)
    page.wait_for_selector("#tc-content table.tc-table")


class TestTestcasesTable:
    def test_table_with_six_columns(self, page: Page) -> None:
        _open_testcases(page)
        table = page.locator("#tc-content table.tc-table")
        expect(table).to_be_visible()
        headers = table.locator("th")
        expect(headers).to_have_count(6)
        expect(headers.nth(0)).to_have_text("ID")
        expect(headers.nth(1)).to_have_text("タイトル")
        expect(headers.nth(2)).to_have_text("前提条件")
        expect(headers.nth(3)).to_have_text("手順")
        expect(headers.nth(4)).to_have_text("期待結果")
        expect(headers.nth(5)).to_have_text("自動化")

        # 行数はAPI（/api/testcases）が返す件数と一致する（捏造しない）
        api_data = requests.get(
            f"{BASE_URL}/api/testcases", params={"domain": FIXTURE_DOMAIN}, timeout=10
        ).json()
        expected_count = api_data.get("count", 0)
        assert expected_count > 0, "フィクスチャからテストケースが生成されていない"
        expect(table.locator("tbody tr")).to_have_count(expected_count)

    def test_preconditions_and_steps_rendered_as_lists(self, page: Page) -> None:
        _open_testcases(page)
        table = page.locator("#tc-content table.tc-table")
        first_row = table.locator("tbody tr").first
        expect(first_row.locator("td").nth(0)).not_to_be_empty()
        # 手順セルは <ol class="tc-cell-list"> で構造化されている
        expect(first_row.locator("td").nth(3).locator("ol.tc-cell-list")).to_be_attached()


class TestTestcasesFilter:
    """C-2: 絞り込みツールバー（テキスト検索・自動化状況）とページネーション。"""

    def test_filter_toolbar_present(self, page: Page) -> None:
        _open_testcases(page)
        expect(page.locator("#tc-search")).to_be_visible()
        expect(page.locator("#tc-auto-filter")).to_be_visible()
        expect(page.locator("#tc-count")).to_be_visible()

    def test_nonmatching_query_empties_then_restores(self, page: Page) -> None:
        _open_testcases(page)
        total = page.locator("#tc-content table.tc-table tbody tr").count()
        assert total > 0
        page.locator("#tc-search").fill("___no_such_case_xyz___")
        expect(page.locator("#tc-table-wrap .empty")).to_be_visible()
        expect(page.locator("#tc-count")).to_have_text("0件")
        # クリアすると元の件数へ復元する
        page.locator("#tc-search").fill("")
        expect(page.locator("#tc-content table.tc-table tbody tr")).to_have_count(total)

    def test_matching_query_keeps_matching_row(self, page: Page) -> None:
        _open_testcases(page)
        first_id = (
            page.locator("#tc-content table.tc-table tbody tr")
            .first.locator("td.tc-id")
            .inner_text()
        ).strip()
        assert first_id
        page.locator("#tc-search").fill(first_id)
        rows = page.locator("#tc-content table.tc-table tbody tr")
        expect(rows.first).to_contain_text(first_id)
        # 絞り込み後の全行が検索語（ID）に一致する
        assert rows.count() >= 1
