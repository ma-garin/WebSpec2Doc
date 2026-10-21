"""System06 Document Assurance 画面の契約: /docverify が docassure の JS/CSS を参照し、評価不能を 100/0 に捏造しない。"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _client():
    import app as appmod
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


def test_docverify_page_references_docassure_assets():
    r = _client().get("/docverify")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "js/docassure.js" in html and "css/docassure.css" in html
    assert 'id="da-root"' in html


def test_js_branches_on_null_value_and_never_fabricates():
    js = (ROOT / "static/js/docassure.js").read_text(encoding="utf-8")
    assert re.search(r"\.value\s*==\s*null", js), "value null の分岐が必要"
    assert "評価不能" in js
    assert not re.search(r"value\s*(\|\||\?\?)\s*(100|0)\b", js)
    assert not re.search(r"\.value\s*=\s*(100|0)\b", js)


def test_js_declares_mode_and_conflict_unresolved_notice():
    js = (ROOT / "static/js/docassure.js").read_text(encoding="utf-8")
    assert "DETERMINISTIC_ONLY" in js and "AI レビューは未実行" in js
    assert "どちらが正しいかは未確定" in js
    assert "（任意）" not in js
