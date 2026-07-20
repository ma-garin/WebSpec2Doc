"""E2E: アプリシェル（topbar クイック検索・アバター）。

Phase B（UIシェル刷新）の受入テスト。
- クイック検索: 画面名でフィルタ → Enter/クリックで該当ビューへ遷移
- Cmd/Ctrl+K でクイック検索にフォーカス
- 利用者アバターは認証 OFF（既定）では非表示

検証対象: http://127.0.0.1:8765（認証 OFF の本体アプリ）
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

_ACTIVE = re.compile(r"\bis-active\b")

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")


@pytest.fixture()
def app_page(page: Page) -> Page:
    page.goto(BASE_URL, wait_until="networkidle")
    expect(page.locator("#topbar-search-input")).to_be_visible(timeout=10_000)
    return page


class TestQuickSearch:



    def test_cmd_k_focuses_search(self, app_page: Page) -> None:
        """Cmd/Ctrl+K でクイック検索にフォーカスする。"""
        # 一旦別要素へフォーカス
        app_page.locator("body").click()
        modifier = "Meta" if sys.platform == "darwin" else "Control"
        app_page.keyboard.press(f"{modifier}+KeyK")
        focused_id = app_page.evaluate("() => document.activeElement && document.activeElement.id")
        assert focused_id == "topbar-search-input", f"フォーカスが検索にない: {focused_id}"

    def test_escape_closes_results(self, app_page: Page) -> None:
        """Escape で検索結果が閉じる。"""
        app_page.locator("#topbar-search-input").fill("設定")
        expect(app_page.locator("#topbar-search-results .topbar-search-item").first).to_be_visible(
            timeout=5_000
        )
        app_page.locator("#topbar-search-input").press("Escape")
        expect(app_page.locator("#topbar-search-results")).to_be_hidden()


