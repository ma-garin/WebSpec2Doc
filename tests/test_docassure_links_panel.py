"""連携パネル（static/js/docassure-links-panel.js）の静的検査。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JS = (ROOT / "static/js/docassure-links-panel.js").read_text(encoding="utf-8")
CSS = (ROOT / "static/css/docassure-links-panel.css").read_text(encoding="utf-8")


def test_registers_panel():
    assert "window.DAPanels.links" in JS
    assert "label: '連携'" in JS


def test_uses_esc():
    assert JS.count("esc(") > 20


def test_relative_paths_only():
    paths = re.findall(r"ctx\.(?:get|post)\('([^']+)'", JS)
    assert paths
    for p in paths:
        assert not p.startswith("/") and "://" not in p and not p.startswith("api/")
        assert p.startswith(("system01/", "system02/", "system09/"))


def test_no_native_dialogs():
    assert not re.search(r"\b(?:window\.)?(?:alert|confirm|prompt)\s*\(", JS)


def test_not_observed_caution():
    assert "NOT_OBSERVED" in JS
    assert "存在しないとは限りません" in JS
    assert "確定ではなく候補" in JS


def test_no_external_urls():
    assert not re.search(r"https?://", JS + CSS)


def test_honest_states():
    assert "実行済みではありません" in JS
    assert "影響なしの証明ではありません" in JS
    assert "前の版がありません" in JS
