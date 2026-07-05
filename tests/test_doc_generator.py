"""web/services/qa/doc_generator.py のユニットテスト（B-3: エグゼクティブサマリー可読化）。"""

from __future__ import annotations

from typing import Any

from web.services.qa.doc_generator import (
    _count_markdown_table_rows,
    _executive_summary_html,
    _test_cases,
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


class TestExecutiveSummaryStructure:
    """R3-06: 結論1行→数値カード→3行以内の箇条書き→詳細は各章リンク、の構造。"""

    def _build(self) -> tuple[str, dict[str, Any]]:
        # 決済画面(P002)はリスクキーワード＋必須フィールドで高リスクスコアになる想定。
        screens = [
            _screen(
                "P001",
                title="トップ",
                fields=[_field("q")],
                to=["P002"],
            ),
            _screen(
                "P002",
                title="お支払い・決済",
                fields=[_field("card", required=True), _field("cvv", required=True)],
                buttons=["購入する"],
            ),
        ]
        report = _report(screens)
        domain = "example.com"
        docs = {"test_cases": _test_cases(domain, report)}
        return domain, report, docs  # type: ignore[return-value]

    def test_conclusion_line_names_highest_risk_screen(self) -> None:
        domain, report, docs = self._build()
        html_out = _executive_summary_html(domain, report, docs)
        assert "最重要リスク" in html_out
        # 決済画面が最もリスクスコアが高い（必須項目2件＋決済語＋操作要素）はずなので結論に出る
        conclusion_part = html_out.split('<div class="cards">')[0]
        assert "P002" in conclusion_part

    def test_conclusion_line_handles_no_screens(self) -> None:
        html_out = _executive_summary_html("example.com", _report([]), {"test_cases": ""})
        assert "画面が抽出されていない" in html_out
        assert "未確認" in html_out

    def test_numeric_cards_present(self) -> None:
        domain, report, docs = self._build()
        html_out = _executive_summary_html(domain, report, docs)
        assert "対象画面数" in html_out
        assert "生成ケース数" in html_out
        # 2画面のうち screens 数が数値カードに出ていること
        assert '<div class="num">2</div><div>対象画面数</div>' in html_out

    def test_bullet_list_has_at_most_three_items(self) -> None:
        domain, report, docs = self._build()
        html_out = _executive_summary_html(domain, report, docs)
        bullet_section = html_out.split("<ul>", 1)[1].split("</ul>", 1)[0]
        assert bullet_section.count("<li>") <= 3

    def test_links_to_each_chapter_section(self) -> None:
        domain, report, docs = self._build()
        docs = {
            **docs,
            "test_plan": "# plan",
            "test_analysis": "# analysis",
        }
        html_out = _executive_summary_html(domain, report, docs)
        assert 'href="#section-test_plan"' in html_out
        assert 'href="#section-test_analysis"' in html_out

    def test_all_strings_are_escaped(self) -> None:
        """画面タイトルにXSS文字列が含まれても html.escape() されること（規約0-1）。"""
        screens = [
            _screen(
                "P001",
                title="<script>alert(1)</script>",
                fields=[_field("a", required=True), _field("b", required=True)],
            )
        ]
        report = _report(screens)
        docs = {"test_cases": _test_cases("example.com", report)}
        html_out = _executive_summary_html("example.com", report, docs)
        assert "<script>alert(1)</script>" not in html_out
        assert "&lt;script&gt;" in html_out


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
