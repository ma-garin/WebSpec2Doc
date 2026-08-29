from __future__ import annotations

from urllib.parse import urlparse

import networkx as nx

from analyzer.html_analyzer import AnalyzedPage

DEFAULT_LINK_TEXT = "リンク"
MERMAID_HEADER = "graph LR"
# サイト全体の50%以上のページからリンクされるノードはナビゲーションリンクとみなす
NAV_MIN_RATIO = 0.5
NAV_MIN_NODES = 4  # ページ数がこれ未満のときはフィルタ不要


def generate_mermaid(
    graph: nx.DiGraph,
    pages: list[AnalyzedPage],
    suppress_nav: bool = True,
) -> str:
    page_by_id = {page.page_id: page for page in pages}
    lines = [MERMAID_HEADER]

    for node_id in graph.nodes:
        page = page_by_id.get(str(node_id))
        path = _url_path(page.page_data.url) if page else "/"
        lines.append(f'  {node_id}["{_escape_label(str(node_id))}<br/>{_escape_label(path)}"]')

    edges = list(graph.edges(data=True))
    if suppress_nav:
        edges = _filter_nav_edges(edges, graph)

    for source, target, data in edges:
        link_text = str(data.get("link_text") or DEFAULT_LINK_TEXT)
        lines.append(f"  {source} -->|{_escape_label(link_text)}| {target}")

    return "\n".join(lines) + "\n"


def _filter_nav_edges(
    edges: list[tuple],
    graph: nx.DiGraph,
) -> list[tuple]:
    node_count = graph.number_of_nodes()
    if node_count < NAV_MIN_NODES:
        return edges

    min_sources = max(2, int(node_count * NAV_MIN_RATIO))
    # 多くのページからリンクされるノード = ナビゲーションターゲット
    nav_targets: frozenset[str] = frozenset(
        str(n) for n in graph.nodes if graph.in_degree(n) >= min_sources
    )

    # ナビターゲットへのエッジは代表1本のみ残す（最初に出現したもの）
    seen_nav: set[str] = set()
    result: list[tuple] = []
    for source, target, data in edges:
        t = str(target)
        if t in nav_targets:
            if t not in seen_nav:
                seen_nav.add(t)
                result.append((source, target, data))
        else:
            result.append((source, target, data))
    return result


def _url_path(url: str) -> str:
    parsed = urlparse(url)
    if parsed.query:
        return f"{parsed.path or '/'}?{parsed.query}"
    return parsed.path or "/"


def _escape_label(value: str) -> str:
    return value.replace('"', "'").replace("[", "(").replace("]", ")")
