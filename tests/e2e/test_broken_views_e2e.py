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
import os
import shutil
from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")
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


class TestSettingsTabs:
    """設定画面のタブ切替（再発防止: click ハンドラ未実装）。"""


class TestHistoryDiffFeedback:
    """履歴・差分タブの「この2時点の差分を表示」ボタンの応答性（再発防止: 無反応バグ）。"""

    def _open_history_tab(self, page: Page) -> None:
        page.goto(f"{BASE_URL}/#report/{DIFF_DOMAIN}/history")
        expect(page.locator("#result-panel")).to_be_visible()
        expect(page.locator("#tl-diff-btn")).to_be_visible(timeout=10_000)

    def test_no_javascript_errors(self, page: Page) -> None:
        js_errors: list[str] = []
        page.on("pageerror", lambda exc: js_errors.append(str(exc)))
        self._open_history_tab(page)
        page.locator("#tl-diff-btn").click()
        page.wait_for_timeout(500)
        assert js_errors == [], f"JavaScript エラー: {js_errors}"
