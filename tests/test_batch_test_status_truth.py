"""System07: 生成しただけのものを合格に見せない（C-P0-3）。静的に JS/CSS の文言・クラスを検査する。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "static/js/batch-test.js").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/batch-test.css").read_text(encoding="utf-8")


def test_no_pass_color_for_generated_items():
    assert "i-pass" not in JS
    assert "p-pass" not in JS
    assert not re.search(r"kpi\([^)]*,\s*'ok'", JS)


def test_no_pass_wording():
    assert "合格" not in re.sub(r"合格／失敗（実行結果を取り込むと表示）", "", JS)


def test_generated_is_labeled_not_executed():
    assert "生成済み（未実行）" in JS
    assert "生成したケース数" in JS
    assert "'未実行'" in JS


def test_no_run_notice_present():
    assert "この画面ではテストを実行しません。生成・書き出しまでです。実行結果は取り込むまで表示しません。" in JS
    assert ".bt-truth" in CSS


def test_four_stages_are_separate_and_result_gated():
    assert "'生成済み'" in JS and "'書き出し済み（未実行）'" in JS and "'実行済み'" in JS and "'確認済み'" in JS
    # 実行済み・確認済みは結果／確認の記録がある時だけ done にする
    assert "ran ? 'done' : 'not_started'" in JS
    assert "ver ? 'done' : 'unverified'" in JS
    # 生成済み・書き出し済みは done（完了色）にしない
    assert "gen ? 'preparing'" in JS and "ex.length ? 'preparing'" in JS


def test_export_is_recorded_only_after_success_and_reload_is_unverified():
    assert "state.exported[j.id]" in JS
    assert "リロード後は未確認" in JS
    # 失敗時は notice(error) を出し、記録は成功側でだけ書く
    ok_part = JS.split(".then(function (x) {", 1)[1].split(".catch(", 1)[0]
    assert "state.exported" in ok_part


def test_states_and_confirm_use_ws2d():
    for token in ("kind: 'empty'", "kind: 'unavailable'", "'partial'", "kind: 'error'", "W.confirm", "danger: true", "W.reason", "W.status.html"):
        assert token in JS
    assert "OK_EXT" in JS


def test_page_header_present():
    html = (ROOT / "templates/batch_test.html").read_text(encoding="utf-8")
    for token in ('class="c-page-head', 'id="bt-reason"', 'id="bt-stages"', 'id="bt-head-primary"'):
        assert token in html
