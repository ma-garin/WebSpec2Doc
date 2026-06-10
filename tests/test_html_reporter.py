"""html_reporter.py のスモークテスト。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import html as html_module

import networkx as nx

from analyzer.html_analyzer import AnalyzedPage, analyze_pages
from crawler.page_crawler import FieldData, FormData, PageData
from generator.html_reporter import generate_html_report


def _make_analyzed_page(
    url: str = "https://example.com/",
    title: str = "Test Page",
    forms: tuple[FormData, ...] = (),
) -> AnalyzedPage:
    """テスト用 AnalyzedPage を生成するヘルパー。"""
    page_data = PageData(
        url=url,
        title=title,
        headings=("Test Heading",),
        links=(),
        forms=forms,
        screenshot_path=None,
    )
    analyzed = analyze_pages([page_data])
    return analyzed[0]


def _empty_graph() -> nx.DiGraph:
    return nx.DiGraph()


def test_html_reporter_creates_output_file(tmp_path: Path) -> None:
    """html_reporter が HTML 文字列を返す基本スモークテスト。"""
    analyzed = [_make_analyzed_page()]
    graph = _empty_graph()
    graph.add_node(
        "P001",
        url="https://example.com/",
        title="Test Page",
        page_id="P001",
        forms_count=0,
        fields_count=0,
    )

    result = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content="graph LR\n  P001\n",
    )

    assert isinstance(result, str)
    assert len(result) > 0

    # ファイルに書き出して存在確認
    out = tmp_path / "report.html"
    out.write_text(result, encoding="utf-8")
    assert out.exists()
    assert out.stat().st_size > 0


def test_html_reporter_returns_valid_html_structure(tmp_path: Path) -> None:
    """生成された HTML が基本的な構造タグを持つ。"""
    analyzed = [_make_analyzed_page()]
    graph = _empty_graph()

    result = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content="graph LR\n",
    )

    assert "<!doctype html>" in result.lower() or "<!DOCTYPE html>" in result
    assert "<html" in result
    assert "</html>" in result
    assert "<body" in result
    assert "</body>" in result


def test_html_reporter_contains_page_id(tmp_path: Path) -> None:
    """生成 HTML に画面 ID (P001) が含まれる。"""
    analyzed = [_make_analyzed_page()]
    graph = _empty_graph()

    result = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content="graph LR\n",
    )

    assert "P001" in result


def test_html_reporter_escapes_xss_in_title(tmp_path: Path) -> None:
    """ページタイトルの XSS 文字が html.escape() でエスケープされる。"""
    xss_title = "<script>alert(1)</script>"
    analyzed = [_make_analyzed_page(title=xss_title)]
    graph = _empty_graph()

    result = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content="graph LR\n",
    )

    # リテラルの <script> タグがそのまま出力されてはいけない
    assert "<script>alert(1)</script>" not in result
    # エスケープ済み文字列が含まれること
    assert html_module.escape(xss_title) in result


def test_html_reporter_escapes_xss_in_target_url(tmp_path: Path) -> None:
    """target_url の XSS 文字がエスケープされる。"""
    xss_url = 'https://example.com/"><script>alert(1)</script>'
    analyzed = [_make_analyzed_page(url="https://example.com/")]
    graph = _empty_graph()

    result = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url=xss_url,
        mermaid_content="graph LR\n",
    )

    # 生の <script> タグが注入されていないこと
    assert '"><script>alert(1)</script>' not in result


def test_html_reporter_with_form(tmp_path: Path) -> None:
    """フォームを持つページの HTML レポートにフォーム情報が含まれる。"""
    field = FieldData(
        field_type="text",
        name="username",
        placeholder="ユーザー名",
        required=True,
    )
    form = FormData(action="/login", method="post", fields=(field,))
    analyzed = [
        _make_analyzed_page(url="https://example.com/login", title="ログイン", forms=(form,))
    ]
    graph = _empty_graph()

    result = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content="graph LR\n",
    )

    assert "username" in result
    assert "/login" in result


def test_html_reporter_multiple_pages(tmp_path: Path) -> None:
    """複数ページのレポートに全ページの ID が含まれる。"""
    page1 = PageData(
        url="https://example.com/",
        title="Home",
        headings=(),
        links=("https://example.com/about",),
        forms=(),
        screenshot_path=None,
    )
    page2 = PageData(
        url="https://example.com/about",
        title="About",
        headings=(),
        links=(),
        forms=(),
        screenshot_path=None,
    )
    analyzed = analyze_pages([page1, page2])

    graph = nx.DiGraph()
    graph.add_node("P001")
    graph.add_node("P002")
    graph.add_edge("P001", "P002")

    result = generate_html_report(
        pages=analyzed,
        graph=graph,
        form_summary=[],
        target_url="https://example.com/",
        mermaid_content="graph LR\n  P001-->P002\n",
    )

    assert "P001" in result
    assert "P002" in result
