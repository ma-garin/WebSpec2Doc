"""システムテスト L3: ドキュメント作成（docs/system_test_cases.csv ST-010〜ST-013)。

実行方法:
    make e2e-system
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect
from tests.e2e.system.helpers import MEMBER, open_docs_system


class TestStDocGen:
    """URL 指定の生成ウィザード・実行履歴・成果物参照。"""

    def test_st010_generate_starts_with_valid_url(self, page: Page, system_server: str) -> None:
        """ST-010: 有効な URL で探索を開始すると進捗（または次段階）が現れる。

        クロール対象はサーバー自身のログインページ（WEBSPEC2DOC_ALLOW_LOCAL=1）。
        成果物の完成までは待たず、「実行が開始された」ことの肯定的な目印
        （ステータス表示 or 第1ステップの完了）までを検証する。
        """
        open_docs_system(page, system_server, MEMBER)
        page.locator("#url-input").fill(f"{system_server}/auth/login")
        page.locator("#discover-btn").click()
        page.wait_for_function(
            """() => {
                const msg = document.querySelector('#url-input-message');
                const p1 = document.querySelector('#wizard-p1');
                return (msg && msg.textContent.trim().length > 0)
                    || (p1 && p1.offsetParent === null);
            }""",
            timeout=30_000,
        )

    def test_st011_invalid_url_shows_validation_message(
        self, page: Page, system_server: str
    ) -> None:
        """ST-011: 不正な URL では検証メッセージが出て、ウィザードは進まない。"""
        open_docs_system(page, system_server, MEMBER)
        page.locator("#url-input").fill("これはURLではない")
        page.locator("#discover-btn").click()
        # 具体的な文言は実装に委ね、何らかのメッセージが出ることを目印にする
        expect(page.locator("#url-input-message")).to_contain_text(re.compile(r"\S"))
        expect(page.locator("#wizard-p1")).to_be_visible()

    def test_st012_run_history_shows_past_run(self, page: Page, system_server: str) -> None:
        """ST-012: 実行履歴に過去の実行が表示される（サンプルレポートで実データを作る）。"""
        open_docs_system(page, system_server, MEMBER)
        resp = page.request.post(f"{system_server}/api/sample-report")
        assert resp.ok, f"サンプルレポート作成失敗: {resp.status} {resp.text()}"
        payload = resp.json() if resp.text() else {}
        domain = str(payload.get("domain") or payload.get("site") or "")

        page.goto(f"{system_server}/")
        page.locator(
            "#nav-docs-run-history-btn:visible, #nav-run-history-btn:visible"
        ).first.click()
        expect(page.locator("#view-run-history")).to_be_visible()
        if domain:
            expect(page.locator("#view-run-history")).to_contain_text(domain)
        else:
            expect(page.locator("#rh-count")).to_be_visible()

    def test_st013_file_preview(self, page: Page, system_server: str) -> None:
        """ST-013: 成果物ファイルのプレビュー表示。"""
        pytest.skip(
            "ST-013: プレビューを開く導線のセレクタが実測未確定のためサイクル1では未実装"
            "（モーダル自体は #file-preview-modal として存在を確認済み）"
        )
