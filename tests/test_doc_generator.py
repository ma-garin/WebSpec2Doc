"""web/services/qa/doc_generator.py のユニットテスト。"""

from __future__ import annotations

from typing import Any

from web.services.qa.doc_generator import (
    _count_markdown_table_rows,
)


def _field(name: str, **kw: Any) -> dict[str, Any]:
    base = {"name": name, "field_type": "text", "required": False}
    base.update(kw)
    return base


def _screen(page_id: str, *, title: str = "", fields=None, buttons=None, to=None) -> dict[str, Any]:
    forms = [{"action": "/submit", "method": "post", "fields": fields}] if fields else []
    return {
        "page_id": page_id,
        "title": title or f"画面 {page_id}",
        "url": f"https://example.com/{page_id.lower()}",
        "buttons": buttons or [],
        "forms": forms,
        "transitions": {"to": to or [], "from": []},
    }


def _report(screens: list[dict[str, Any]]) -> dict[str, Any]:
    return {"screens": screens}


class TestCountMarkdownTableRows:
    def test_counts_data_rows_only(self) -> None:
        table = (
            "| ケースID | 種別 | 手順 | 期待結果 | Trace |\n"
            "|---|---|---|---|---|\n"
            "| TC-0001 | 画面表示 | 開く | 表示される | P001 |\n"
            "| TC-0002 | 画面遷移 | 遷移する | 到達する | P001->P002 |\n"
        )
        assert _count_markdown_table_rows(table) == 2

    def test_empty_text_yields_zero(self) -> None:
        assert _count_markdown_table_rows("") == 0

    def test_no_table_yields_zero(self) -> None:
        assert _count_markdown_table_rows("# テストケース: example.com\n\nno table here\n") == 0
