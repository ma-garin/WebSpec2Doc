"""実行履歴の種別タブ分離（R3-16）の E2E テスト。

対象:
    - templates/partials/view-run-history.html の種別タブ（旧 select を置換）
    - static/js/view-run-history.js の初期表示（既定タブ=解析）とタブ切替・
      localStorage 永続（wsd_rh_type）

実行方法:
    make verify-ui
"""

from __future__ import annotations

import json
import os
import re

from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")

MOCK_RUNS = {
    "runs": [
        {
            "type": "crawl",
            "domain": "a.example.com",
            "timestamp": "2026-07-01 10:00",
            "status": "complete",
            "summary": {"screen_count": 3, "test_condition_count": 5, "document_count": 4},
            "link": "",
        },
        {
            "type": "autorun",
            "domain": "b.example.com",
            "timestamp": "2026-07-01 11:00",
            "status": "complete",
            "summary": {"passed": 2, "failed": 0, "total": 2, "duration_sec": 5},
            "link": "",
        },
    ]
}


def _mock_runs(page: Page) -> None:
    page.route(
        "**/api/history/runs",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(MOCK_RUNS)
        ),
    )


def _open_run_history(page: Page) -> None:
    page.goto(BASE_URL)
    _mock_runs(page)
    page.locator("#nav-run-history-btn").click()
    page.wait_for_selector("#rh-tbody tr")


class TestRunHistoryTypeTabs:
    def test_default_tab_is_crawl_and_switches(self, page: Page) -> None:
        _open_run_history(page)

        # 初期表示は「解析」タブで、解析種別のみ表示される
        expect(page.locator('.rh-type-tab[data-type="crawl"]')).to_have_class(
            re.compile(r"is-active")
        )
        rows = page.locator("#rh-tbody tr")
        expect(rows).to_have_count(1)
        expect(rows.first.locator(".rh-type-badge")).to_have_class(re.compile(r"rh-type-crawl"))

        # AutoRun タブへ切替
        page.locator('.rh-type-tab[data-type="autorun"]').click()
        expect(page.locator('.rh-type-tab[data-type="autorun"]')).to_have_class(
            re.compile(r"is-active")
        )
        expect(page.locator('.rh-type-tab[data-type="crawl"]')).not_to_have_class(
            re.compile(r"is-active")
        )
        rows2 = page.locator("#rh-tbody tr")
        expect(rows2).to_have_count(1)
        expect(rows2.first.locator(".rh-type-badge")).to_have_class(re.compile(r"rh-type-autorun"))

        # 選択が localStorage に記憶される
        stored = page.evaluate("localStorage.getItem('wsd_rh_type')")
        assert stored == "autorun"

    def test_all_tab_shows_every_type(self, page: Page) -> None:
        _open_run_history(page)
        page.locator('.rh-type-tab[data-type="all"]').click()
        expect(page.locator("#rh-tbody tr")).to_have_count(2)

    def test_selection_persists_across_reload(self, page: Page) -> None:
        _open_run_history(page)
        page.locator('.rh-type-tab[data-type="autorun"]').click()
        expect(page.locator('.rh-type-tab[data-type="autorun"]')).to_have_class(
            re.compile(r"is-active")
        )

        # 再読み込み後も選択した種別タブが復元される
        _mock_runs(page)
        page.reload()
        page.locator("#nav-run-history-btn").click()
        page.wait_for_selector("#rh-tbody tr")
        expect(page.locator('.rh-type-tab[data-type="autorun"]')).to_have_class(
            re.compile(r"is-active")
        )
