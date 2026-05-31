"""サイト追加ウィザードの既定挙動テスト（Flask テストクライアント）"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod


def _index_html() -> str:
    return appmod.app.test_client().get("/").get_data(as_text=True)


def test_autocrawl_is_default_mode() -> None:
    assert 'value="crawl" checked' in _index_html()


def test_single_mode_is_not_default_but_available() -> None:
    html = _index_html()
    assert 'value="single" checked' not in html
    assert 'value="single"' in html


def test_manual_mode_still_available() -> None:
    assert 'value="manual"' in _index_html()
