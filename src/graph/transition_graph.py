from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass

import networkx as nx

from analyzer.html_analyzer import AnalyzedPage
from crawler.page_crawler import PageData

DEFAULT_LINK_TEXT = "リンク"
_MAX_2SWITCH_PATHS = 50
_TP_ID_PREFIX = "TP"
_TP_ID_WIDTH = 3

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TransitionTestPath:
    """状態遷移テストの 1 テストパス。"""

    path_id: str
    nodes: tuple[str, ...]
    edges: tuple[str, ...]
    coverage: str
    test_objective: str


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


def _build_graph_from_pages(pages: list[PageData]) -> nx.DiGraph:
    """PageData リストから URL をノードとする有向グラフを構築する。"""
    graph = nx.DiGraph()
    url_set = {page.url for page in pages}

    for page in pages:
        graph.add_node(page.url, title=page.title)

    for page in pages:
        for link in page.links:
            if link in url_set:
                graph.add_edge(page.url, link)

    return graph


def generate_transition_tests(
    pages: list[PageData],
    coverage: str = "1-switch",
) -> list[TransitionTestPath]:
    """遷移グラフから状態遷移テストパスを自動生成する。

    coverage:
      "0-switch": 全ノード（ページ）を 1 度以上訪問するパスを生成
      "1-switch": 全エッジ（遷移）を 1 度以上通過するパスを生成
      "2-switch": 全エッジペア（連続 2 遷移）を 1 度以上通過するパスを生成（上限 50 パス）
    """
    graph = _build_graph_from_pages(pages)
    url_to_title = {page.url: page.title for page in pages}

    if coverage == "0-switch":
        raw_paths = [[url] for url in graph.nodes()]
    elif coverage == "1-switch":
        raw_paths = [[u, v] for u, v in graph.edges()]
    elif coverage == "2-switch":
        raw_paths = _collect_2switch_paths(graph)
    else:
        logger.warning("未知の coverage 値です: %s", coverage)
        raw_paths = []

    return [
        _make_path(i, node_list, coverage, url_to_title)
        for i, node_list in enumerate(raw_paths)
    ]


def _collect_2switch_paths(graph: nx.DiGraph) -> list[list[str]]:
    """全連続エッジペア (u→v→w) のパスを収集する（上限 _MAX_2SWITCH_PATHS 件）。"""
    paths: list[list[str]] = []
    for u, v in graph.edges():
        for w in graph.successors(v):
            paths.append([u, v, w])
            if len(paths) >= _MAX_2SWITCH_PATHS:
                return paths
    return paths


def _make_path(
    index: int,
    node_list: list[str],
    coverage: str,
    url_to_title: dict[str, str],
) -> TransitionTestPath:
    """node_list から TransitionTestPath を生成する。"""
    path_id = f"{_TP_ID_PREFIX}{index + 1:0{_TP_ID_WIDTH}d}"
    nodes = tuple(node_list)
    edges = tuple(
        f"{_short_label(node_list[i], url_to_title)}→{_short_label(node_list[i + 1], url_to_title)}"
        for i in range(len(node_list) - 1)
    )
    test_objective = _build_test_objective(coverage, node_list, url_to_title)
    return TransitionTestPath(
        path_id=path_id,
        nodes=nodes,
        edges=edges,
        coverage=coverage,
        test_objective=test_objective,
    )


def _short_label(url: str, url_to_title: dict[str, str]) -> str:
    """URL のタイトルを返す。タイトルがなければ URL のパス部分を返す。"""
    title = url_to_title.get(url, "")
    if title:
        return title
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.path or url


def _build_test_objective(
    coverage: str,
    node_list: list[str],
    url_to_title: dict[str, str],
) -> str:
    """coverage に応じた日本語テスト目的文を生成する。"""
    if coverage == "0-switch":
        label = _short_label(node_list[0], url_to_title)
        return f"「{label}」ページが正常に表示されることを確認"
    if coverage == "1-switch":
        from_label = _short_label(node_list[0], url_to_title)
        to_label = _short_label(node_list[1], url_to_title)
        return f"「{from_label}」から「{to_label}」への遷移を確認"
    if coverage == "2-switch":
        from_label = _short_label(node_list[0], url_to_title)
        mid_label = _short_label(node_list[1], url_to_title)
        to_label = _short_label(node_list[2], url_to_title)
        return f"「{from_label}」→「{mid_label}」→「{to_label}」の連続遷移を確認"
    return "遷移を確認"


def transition_tests_to_dict(paths: list[TransitionTestPath]) -> list[dict]:
    """TransitionTestPath リストを JSON シリアライズ可能な dict リストに変換する。"""
    result = []
    for path in paths:
        d = asdict(path)
        d["nodes"] = list(d["nodes"])
        d["edges"] = list(d["edges"])
        result.append(d)
    return result


def _fields_count(page: AnalyzedPage) -> int:
    return sum(len(form.fields) for form in page.page_data.forms)
