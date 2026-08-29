from __future__ import annotations

from urllib.parse import urlparse

import networkx as nx

from analyzer.html_analyzer import AnalyzedPage

EMPTY_CELL = "-"
FORMS_TITLE = "# フォーム一覧"
SCREENS_TITLE = "# 画面一覧"


def generate_screens_markdown(
    pages: list[AnalyzedPage],
    graph: nx.DiGraph,
    target_url: str,
) -> str:
    lines = [
        SCREENS_TITLE,
        "",
        f"対象URL: {target_url}",
        "",
        "| # | 画面ID | URL | タイトル | フォーム数 | 遷移先 |",
        "|---:|---|---|---|---:|---|",
    ]
    rows = [_screen_row(index, page, graph) for index, page in enumerate(pages, start=1)]
    return "\n".join(lines + rows) + "\n"


def generate_forms_markdown(form_summary: list[dict[str, object]]) -> str:
    lines = [
        FORMS_TITLE,
        "",
        "| 画面ID | フィールド名 | 型 | 必須 | placeholder |",
        "|---|---|---|---|---|",
    ]
    rows = [_form_row(item) for item in form_summary]
    return "\n".join(lines + rows) + "\n"


def _screen_row(index: int, page: AnalyzedPage, graph: nx.DiGraph) -> str:
    transitions = ", ".join(str(node_id) for node_id in graph.successors(page.page_id))
    return (
        f"| {index} | {page.page_id} | {_url_path(page.page_data.url)} | "
        f"{_cell(page.page_data.title)} | {len(page.page_data.forms)} | "
        f"{_cell(transitions)} |"
    )


def _form_row(item: dict[str, object]) -> str:
    required = "Yes" if bool(item.get("required")) else "No"
    return (
        f"| {_cell(item.get('page_id'))} | {_cell(item.get('name'))} | "
        f"{_cell(item.get('field_type'))} | {required} | "
        f"{_cell(item.get('placeholder'))} |"
    )


def _url_path(url: str) -> str:
    parsed = urlparse(url)
    if parsed.query:
        return f"{parsed.path or '/'}?{parsed.query}"
    return parsed.path or "/"


def _cell(value: object) -> str:
    text = str(value) if value not in (None, "") else EMPTY_CELL
    return text.replace("|", "\\|").replace("\n", " ")
