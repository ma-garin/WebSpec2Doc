"""URL履歴サジェスト（R3-15）の E2E テスト。

対象:
    - static/js/execution.js の saveUrlHistory() / populateUrlHistory()
    - #url-input の list="url-history-list"（datalist へのサジェスト反映）
    - templates/partials/view-settings.html の #set-url-history-limit
      （0を選ぶと保持件数を無効化し、既存履歴も削除する）

実行方法:
    make verify-ui
"""

from __future__ import annotations

import os
import re

from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")


def _open_generate(page: Page) -> None:
    page.locator("#nav-new-analysis-btn").click()
    page.wait_for_selector("#url-input", state="visible")


def _open_settings(page: Page) -> None:
    page.locator('.app-nav-item[data-view="settings"]').click()
    page.wait_for_selector("#set-tab-crawl", state="visible")
    page.locator('.set-tab[data-tab="crawl"]').click()
    page.wait_for_selector("#set-url-history-limit", state="visible")


class TestUrlHistorySuggestion:
    def test_datalist_populated_after_run(self, page: Page) -> None:
        page.goto(BASE_URL)
        # populateUrlHistory() はスクリプト読み込み時に一度実行済みのため、
        # ここで履歴を仕込んでから focus イベントで再反映させる。
        page.evaluate(
            """() => {
                localStorage.setItem('wsd_url_history', JSON.stringify([
                    'https://a.example.com/', 'https://b.example.com/'
                ]));
            }"""
        )
        _open_generate(page)
        page.locator("#url-input").click()
        options = page.locator("#url-history-list option")
        expect(options).to_have_count(2)
        values = [options.nth(i).get_attribute("value") for i in range(2)]
        assert "https://a.example.com/" in values
        assert "https://b.example.com/" in values

    def test_datalist_respects_saved_limit(self, page: Page) -> None:
        """設定の保持件数を超える分はサジェストに出さない。"""
        page.goto(BASE_URL)
        page.evaluate(
            """() => {
                localStorage.setItem('webspec2doc.settings', JSON.stringify({urlHistoryLimit: 2}));
                localStorage.setItem('wsd_url_history', JSON.stringify([
                    'https://a.example.com/', 'https://b.example.com/', 'https://c.example.com/'
                ]));
            }"""
        )
        _open_generate(page)
        page.locator("#url-input").click()
        expect(page.locator("#url-history-list option")).to_have_count(2)

    def test_limit_zero_clears_history(self, page: Page) -> None:
        page.goto(BASE_URL)
        page.evaluate(
            "localStorage.setItem('wsd_url_history', JSON.stringify(['https://a.example.com/']))"
        )
        _open_settings(page)
        page.locator("#set-url-history-limit").select_option("0")
        page.locator("#save-settings").click()
        expect(page.locator("#settings-msg")).to_have_class(re.compile(r"show"))
        cleared = page.evaluate("localStorage.getItem('wsd_url_history')")
        assert cleared is None, f"URL履歴が削除されていない: {cleared}"
