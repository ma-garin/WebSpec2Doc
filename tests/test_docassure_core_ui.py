"""docassure.js の中核 UI 契約（文字列検査）: パネル登録口・理由欄・組み込みダイアログ禁止・出所ラベル。"""
import re
from pathlib import Path

JS = (Path(__file__).resolve().parent.parent / "static/js/docassure.js").read_text(encoding="utf-8")


def test_panel_registry_and_ctx():
    assert "window.DAPanels" in JS
    assert re.search(r"\.html\(ctx\(\)\)", JS) and re.search(r"\.bind\(", JS)
    for k in ("iid", "url", "data", "esc", "get", "post"):
        assert re.search(r"\b" + k + r":", JS), k


def test_reason_fields_and_no_native_dialogs():
    assert "data-reason" in JS and "data-expiry" in JS
    assert not re.search(r"window\.(prompt|confirm|alert)|(?<![.\w])(prompt|confirm|alert)\s*\(", JS)


def test_provenance_japanese_labels_and_waiver_expired():
    assert "推測（事実ではない）" in JS and "原文に記載" in JS and "原文から導出" in JS
    assert "提案（未承認）" in JS
    assert "期限切れ。再度確認が必要" in JS


def test_panels_pass_relative_paths_to_ctx_get_post():
    """ctx.get/post は検査 URL を付ける。パネルが絶対パスを渡すと URL が二重になり 404 になる（実機で発生）。"""
    import pathlib
    import re
    for name in ("diff-panel", "review-panel", "trace-panel"):
        src = pathlib.Path(f"static/js/docassure-{name}.js").read_text(encoding="utf-8")
        assert not re.search(r"ctx\.(get|post)\(\s*(path\s*\+|['\"]/api)", src), name
