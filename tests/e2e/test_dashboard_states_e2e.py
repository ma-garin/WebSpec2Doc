"""E2E: ダッシュボード解析履歴の状態表示（Phase D 状態体系化）。

- 履歴 API 失敗時は ui-states.js の .ui-error（再試行ボタンつき）を表示する。
- 再試行で成功応答に切り替わると、KPI カードと履歴テーブルが描画される。

実行方法: make verify-ui
"""

from __future__ import annotations

import json
import os

from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")

_OK_BODY = {
    "items": [
        {
            "domain": "state.example.com",
            "screens": 3,
            "fields": 5,
            "snapshot_count": 1,
            "has_diff": False,
            "updated": "2026-07-01 10:00",
            "updated_ts": 1783300000,
            "formats": [],
        }
    ]
}


class TestDashboardHistoryStates:
    def test_error_then_retry_recovers(self, page: Page) -> None:
        # 最初の /api/history を 500 で失敗させる
        state = {"fail": True}

        def _handler(route):  # type: ignore[no-untyped-def]
            if state["fail"]:
                route.fulfill(status=500, content_type="application/json", body="{}")
            else:
                route.fulfill(
                    status=200, content_type="application/json", body=json.dumps(_OK_BODY)
                )

        page.route("**/api/history", _handler)
        page.goto(BASE_URL, wait_until="networkidle")

        # エラー状態（再試行ボタンつき）が表示される
        error = page.locator("#history-body .ui-error")
        expect(error).to_be_visible(timeout=8_000)
        retry = error.locator("button", has_text="再試行")
        expect(retry).to_be_visible()

        # 応答を成功に切り替えて再試行 → テーブル（＋KPIカード）が描画される
        state["fail"] = False
        retry.click()
        expect(page.locator("#history-body table.data")).to_be_visible(timeout=8_000)
        expect(page.locator("#history-body .stat-card")).to_have_count(4)
        expect(page.locator("#history-body .ui-error")).to_have_count(0)
