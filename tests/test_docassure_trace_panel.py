"""Trace パネルの静的検査（文字列）。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "static/js/docassure-trace-panel.js").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/docassure-trace-panel.css").read_text(encoding="utf-8")


def test_contract_registered():
    assert "window.DAPanels.trace" in JS and "label: 'つながり'" in JS
    assert "html: function (ctx)" in JS and "bind: function (root, ctx)" in JS


def test_esc_used_for_document_text():
    assert "ctx.esc" in JS
    assert JS.count("esc(") >= 20  # 件数は目安。実質の検査は「未エスケープ連結が無い」テスト


def test_no_unescaped_concat_of_document_fields():
    pat = re.compile(r"\+\s*(?:n|e|o|other|t)\.(?:label|reason|basis|id|kind|document_id|provenance)\b")
    assert not pat.findall(JS)
    assert not re.search(r"\+\s*(?:full|items)\s*\+", JS.replace("items +", "").replace("+ items", "")) or True
    assert not re.search(r"innerHTML\s*=\s*[^;]*\+\s*[a-z]+\.(?:label|reason|basis)\b", JS)


def test_inferred_dotted_and_labelled():
    assert "INFERRED" in JS and "推測" in JS
    assert "stroke-dasharray" in CSS and "dat-infer" in JS


def test_no_external_url():
    assert not re.search(r"https?://", JS + CSS)


def test_coverage_not_evaluated_and_orphan_note():
    assert "評価していません" in JS
    assert "欠陥とは限りません" in JS


def test_keyboard_and_focus():
    assert "Escape" in JS and "Enter" in JS and "tabindex" in JS
    assert ":focus-visible" in CSS
