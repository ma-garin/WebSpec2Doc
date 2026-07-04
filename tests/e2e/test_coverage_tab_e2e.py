"""SPEC-2-2: 探索カバレッジタブ（ヒートマップ・チャーター提案）の E2E テスト。

対象:
    - templates/partials/view-generate.html の data-tab="coverage" ボタン/パネル
    - static/js/view-coverage.js::renderCoverage
    - web/routes/report.py::api_result の files.exploration_heatmap / exploration_json

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
FIXTURE_DOMAIN = "e2e-coverage-tab.example.com"
EMPTY_FIXTURE_DOMAIN = "e2e-coverage-tab-empty.example.com"
ROOT = Path(__file__).parent.parent.parent
FIXTURE_DIR = ROOT / "output" / FIXTURE_DOMAIN
EMPTY_FIXTURE_DIR = ROOT / "output" / EMPTY_FIXTURE_DOMAIN

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
            "buttons": [],
            "forms": [],
            "transitions": {"to": ["P002"], "from": []},
        },
        {
            "page_id": "P002",
            "title": "チェックアウト",
            "url": f"https://{FIXTURE_DOMAIN}/checkout",
            "is_canonical": True,
            "headings": ["チェックアウト"],
            "buttons": [],
            "forms": [],
            "transitions": {"to": [], "from": ["P001"]},
        },
    ],
}

FIXTURE_COVERAGE = {
    "summary": {
        "total_screens": 2,
        "explored_screens": 1,
        "unexplored_screens": 1,
        "coverage_ratio": 0.5,
        "total_states": 0,
        "touched_states": 0,
        "session_events": 2,
    },
    "screens": [
        {
            "page_id": "P001",
            "url": f"https://{FIXTURE_DOMAIN}/",
            "title": "トップ",
            "visits": 1,
            "actions": 0,
            "states": [],
            "explored": True,
        },
        {
            "page_id": "P002",
            "url": f"https://{FIXTURE_DOMAIN}/checkout",
            "title": "チェックアウト",
            "visits": 0,
            "actions": 0,
            "states": [],
            "explored": False,
        },
    ],
    "unmatched_footprints": [],
    "charters": [
        {
            "page_id": "P002",
            "url": f"https://{FIXTURE_DOMAIN}/checkout",
            "title": "チェックアウト",
            "reason": "未探索 × ビジネスフロー通過画面",
            "flows": [{"flow_name": "ログイン→決済", "path_id": "TP012"}],
            "priority": "高",
        }
    ],
}

FIXTURE_HEATMAP_HTML = "<!doctype html><html><body>heatmap placeholder</body></html>"


@pytest.fixture(scope="module", autouse=True)
def coverage_fixture() -> Generator[None, None, None]:
    """探索カバレッジ集計済みドメインと未集計ドメインを output/ に配置する。"""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "report.json").write_text(
        json.dumps(FIXTURE_REPORT, ensure_ascii=False), encoding="utf-8"
    )
    (FIXTURE_DIR / "exploration_coverage.json").write_text(
        json.dumps(FIXTURE_COVERAGE, ensure_ascii=False), encoding="utf-8"
    )
    (FIXTURE_DIR / "exploration_heatmap.html").write_text(FIXTURE_HEATMAP_HTML, encoding="utf-8")

    EMPTY_FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (EMPTY_FIXTURE_DIR / "report.json").write_text(
        json.dumps(
            {
                "meta": {"target_url": f"https://{EMPTY_FIXTURE_DOMAIN}/"},
                "screens": [
                    {
                        "page_id": "P001",
                        "title": "トップ",
                        "url": f"https://{EMPTY_FIXTURE_DOMAIN}/",
                        "is_canonical": True,
                        "headings": [],
                        "buttons": [],
                        "forms": [],
                        "transitions": {"to": [], "from": []},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    yield
    shutil.rmtree(FIXTURE_DIR, ignore_errors=True)
    shutil.rmtree(EMPTY_FIXTURE_DIR, ignore_errors=True)


def _open_report(page: Page, domain: str, suffix: str = "") -> None:
    page.goto(f"{BASE_URL}/#report/{domain}{suffix}")
    expect(page.locator("#result-panel")).to_be_visible()
    expect(page.locator("#r-domain")).to_have_text(domain)


class TestCoverageTab:
    def test_coverage_tab_renders_heatmap(self, page: Page) -> None:
        _open_report(page, FIXTURE_DOMAIN)
        page.locator('.result-tab[data-tab="coverage"]').click()
        expect(page.locator("#rp-coverage")).to_be_visible()
        expect(page.locator("#rp-coverage iframe.coverage-heatmap-frame")).to_be_visible()
        expect(page.locator("#rp-coverage")).to_contain_text("次の探索チャーター（提案）")
        expect(page.locator("#rp-coverage")).to_contain_text("チェックアウト")

    def test_coverage_tab_charter_reason_visible(self, page: Page) -> None:
        _open_report(page, FIXTURE_DOMAIN)
        page.locator('.result-tab[data-tab="coverage"]').click()
        expect(page.locator("#rp-coverage")).to_contain_text("ログイン→決済")
        expect(page.locator("#rp-coverage")).to_contain_text("TP012")

    def test_coverage_tab_empty_state(self, page: Page) -> None:
        _open_report(page, EMPTY_FIXTURE_DOMAIN)
        page.locator('.result-tab[data-tab="coverage"]').click()
        expect(page.locator("#rp-coverage .ui-empty")).to_be_visible()
        expect(page.locator("#rp-coverage")).to_contain_text("探索セッション未集計")

    def test_coverage_deeplink(self, page: Page) -> None:
        _open_report(page, FIXTURE_DOMAIN, "/coverage")
        expect(page.locator("#rp-coverage")).to_be_visible()
        expect(page.locator('.result-tab[data-tab="coverage"]')).to_have_class(
            re.compile(r"is-active")
        )
