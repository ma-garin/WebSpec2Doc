from __future__ import annotations

import json

import networkx as nx

from analyzer.html_analyzer import AnalyzedPage
from crawler.page_crawler import FieldData, FormData, PageData
from generator.json_reporter import generate_json_report


def test_fielddata_has_a11y_fields() -> None:
    field = FieldData(
        field_type="text",
        name="email",
        placeholder="",
        required=True,
        aria_label="メールアドレス",
        aria_required=True,
        role="textbox",
        has_visible_label=True,
    )
    assert field.aria_label == "メールアドレス"
    assert field.aria_required is True
    assert field.role == "textbox"
    assert field.has_visible_label is True


def test_fielddata_defaults_backward_compat() -> None:
    field = FieldData(field_type="text", name="q", placeholder="", required=False)
    assert field.aria_label == ""
    assert field.aria_required is False
    assert field.role == ""
    assert field.has_visible_label is False


def test_pagedata_has_a11y_issues() -> None:
    page = PageData(
        url="https://example.com/",
        title="Top",
        headings=(),
        links=(),
        forms=(),
        screenshot_path=None,
        a11y_issues=("img[alt欠落]: 3件", "ラベルなし入力: 2件"),
    )
    assert len(page.a11y_issues) == 2
    assert "img[alt欠落]" in page.a11y_issues[0]


def test_pagedata_a11y_issues_default_empty() -> None:
    page = PageData(
        url="https://example.com/",
        title="Top",
        headings=(),
        links=(),
        forms=(),
        screenshot_path=None,
    )
    assert page.a11y_issues == ()


def test_json_report_includes_a11y_fields() -> None:
    field = FieldData(
        field_type="email",
        name="email",
        placeholder="",
        required=True,
        aria_label="メール",
        has_visible_label=True,
    )
    form = FormData(action="/login", method="post", fields=(field,))
    page = PageData(
        url="https://example.com/login",
        title="ログイン",
        headings=("ログイン",),
        links=(),
        forms=(form,),
        screenshot_path=None,
        a11y_issues=("ラベルなし入力: 0件",),
    )
    analyzed = AnalyzedPage(page_data=page, page_id="P001", buttons=(), nav_elements=())
    graph = nx.DiGraph()
    graph.add_node("P001")

    report = json.loads(generate_json_report([analyzed], graph, "https://example.com/"))
    screen = report["screens"][0]
    assert screen["a11y_issues"] == ["ラベルなし入力: 0件"]
    field_data = screen["forms"][0]["fields"][0]
    assert field_data["aria_label"] == "メール"
    assert field_data["has_visible_label"] is True


def test_extract_a11y_issues_import() -> None:
    from crawler.link_extractor import extract_a11y_issues

    assert callable(extract_a11y_issues)
