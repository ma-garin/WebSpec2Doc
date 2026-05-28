from __future__ import annotations

import networkx as nx

from analyzer.html_analyzer import AnalyzedPage

DEFAULT_LINK_TEXT = "リンク"


def build_graph(pages: list[AnalyzedPage]) -> nx.DiGraph:
    graph = nx.DiGraph()
    url_to_id = {page.page_data.url: page.page_id for page in pages}

    for page in pages:
        graph.add_node(
            page.page_id,
            url=page.page_data.url,
            title=page.page_data.title,
            page_id=page.page_id,
            forms_count=len(page.page_data.forms),
            fields_count=_fields_count(page),
        )

    for page in pages:
        for link in page.page_data.links:
            target_id = url_to_id.get(link)
            if target_id is not None:
                graph.add_edge(page.page_id, target_id, link_text=DEFAULT_LINK_TEXT)

    return graph


def _fields_count(page: AnalyzedPage) -> int:
    return sum(len(form.fields) for form in page.page_data.forms)
