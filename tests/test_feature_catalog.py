"""src/generator/feature_catalog.py のユニットテスト。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from generator.feature_catalog import generate_features_markdown


class TestGenerateFeaturesMarkdown:
    def test_empty_screens_yields_placeholder_row(self) -> None:
        md = generate_features_markdown([])
        assert "# 機能一覧" in md
        assert "機能を抽出できませんでした" in md

    def test_form_yields_form_feature_row(self) -> None:
        screens = [
            {
                "page_id": "P001",
                "title": "検索",
                "forms": [{"action": "/search", "method": "get", "fields": [{"name": "q"}]}],
            }
        ]
        md = generate_features_markdown(screens)
        assert "フォーム機能" in md
        assert "GET /search" in md
        assert "入力項目1件" in md
        assert "P001 検索" in md

    def test_button_yields_operation_feature_row(self) -> None:
        screens = [{"page_id": "P001", "title": "トップ", "buttons": ["検索", ""]}]
        md = generate_features_markdown(screens)
        assert "操作機能" in md
        assert "「検索」操作" in md
        # 空文字のボタンラベルは行を生成しない
        assert md.count("操作機能") == 1

    def test_transition_yields_transition_feature_row(self) -> None:
        screens = [
            {"page_id": "P001", "title": "トップ", "transitions": {"to": ["P002"], "from": []}}
        ]
        md = generate_features_markdown(screens)
        assert "遷移機能" in md
        assert "P001 → P002 への画面遷移" in md

    def test_feature_ids_are_sequential_across_kinds(self) -> None:
        screens = [
            {
                "page_id": "P001",
                "title": "トップ",
                "forms": [{"action": "/a", "method": "post", "fields": []}],
                "buttons": ["送信"],
                "transitions": {"to": ["P002"], "from": []},
            }
        ]
        md = generate_features_markdown(screens)
        assert "F001" in md
        assert "F002" in md
        assert "F003" in md
