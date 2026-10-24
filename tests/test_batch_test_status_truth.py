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
    caption = "合格／失敗は未実行（実行結果を取り込むと表示）"
    assert caption in JS
    assert "合格" not in JS.replace(caption, "")


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


def test_export_record_comes_from_server_and_only_after_success():
    # 書き出しの記録はサーバ（job.exports）が持ち、成功した時だけ読み直す。画面だけの記録は持たない
    assert "state.exported" not in JS
    assert "j.exports" in JS
    ok_part = JS.split(".then(function (x) {", 1)[1].split(".catch(function (e) { fail(", 1)[0]
    assert "api('GET', API + '/' + j.id)" in ok_part
    # 書き出した後で中身が変わったら「書き出し済み」に数えない
    assert "!r[k].stale" in JS and "'書き出し後に変更あり'" in JS
    assert "サーバの送出記録" in JS


def test_states_and_confirm_use_ws2d():
    for token in ("kind: 'empty'", "kind: 'unavailable'", "'partial'", "kind: 'error'", "W.confirm", "danger: true", "W.reason", "W.status.html"):
        assert token in JS
    assert "OK_EXT" in JS


def test_page_header_present():
    from app import app

    response = app.test_client().get("/batch-test")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    for token in ('class="c-page-head', 'id="page-reason"', 'id="bt-stages"', 'id="bt-head-primary"'):
        assert token in html
