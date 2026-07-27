"""AutoRun の全状態を横断で点検する（L3 システムテスト）。

なぜ必要か:
    これまでの不具合は「ある1つの状態を誰も画面で見ていなかった」ことで
    生まれている。停止ボタンが2つ出ていた件も、ログイン入力待ちで中止できな
    かった件も、実行完了後に受付フォームが復活した件も、すべて特定の状態を
    通っていなかったために見逃した。

    そこで、状態を1つずつ人が見に行くのではなく、全状態を機械的に走査して
    共通の不変条件を検査する。

検査する不変条件:
    1. 実行中・待機中は必ず中止できる（出口がある）
    2. 同じラベルのボタンが同一画面に2つ以上出ない
    3. 実行が終わっていない間は受付フォームを出さない
    4. 実行が終わったら受付フォームを復活させない（結果が主役）
    5. 進行中の状態は「いま何をしているか」がバーに出る
"""

from __future__ import annotations

import json
import os

import pytest
from playwright.sync_api import Page

BASE_URL = os.environ.get("WEBSPEC2DOC_E2E_URL", "http://127.0.0.1:8765")

#: 進行中（中止できなければならない）
_ACTIVE = [
    ("discovering", "到達確認中"),
    ("awaiting_input", "ログイン情報の入力待ち"),
    ("crawling", "観測中"),
    ("generating_qa", "成果物を生成中"),
    ("generating_scripts", "スクリプトを生成中"),
    ("running_tests", "テストを実行中"),
]

#: 終了（やり直せなければならない／受付は復活させない）
_TERMINAL = [("complete", "完了"), ("failed", "失敗"), ("cancelled", "停止済み")]

_PROBE_JS = """(payload) => {
  const vis = e => {
    if (!e) return false;
    const r = e.getBoundingClientRect();
    const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  _autorunRender(payload);
  const bar = document.getElementById('autorun-leadbar');
  const intake = document.getElementById('autorun-idle-msg');
  const labels = Array.from(document.querySelectorAll('button'))
    .filter(vis).map(b => b.innerText.trim()).filter(Boolean);
  const dupes = [...new Set(labels.filter((v, i, a) => a.indexOf(v) !== i))];
  return {
    barVisible: vis(bar),
    barText: bar && vis(bar) ? bar.innerText.replace(/\\s+/g, ' ') : '',
    intakeVisible: vis(intake),
    buttons: labels,
    duplicateButtons: dupes,
    canCancel: labels.some(t => /中止|キャンセル/.test(t)),
    canRetry: labels.some(t => /やり直す|新しく実行/.test(t)),
  };
}"""


def _payload(status: str, step_label: str) -> dict:
    """サーバ応答を模したレンダリング入力。"""
    return {
        "job_id": "state-matrix",
        "domain": "127.0.0.1:8767",
        "url": "http://127.0.0.1:8767/index.html",
        "status": status,
        "step_label": step_label,
        "log": ["[20:00:00] 観測開始", "[20:00:07] 到達確認完了: 7画面を検出"],
        "outputs": {},
        "test_results": (
            {"passed": 6, "failed": 0, "skipped": 0, "total": 6, "ok": True}
            if status == "complete"
            else None
        ),
        "error": "観測結果を保存できませんでした。" if status == "failed" else None,
        "started_at": "2026-07-26T20:00:00",
        "finished_at": (
            "2026-07-26T20:01:00" if status in {"complete", "failed", "cancelled"} else None
        ),
        "elapsed_sec": 60,
        "input_request": (
            {"message": "ログインが必要です", "login_url": "http://127.0.0.1:8767/login.html"}
            if status == "awaiting_input"
            else None
        ),
        "awaiting_remaining_sec": 1700 if status == "awaiting_input" else 0,
        "run_policy": {},
        "step_data": {
            "crawl": {"screens": 6, "forms": 3},
            "discover": {"pages": 7, "login_required": 1},
        },
        "unverified": ["未観測の領域: 認証が必要で未観測（1件）"] if status == "complete" else [],
    }


