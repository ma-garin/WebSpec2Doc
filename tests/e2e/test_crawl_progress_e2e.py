"""クロール実行中タイトルの進捗表示（xxx/xxx）の E2E テスト（R3-07）。

対象:
    static/js/execution.js の updateCrawlProgress() が #exec-title に
    「クロール中…（完了数/総数）」を常時反映すること。

実行方法:
    make verify-ui
"""

from __future__ import annotations

import os

from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")


class TestCrawlProgressTitle:
    def test_title_shows_progress_counts(self, page: Page) -> None:
        """crawl_started/page_completed イベントをモック配信し、
        #exec-title に「クロール中…（1/5）」のように完了数/総数が表示されること。"""
        page.goto(BASE_URL)
        page.evaluate(
            """() => {
                resetCrawlProgress(5);
                handleCrawlEvent({event: 'crawl_started', total: 5, parallelism: 1});
                handleCrawlEvent({event: 'page_completed', elapsed_sec: 1.2});
            }"""
        )
        expect(page.locator("#exec-title")).to_contain_text("クロール中…（1/5）")

    def test_title_updates_as_more_pages_complete(self, page: Page) -> None:
        """複数ページの完了で完了数が積み上がること（総数は crawl_started の値を維持）。"""
        page.goto(BASE_URL)
        page.evaluate(
            """() => {
                resetCrawlProgress(3);
                handleCrawlEvent({event: 'crawl_started', total: 3, parallelism: 1});
                handleCrawlEvent({event: 'page_completed', elapsed_sec: 1});
                handleCrawlEvent({event: 'page_completed', elapsed_sec: 1});
            }"""
        )
        expect(page.locator("#exec-title")).to_contain_text("クロール中…（2/3）")

    def test_title_falls_back_to_question_mark_when_total_unknown(self, page: Page) -> None:
        """総数が未確定（0のまま）の場合は '?' を表示し、値の捏造をしないこと。"""
        page.goto(BASE_URL)
        page.evaluate(
            """() => {
                resetCrawlProgress(0);
                handleCrawlEvent({event: 'page_completed', elapsed_sec: 1});
            }"""
        )
        expect(page.locator("#exec-title")).to_contain_text("クロール中…（1/?）")
