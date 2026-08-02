"""画面を離れて戻ったときに、前の状態が残らないこと（L3 システムテスト）。

対象（実ユーザーのドッグフーディング報告）:
    「一度解析し、戻ると表示にログインが残っている。致命的」

    画面解析の途中で他の画面へ移り、「新規解析」で戻ると、前回の
    「画面を解析しています…（経過 0:05）」の進捗カードと
    「このサイトはログインが必要です」のパネルがそのまま出ていた。
    今動いているのか前回の残りなのか、利用者には判断できない。

    根本原因は clearDiscovered() が発見結果（一覧・ステータス）しか
    消しておらず、進捗カード・ライブフィード・経過タイマー・
    ログイン案内カードが残っていたこと（static/js/wizard.js）。

あわせて、この修正の過程で作り込んだ回帰も固定する:

    レポートパネル（#result-panel）を .view の外へ出したため
    （generate と run-result で共有するため）、showResults() が
    hidden を外すだけで「今いる画面の上に」パネルが出るようになっていた。
    テスト実行の完了時など、別の画面にいる間に呼ばれる経路がある。

実行方法:
    make verify-ui
"""

from __future__ import annotations

import os

from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")
# 同梱デモサイト（make demo）。外部へ出ずに解析できる。
DEMO_URL = "http://127.0.0.1:8767/index.html"


def _open_generate(page: Page) -> None:
    page.goto(f"{BASE_URL}/generate")
    page.wait_for_selector("#url-input", state="visible")


def _start_discover(page: Page, url: str) -> None:
    page.fill("#url-input", url)
    page.dispatch_event("#url-input", "input")
    page.click("#discover-btn")


def _is_shown(page: Page, element_id: str) -> bool:
    """style.display と祖先の可視性の両方で判定する。"""
    return page.evaluate(
        """(id) => {
            const el = document.getElementById(id);
            if (!el) return false;
            return !el.hidden && !el.classList.contains('hidden')
                && el.style.display !== 'none' && el.offsetParent !== null;
        }""",
        element_id,
    )


class TestDiscoverStateDoesNotLinger:
    """画面解析の「実行中」表示が、離脱後に残らないこと。"""

    def test_progress_card_is_gone_after_leaving(self, page: Page) -> None:
        _open_generate(page)
        _start_discover(page, DEMO_URL)
        # 進捗カードが出るまで待つ（出ないと、そもそも検証にならない）
        page.wait_for_function(
            "() => document.getElementById('discover-loading')?.style.display !== 'none'",
            timeout=15_000,
        )
        assert _is_shown(page, "discover-loading")

        # 解析の途中で他の画面へ移る
        page.evaluate("switchView('run-history')")
        page.wait_for_timeout(600)

        # 進捗まわりが残っていないこと
        assert not _is_shown(page, "discover-loading")
        assert page.evaluate("document.getElementById('discover-live-feed').children.length") == 0
        assert page.evaluate("document.getElementById('discover-elapsed').textContent") == ""
        assert page.evaluate("_discoverTimerInterval === null"), "経過タイマーが止まっていない"

    def test_login_card_is_gone_after_new_analysis(self, page: Page) -> None:
        """「新規解析」ではログイン案内も消えること（利用者の報告そのもの）。"""
        _open_generate(page)
        _start_discover(page, DEMO_URL)
        page.wait_for_function(
            "() => document.getElementById('discover-loading')?.style.display === 'none'",
            timeout=90_000,
        )
        page.evaluate("switchView('dashboard')")
        page.wait_for_timeout(500)

        page.evaluate("openAddSite()")
        page.wait_for_timeout(500)

        assert not _is_shown(page, "discover-loading")
        assert not _is_shown(page, "login-required-card")
        assert page.evaluate("document.getElementById('url-input').value") == ""
        assert page.evaluate("document.getElementById('discovered-url-list').children.length") == 0

    def test_completed_results_survive_leaving(self, page: Page) -> None:
        """完了した解析結果は、離脱しても消えないこと。

        「実行中の表示を消す」を作りすぎると、戻った利用者が解析し直しになる。
        消してよいのは進行中に見えるものだけ。
        """
        _open_generate(page)
        _start_discover(page, DEMO_URL)
        page.wait_for_function(
            "() => document.getElementById('discover-loading')?.style.display === 'none'",
            timeout=90_000,
        )
        found = page.evaluate("document.getElementById('discovered-url-list').children.length")
        assert found > 0, "解析結果が0件では検証にならない"

        page.evaluate("switchView('dashboard')")
        page.wait_for_timeout(500)
        page.evaluate("switchView('generate')")
        page.wait_for_timeout(500)

        after = page.evaluate("document.getElementById('discovered-url-list').children.length")
        assert after == found, "完了した解析結果まで消えている"


class TestReportPanelStaysInItsView:
    """レポートパネルが、所属しない画面の上に出ないこと。"""

    def test_show_results_moves_to_its_own_view(self, page: Page) -> None:
        page.goto(BASE_URL)
        page.wait_for_selector("#view-dashboard", state="visible")

        # 別の画面にいる間に showResults が呼ばれる経路（テスト実行の完了時など）
        page.evaluate("switchView('settings')")
        page.wait_for_timeout(400)
        page.evaluate("showResults('127.0.0.1:8767', 'overview')")
        page.wait_for_timeout(1500)

        active = page.evaluate(
            "[...document.querySelectorAll('.view.is-active')].map(v => v.id)[0] || ''"
        )
        panel_shown = _is_shown(page, "result-panel")
        assert not panel_shown or active in (
            "view-generate",
            "view-run-result",
        ), f"レポートパネルが {active} の上に出ている"

    def test_panel_is_hidden_on_unrelated_views(self, page: Page) -> None:
        page.goto(BASE_URL)
        page.wait_for_selector("#view-dashboard", state="visible")
        page.evaluate("showResults('127.0.0.1:8767', 'overview')")
        page.wait_for_timeout(1500)
        expect(page.locator("#result-panel")).to_be_visible()

        for view in ("dashboard", "run-history", "settings", "user-guide"):
            page.evaluate(f"switchView('{view}')")
            page.wait_for_timeout(300)
            assert not _is_shown(page, "result-panel"), f"{view} でパネルが出ている"
