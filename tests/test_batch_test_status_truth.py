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
