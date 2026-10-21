"""Document Assurance パネルの静的検査（文字列）。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [ROOT / "static/js/docassure-diff-panel.js", ROOT / "static/js/docassure-review-panel.js",
         ROOT / "static/css/docassure-panels.css"]
JS = FILES[:2]


def _t(p):
    return p.read_text(encoding="utf-8")


def test_files_exist():
    assert all(p.exists() for p in FILES)


def test_uses_esc():
    for p in JS:
        assert "ctx.esc" in _t(p) or "esc(" in _t(p), p.name


def test_no_native_dialogs():
    for p in JS:
        assert not re.search(r"\b(window\.)?(confirm|alert|prompt)\s*\(", _t(p)), p.name


def test_review_wording():
    t = _t(JS[1])
    assert "DEGRADED" in t and "候補" in t and "<dialog" in t and "confirm_send" in t


def test_diff_wording():
    t = _t(JS[0])
    assert "要件の変更ではありません" in t and "no_previous" in t


def test_no_external_url():
    for p in FILES:
        assert not re.search(r"https?://", _t(p)), p.name


def test_no_innerhtml_of_raw_document_text():
    # 文書由来の値は esc を通す（生の r.body.* を連結していない簡易検査）
    for p in JS:
        assert "innerHTML = d." not in _t(p)
