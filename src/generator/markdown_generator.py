from __future__ import annotations

from urllib.parse import urlparse

import networkx as nx

from analyzer.html_analyzer import AnalyzedPage

EMPTY_CELL = "-"
FORMS_TITLE = "# フォーム一覧"
SCREENS_TITLE = "# 画面一覧"
POSTBACK_TITLE = "## 未追跡の遷移（href が javascript:）"


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
    return "\n".join(lines + rows + _postback_section(pages)) + "\n"


def _postback_section(pages: list[AnalyzedPage]) -> list[str]:
    """href が javascript: のため追えなかった遷移を節として出す。

    ASP.NET WebForms / DNN は __doPostBack で画面遷移するため、リンクとして
    辿れず画面一覧に現れない。何も書かないと「遷移が無い」と読めてしまうので、
    未追跡であることを明示する（evidence-only 原則）。検出ゼロなら節ごと出さず、
    既存レポートの形を変えない。
    """
    rows: list[str] = []
    for page in pages:
        for nav in page.page_data.postback_navigations:
            target = f"{nav.target}:{nav.argument}" if nav.argument else nav.target
            rows.append(
                f"| {page.page_id} | {_cell(nav.label)} | "
                f"{_cell(target)} | {_cell(nav.selector)} |"
            )
    if not rows:
        return []
    return [
        "",
        POSTBACK_TITLE,
        "",
        "これらの遷移はリンクではなくポストバックのため、クロール対象外（未追跡）です。",
        "",
        "| 画面ID | ラベル | 遷移先(target:argument) | セレクタ |",
        "|---|---|---|---|",
        *rows,
    ]


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
