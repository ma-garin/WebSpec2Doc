"""C-broken-views の再発防止 E2E テスト（L3 システムテスト）。

対象（実ユーザーのドッグフーディング報告）:
    1. ユーザーガイド画面: 「画面スクロールができない」「中身が動かない」
       「CLIについて言及がない」
       → 根本原因は #app-content に付与される is-executing / is-reporting
       （レポート表示・実行中専用の全高モードフラグ）が switchView() で
       他画面へ移動しても解除されず、以後に開いたどの画面も
       overflow:hidden に固定されてしまうことだった
       （static/js/core.js switchView, static/js/recrawl.js openResultsForDomain）。
    2. 設定画面: 「タブ操作ができません」
       → .set-tab ボタンに click ハンドラが未実装で、押しても何も起きなかった
       （static/js/settings.js）。
    3. 履歴・差分: 「[この2時点の差分を表示]を押下しても反応がよくわからない」
       → ローディング表示が無く、選択を変えずに押すと iframe の src が
       変化しないため見た目上何も起きないことがあった
       （static/js/results.js showTimelineDiff）。

実行方法:
    make verify-ui
"""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://127.0.0.1:8765"
DIFF_DOMAIN = "e2e-broken-views-diff.example.com"
ROOT = Path(__file__).parent.parent.parent
DIFF_FIXTURE_DIR = ROOT / "output" / DIFF_DOMAIN

OLD_SNAPSHOT = [
    {
        "url": f"https://{DIFF_DOMAIN}/",
        "title": "トップ",
        "headings": [],
        "links": [],
        "forms": [],
        "buttons": [],
    },
]
NEW_SNAPSHOT = [
    {
        "url": f"https://{DIFF_DOMAIN}/",
        "title": "トップ",
        "headings": [],
        "links": [],
        "forms": [],
        "buttons": [],
    },
    {
        "url": f"https://{DIFF_DOMAIN}/new",
        "title": "新ページ",
        "headings": [],
        "links": [],
        "forms": [],
        "buttons": [],
    },
]


@pytest.fixture(scope="module", autouse=True)
def diff_snapshot_fixture() -> Generator[None, None, None]:
    """履歴・差分タブ用に2時点分のスナップショットを配置し、テスト後に削除する。"""
    snaps_dir = DIFF_FIXTURE_DIR / "snapshots"
    snaps_dir.mkdir(parents=True, exist_ok=True)
    (snaps_dir / "20260101-000000.json").write_text(
        json.dumps(OLD_SNAPSHOT, ensure_ascii=False), encoding="utf-8"
    )
    (snaps_dir / "20260102-000000.json").write_text(
        json.dumps(NEW_SNAPSHOT, ensure_ascii=False), encoding="utf-8"
    )
    yield
    shutil.rmtree(DIFF_FIXTURE_DIR, ignore_errors=True)


class TestUserGuideScroll:
    """ユーザーガイド画面のスクロール可能性（再発防止: is-executing/is-reporting 残留）。"""

    def test_scrollable_on_fresh_load(self, page: Page) -> None:
        """通常遷移では #app-content がスクロール可能である。"""
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        page.locator(".app-nav-item[data-view='user-guide']").click()
        expect(page.locator("#view-user-guide")).to_be_visible()
        overflow = page.eval_on_selector("#app-content", "el => getComputedStyle(el).overflow")
        assert overflow == "auto", f"#app-content が overflow:auto でない（{overflow}）"

    def test_scrollable_after_opening_report_via_deep_link(self, page: Page) -> None:
        """レポート画面（#report/...）を経由した後でも、他画面へ移動すれば
        全高モード（is-executing/is-reporting）が解除されスクロール可能になる。

        実際のバグ再現手順: レポートを開く（openResultsForDomain経由）→ 別画面へ移動
        → #app-content に is-executing が残留し overflow:hidden に固定されていた。
        """
        page.goto(f"{BASE_URL}/#report/{DIFF_DOMAIN}")
        page.wait_for_timeout(500)
        page.locator(".app-nav-item[data-view='user-guide']").click()
        page.wait_for_timeout(200)
        cls = page.eval_on_selector("#app-content", "el => el.className")
        assert "is-executing" not in cls, f"is-executing が残留している: {cls}"
        assert "is-reporting" not in cls, f"is-reporting が残留している: {cls}"
        before = page.eval_on_selector("#app-content", "el => el.scrollTop")
        box = page.locator("#app-content").bounding_box()
        assert box is not None
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.wheel(0, 500)
        page.wait_for_timeout(150)
        after = page.eval_on_selector("#app-content", "el => el.scrollTop")
        assert after > before, "マウスホイールでスクロールできない"

    def test_content_taller_than_viewport(self, page: Page) -> None:
        """ユーザーガイドの中身がビューポートより長く、実際にスクロールが必要な分量であること。"""
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        page.locator(".app-nav-item[data-view='user-guide']").click()
        scroll_h = page.eval_on_selector("#app-content", "el => el.scrollHeight")
        client_h = page.eval_on_selector("#app-content", "el => el.clientHeight")
        assert (
            scroll_h > client_h
        ), "ガイドの中身がビューポート内に収まってしまっている（検証条件として不十分）"

    def test_cli_usage_section_present(self, page: Page) -> None:
        """CLIの主要フロー（--url/--format/--compare/--login-record）に言及がある。"""
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        page.locator(".app-nav-item[data-view='user-guide']").click()
        text = page.locator("#view-user-guide").inner_text()
        for token in ("--url", "--format", "--compare", "--login-record", "src/main.py"):
            assert token in text, f"ユーザーガイドに {token} の記載がない"


