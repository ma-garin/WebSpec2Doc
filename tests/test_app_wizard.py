"""サイト追加ウィザードの既定挙動テスト（Flask テストクライアント）"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod


def _index_html() -> str:
    return appmod.app.test_client().get("/").get_data(as_text=True)


def test_discover_btn_is_in_url_row() -> None:
    html = _index_html()
    assert 'id="discover-btn"' in html
    # 画面分析ボタンがURL入力と同じ input-row 内にあること
    assert 'id="url-input"' in html.split('id="discover-btn"')[0].split('class="input-row"')[-1]


def test_single_mode_is_removed() -> None:
    assert 'value="single"' not in _index_html()


def test_manual_mode_is_removed() -> None:
    assert 'value="manual"' not in _index_html()