@pytest.fixture()
def autorun(page: Page) -> Page:
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{BASE_URL}/auto-run")
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("#autorun-start-btn", state="attached")
    return page


class TestActiveStates:
    """進行中・待機中の不変条件。"""

    @pytest.mark.parametrize(("status", "label"), _ACTIVE)
    def test_can_always_cancel(self, autorun: Page, status: str, label: str) -> None:
        """止めたい人に必ず出口がある。

        ログイン入力待ちには「設定して続ける／未ログインのまま進む」しか無く、
        実行そのものをやめる手段が無かった（利用者の指摘で発覚）。
        """
        r = autorun.evaluate(_PROBE_JS, _payload(status, label))
        assert r["canCancel"], f"{status}: 中止できない / ボタン={r['buttons']}"

    @pytest.mark.parametrize(("status", "label"), _ACTIVE)
    def test_no_duplicate_buttons(self, autorun: Page, status: str, label: str) -> None:
        """同じ操作を2箇所に出さない。

        主導線バーの外に2つ目の「停止」が出ていた（利用者の指摘で発覚）。
        """
        r = autorun.evaluate(_PROBE_JS, _payload(status, label))
        assert not r[
            "duplicateButtons"
        ], f"{status}: 同じラベルのボタンが重複 {json.dumps(r['duplicateButtons'], ensure_ascii=False)}"

    @pytest.mark.parametrize(("status", "label"), _ACTIVE)
    def test_intake_form_is_hidden_while_running(
        self, autorun: Page, status: str, label: str
    ) -> None:
        """実行中に受付フォームを出さない（いま何の画面か分からなくなる）。"""
        r = autorun.evaluate(_PROBE_JS, _payload(status, label))
        assert not r["intakeVisible"], f"{status}: 実行中なのに受付フォームが出ている"

    @pytest.mark.parametrize(("status", "label"), _ACTIVE)
    def test_shows_what_is_happening(self, autorun: Page, status: str, label: str) -> None:
        """いま何が起きていて、次に何を選ぶかがバーから読み取れる。

        待機中は工程名ではなく「なぜ止まっているか」を出す（そちらが判断材料）。
        """
        r = autorun.evaluate(_PROBE_JS, _payload(status, label))
        assert r["barVisible"], f"{status}: 主導線バーが出ていない"
        expected = "ログインが必要です" if status == "awaiting_input" else label
        assert (
            expected in r["barText"]
        ), f"{status}: バーから現在の状況が読み取れない / {r['barText']}"


class TestTerminalStates:
    """終了状態の不変条件。"""

    @pytest.mark.parametrize(("status", "label"), _TERMINAL)
    def test_intake_form_does_not_return(self, autorun: Page, status: str, label: str) -> None:
        """終了後に受付フォームを復活させない。

        完了時に段階パネルを閉じた際、受付フォームが再表示され、結果ではなく
        入力欄が現れていた（実測で発覚）。
        """
        r = autorun.evaluate(_PROBE_JS, _payload(status, label))
        assert not r["intakeVisible"], f"{status}: 終了後に受付フォームが復活している"

    @pytest.mark.parametrize(("status", "label"), _TERMINAL)
    def test_no_duplicate_buttons(self, autorun: Page, status: str, label: str) -> None:
        r = autorun.evaluate(_PROBE_JS, _payload(status, label))
        assert not r[
            "duplicateButtons"
        ], f"{status}: 同じラベルのボタンが重複 {json.dumps(r['duplicateButtons'], ensure_ascii=False)}"

    @pytest.mark.parametrize("status", ["failed", "cancelled"])
    def test_失敗と停止からはやり直せる(self, autorun: Page, status: str) -> None:
        """行き止まりを作らない。"""
        label = "失敗" if status == "failed" else "停止済み"
        r = autorun.evaluate(_PROBE_JS, _payload(status, label))
        assert r["canRetry"], f"{status}: やり直す手段が無い / ボタン={r['buttons']}"