class TestSettingsTabs:
    """設定画面のタブ切替（再発防止: click ハンドラ未実装）。"""

    def test_default_tab_is_api(self, page: Page) -> None:
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        page.locator(".app-nav-item[data-view='settings']").click()
        expect(page.locator("#set-panel-api")).to_be_visible()
        expect(page.locator("#set-panel-crawl")).to_be_hidden()

    def test_api_tab_includes_model_select(self, page: Page) -> None:
        """モデルタブは廃止し、APIキータブに統合される（S1-6）。"""
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        page.locator(".app-nav-item[data-view='settings']").click()
        expect(page.locator(".set-tab[data-tab='model']")).to_have_count(0)
        expect(page.locator("#set-panel-model")).to_have_count(0)
        expect(page.locator("#api-model")).to_be_visible()
        expect(page.locator("#test-connection")).to_be_visible()

    def test_click_switches_through_all_tabs(self, page: Page) -> None:
        """3タブすべてが押した順にパネル切替されること（クロール既定値・通知タブ含む）。"""
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        page.locator(".app-nav-item[data-view='settings']").click()
        for tab in ("crawl", "notify", "api"):
            page.locator(f".set-tab[data-tab='{tab}']").click()
            expect(page.locator(f"#set-panel-{tab}")).to_be_visible()
            others = [t for t in ("api", "crawl", "notify") if t != tab]
            for other in others:
                expect(page.locator(f"#set-panel-{other}")).to_be_hidden()


class TestHistoryDiffFeedback:
    """履歴・差分タブの「この2時点の差分を表示」ボタンの応答性（再発防止: 無反応バグ）。"""

    def _open_history_tab(self, page: Page) -> None:
        page.goto(f"{BASE_URL}/#report/{DIFF_DOMAIN}/history")
        expect(page.locator("#result-panel")).to_be_visible()
        expect(page.locator("#tl-diff-btn")).to_be_visible(timeout=10_000)

    def test_button_shows_loading_state_immediately(self, page: Page) -> None:
        """クリック直後にボタンのラベルが「取得中」に変わる（無反応に見えない）。

        ローカル環境では /api/snapshot-diff の応答が速すぎて一瞬でラベルが
        元に戻ってしまうため、レスポンスに人工的な遅延を挟んでローディング状態を
        確実に観測する。
        """
        self._open_history_tab(page)

        def _delayed_continue(route):  # type: ignore[no-untyped-def]
            time.sleep(0.6)
            route.continue_()

        page.route("**/api/snapshot-diff**", _delayed_continue)
        page.locator("#tl-diff-btn").click()
        # フルスイート実行時はCPU競合でクリック→再描画が遅延することがあるため、
        # デフォルト5秒より長めに待つ（実際の遅延は0.6秒固定なので誤検知はしない）。
        expect(page.locator("#tl-diff-btn")).to_have_text("差分を取得中…", timeout=15_000)
        # 遅延後にローディングが解除されることも確認する
        expect(page.locator("#tl-diff-btn")).to_have_text("この2時点の差分を表示", timeout=10_000)

    def test_button_shows_result_after_success(self, page: Page) -> None:
        """成功時、ローディング解除後に差分内容（iframe）が表示され、ボタンが元のラベルに戻る。"""
        self._open_history_tab(page)
        page.locator("#tl-diff-btn").click()
        expect(page.locator("#tl-diff-btn")).to_have_text("この2時点の差分を表示", timeout=10_000)
        expect(page.locator("#tl-diff iframe")).to_have_count(1)
        frame = page.frame_locator("#tl-diff iframe")
        expect(frame.locator("body")).to_contain_text("仕様ドリフトレポート")
        expect(frame.locator("body")).to_contain_text("new")

    def test_button_shows_error_on_failure(self, page: Page) -> None:
        """通信エラー時、無言で失敗せず理由付きのエラー表示になり、ボタンが再操作可能に戻る。"""
        self._open_history_tab(page)
        page.route("**/api/snapshot-diff**", lambda route: route.abort())
        page.locator("#tl-diff-btn").click()
        expect(page.locator("#tl-diff")).to_contain_text("差分の取得に失敗しました", timeout=10_000)
        expect(page.locator("#tl-diff-btn")).to_have_text("この2時点の差分を表示")
        expect(page.locator("#tl-diff-btn")).to_be_enabled()

    def test_no_javascript_errors(self, page: Page) -> None:
        js_errors: list[str] = []
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        self._open_history_tab(page)
        page.locator("#tl-diff-btn").click()
        page.wait_for_timeout(500)
        assert js_errors == [], f"JavaScript エラー: {js_errors}"
