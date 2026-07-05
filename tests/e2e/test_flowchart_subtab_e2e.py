"""画面遷移タブ「フローチャート」サブタブ（S3-3 / R2-12）の E2E テスト。

対象:
    - 遷移図タブ内のサブタブに「フローチャート」が存在する
    - クリックで active になり、フローチャート図（Mermaid flowchart TD）が描画される
    - 既存サブタブ（シーケンス/コミュニケーション/アクティビティ/観点マップ）の切替が壊れていない

実行方法:
    make verify-ui
"""

from __future__ import annotations

import json
import os
import re
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")
FIXTURE_DOMAIN = "e2e-flowchart.example.com"
ROOT = Path(__file__).parent.parent.parent
FIXTURE_DIR = ROOT / "output" / FIXTURE_DOMAIN

FIXTURE_REPORT = {
    "meta": {
        "target_url": f"https://{FIXTURE_DOMAIN}/",
        "crawled_at": "2026-07-06 12:00",
        "crawl_depth": 1,
        "max_pages": 5,
        "screen_count": 3,
    },
    "screens": [
        {
            "page_id": "P001",
            "title": "トップ",
            "url": f"https://{FIXTURE_DOMAIN}/",
            "is_canonical": True,
            "headings": ["ようこそ"],
            "buttons": ["お問い合わせへ"],
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
                    "action": "/contact/done",
                    "method": "post",
                    "fields": [
                        {
                            "name": "email",
                            "field_type": "email",
                            "required": True,
                            "locators": ["#email"],
                            "test_conditions": ["必須入力"],
                        }
                    ],
                }
            ],
            "transitions": {"to": ["P003"], "from": ["P001"]},
        },
        {
            "page_id": "P003",
            "title": "送信完了",
            "url": f"https://{FIXTURE_DOMAIN}/contact/done",
            "is_canonical": True,
            "headings": ["送信が完了しました"],
            "buttons": [],
            "forms": [],
            "transitions": {"to": [], "from": ["P002"]},
        },
    ],
}


@pytest.fixture(scope="module", autouse=True)
def report_fixture() -> Generator[None, None, None]:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "report.json").write_text(
        json.dumps(FIXTURE_REPORT, ensure_ascii=False), encoding="utf-8"
    )
    yield
    shutil.rmtree(FIXTURE_DIR, ignore_errors=True)


def _open_flow(page: Page) -> None:
    page.goto(f"{BASE_URL}/#report/{FIXTURE_DOMAIN}")
    expect(page.locator("#result-panel")).to_be_visible()
    page.locator('.result-tab[data-tab="flow"]').click()
    expect(page.locator("#rp-flow-diagram")).to_be_visible()


class TestFlowchartSubtab:
    def test_flowchart_subtab_present(self, page: Page) -> None:
        """遷移図の内部サブタブに「フローチャート」ボタンが存在する。"""
        _open_flow(page)
        btn = page.locator('.uml-subtab[data-uml="flowchart"]')
        expect(btn).to_be_visible()
        expect(btn).to_contain_text("フローチャート")

    def test_flowchart_renders_diagram(self, page: Page) -> None:
        """フローチャートをクリックすると active になり、図（SVG）が描画される。"""
        _open_flow(page)
        page.locator('.uml-subtab[data-uml="flowchart"]').click()
        expect(page.locator('.uml-subtab[data-uml="flowchart"]')).to_have_class(
            re.compile(r"is-active")
        )
        # パネル見出しにメタ情報（フローチャート）が出る
        expect(page.locator("#uml-diagram-area")).to_contain_text("フローチャート")
        # Mermaid が描画した SVG（失敗時はソースの <pre> フォールバック）を待つ
        expect(
            page.locator("#uml-render-target svg, #uml-render-target pre.uml-source")
        ).to_have_count(1, timeout=10000)

    def test_existing_subtabs_still_switch(self, page: Page) -> None:
        """既存サブタブ（アクティビティ/観点マップ）への切替が壊れていない。"""
        _open_flow(page)
        page.locator('.uml-subtab[data-uml="activity"]').click()
        expect(page.locator("#uml-diagram-area")).to_contain_text("アクティビティ図")
        page.locator('.uml-subtab[data-uml="viewpoints"]').click()
        expect(page.locator("#uml-diagram-area")).to_contain_text("テスト観点マップ")
