"""E2E: アプリシェル（topbar クイック検索・アバター）。

Phase B（UIシェル刷新）の受入テスト。
- クイック検索: 画面名でフィルタ → Enter/クリックで該当ビューへ遷移
- Cmd/Ctrl+K でクイック検索にフォーカス
- 利用者アバターは認証 OFF（既定）では非表示

検証対象: http://127.0.0.1:8765（認証 OFF の本体アプリ）
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

_ACTIVE = re.compile(r"\bis-active\b")

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

BASE_URL = "http://127.0.0.1:8765"


@pytest.fixture()
def app_page(page: Page) -> Page:
    page.goto(BASE_URL, wait_until="networkidle")
    expect(page.locator("#topbar-search-input")).to_be_visible(timeout=10_000)
    return page


class TestQuickSearch:
    def test_search_input_present_with_hint(self, app_page: Page) -> None:
        """topbar にクイック検索入力があり、⌘K ヒントを持つ。"""
        inp = app_page.locator("#topbar-search-input")
        expect(inp).to_be_visible()
        assert "検索" in (inp.get_attribute("placeholder") or "")

    def test_search_filters_and_navigates_to_view(self, app_page: Page) -> None:
        """画面名で検索するとヒットし、クリックで該当ビューへ遷移する。"""
        app_page.locator("#topbar-search-input").fill("観点管理")
        results = app_page.locator("#topbar-search-results .topbar-search-item")
        expect(results.first).to_be_visible(timeout=5_000)
        # 「観点管理」ビューのヒットをクリック
        app_page.locator(
            "#topbar-search-results .topbar-search-item[data-view='viewpoints']"
        ).first.click()
        expect(app_page.locator("#view-viewpoints")).to_have_class(_ACTIVE, timeout=5_000)

    def test_enter_navigates_to_first_result(self, app_page: Page) -> None:
        """Enter で先頭候補へ遷移する。"""
        app_page.locator("#topbar-search-input").fill("実行履歴")
        expect(app_page.locator("#topbar-search-results .topbar-search-item").first).to_be_visible(
            timeout=5_000
        )
        app_page.locator("#topbar-search-input").press("Enter")
        expect(app_page.locator("#view-run-history")).to_have_class(_ACTIVE, timeout=5_000)

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


class TestAvatarAuthGate:
    def test_avatar_absent_when_auth_disabled(self, app_page: Page) -> None:
        """認証 OFF（既定）では利用者アバターを表示しない。"""
        # 要素自体が描画されない（テンプレート側で session 未ログイン時は出力しない）
        assert app_page.locator("#topbar-avatar").count() == 0
