from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

import networkx as nx

from analyzer.html_analyzer import AnalyzedPage
from crawler.page_crawler import PageData

DEFAULT_LINK_TEXT = "リンク"
_MAX_2SWITCH_PATHS = 50
_TP_ID_PREFIX = "TP"
_TP_ID_WIDTH = 3

# ISO/IEC/IEEE 29119-4:2015 の Chow N-switch カバレッジ定義:
#   0-switch カバレッジ = 全単一遷移（各遷移を 1 度以上通過）の達成率
#   1-switch カバレッジ = 全連続 2 遷移ペアの達成率
COVERAGE_DEFINITION_SOURCE = (
    "ISO/IEC/IEEE 29119-4:2015 §5.2 状態遷移テスト"
    "（Chow の N-switch カバレッジ: 0-switch=全単一遷移, 1-switch=全連続2遷移ペア）"
)

# ビジネスフロー優先度付けの対象となる画面分類（screen_classifier の分類と対応）
BUSINESS_SCREEN_LABELS: dict[str, str] = {
    "auth": "ログイン",
    "payment": "決済",
    "personal_info": "個人情報",
}
PRIORITY_HIGH = "高"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TransitionTestPath:
    """状態遷移テストの 1 テストパス。"""

    path_id: str
    nodes: tuple[str, ...]
    edges: tuple[str, ...]
    coverage: str
    test_objective: str


@dataclass(frozen=True)
class SwitchCoverage:
    """N-switch カバレッジの達成率（ISO/IEC/IEEE 29119-4 準拠）。"""

    coverage_type: str  # "0-switch" / "1-switch"
    covered: int
    total: int
    rate: float  # 0.0〜1.0（total=0 の場合は 1.0）
    definition_source: str = COVERAGE_DEFINITION_SOURCE


@dataclass(frozen=True)
class BusinessFlow:
    """業務クリティカル画面（認証・決済・個人情報）を通過するテストパス。"""

    flow_name: str  # 例: "ログイン→決済"
    path_id: str
    nodes: tuple[str, ...]
    screen_types: tuple[str, ...]
    priority: str  # 常に "高"


def build_graph(pages: list[AnalyzedPage]) -> nx.DiGraph:
    graph = nx.DiGraph()
    # 同一 URL の別状態レコードがある場合、リンク解決は初出（正規ページ）を指す
    url_to_id: dict[str, str] = {}
    for page in pages:
        url_to_id.setdefault(page.page_data.url, page.page_id)

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


STATE_NODE_SEPARATOR = "#state="


def _build_graph_from_pages(pages: list[PageData]) -> nx.DiGraph:
    """PageData リストから URL をノードとする有向グラフを構築する。

    リンクに加え、SPA 遷移（pushState/replaceState/hashchange）と
    ページ内アクションで出現した画面状態も遷移エッジとして供給する。
    """
    graph = nx.DiGraph()
    url_set = {page.url for page in pages}

    for page in pages:
        graph.add_node(page.url, title=page.title)

    for page in pages:
        for link in page.links:
            if link in url_set:
                graph.add_edge(page.url, link)
        # SPA 遷移エッジ（既知 URL 間のみ）
        for transition in page.spa_transitions:
            if transition.to_url in url_set:
                source = transition.from_url if transition.from_url in url_set else page.url
                graph.add_edge(source, transition.to_url, kind=transition.kind)
        # ページ内アクションで出現した画面状態を状態ノードとして追加
        for state in page.page_states:
            state_node = f"{page.url}{STATE_NODE_SEPARATOR}{state.state_id}"
            graph.add_node(state_node, title=f"{page.title}［{state.kind}］", is_state=True)
            graph.add_edge(page.url, state_node, kind="state")

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
        _make_path(i, node_list, coverage, url_to_title) for i, node_list in enumerate(raw_paths)
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


def compute_switch_coverage(
    pages: list[PageData],
    paths: list[TransitionTestPath],
) -> dict[str, SwitchCoverage]:
    """生成済みテストパスの 0-switch / 1-switch カバレッジ達成率を算出する。

    ISO/IEC/IEEE 29119-4:2015 の Chow N-switch カバレッジ定義に準拠:
      0-switch = グラフの全単一遷移のうちパスが通過した割合
      1-switch = 全連続 2 遷移ペア（u→v→w）のうちパスが通過した割合
    """
    graph = _build_graph_from_pages(pages)
    single_transitions: set[tuple[str, str]] = set(graph.edges())
    pair_transitions: set[tuple[str, str, str]] = {
        (u, v, w) for u, v in graph.edges() for w in graph.successors(v)
    }

    covered_singles: set[tuple[str, str]] = set()
    covered_pairs: set[tuple[str, str, str]] = set()
    for path in paths:
        nodes = path.nodes
        for i in range(len(nodes) - 1):
            covered_singles.add((nodes[i], nodes[i + 1]))
        for i in range(len(nodes) - 2):
            covered_pairs.add((nodes[i], nodes[i + 1], nodes[i + 2]))
    covered_singles &= single_transitions
    covered_pairs &= pair_transitions

    def _rate(covered: int, total: int) -> float:
        # 対象遷移が存在しない場合は「網羅すべきものがない」ため 1.0 とする
        return covered / total if total > 0 else 1.0

    return {
        "0-switch": SwitchCoverage(
            coverage_type="0-switch",
            covered=len(covered_singles),
            total=len(single_transitions),
            rate=_rate(len(covered_singles), len(single_transitions)),
        ),
        "1-switch": SwitchCoverage(
            coverage_type="1-switch",
            covered=len(covered_pairs),
            total=len(pair_transitions),
            rate=_rate(len(covered_pairs), len(pair_transitions)),
        ),
    }


def switch_coverage_to_dict(coverage: dict[str, SwitchCoverage]) -> dict[str, dict]:
    """SwitchCoverage マップを JSON シリアライズ可能な dict に変換する。"""
    return {
        key: {
            "coverage_type": value.coverage_type,
            "covered": value.covered,
            "total": value.total,
            "rate": round(value.rate, 4),
            "definition_source": value.definition_source,
        }
        for key, value in coverage.items()
    }


def classify_pages_for_flows(pages: list[PageData]) -> dict[str, str]:
    """各ページ URL を screen_classifier のルール分類で画面種別にマップする。"""
    from llm.screen_classifier import classify_screen_by_rules

    url_types: dict[str, str] = {}
    for page in pages:
        field_names = [field.name for form in page.forms for field in form.fields if field.name]
        classification = classify_screen_by_rules(page.title, page.headings, field_names)
        url_types[page.url] = classification.screen_type
    return url_types


def prioritize_business_flows(
    paths: list[TransitionTestPath],
    url_screen_types: dict[str, str],
) -> list[BusinessFlow]:
    """業務クリティカル画面（認証・決済・個人情報）を通過するパスを抽出する。

    通過画面の分類ラベルからフロー名（例: ログイン→決済）を自動命名し、
    優先度「高」を付与する。
    """
    flows: list[BusinessFlow] = []
    for path in paths:
        business_types: list[str] = []
        for node in path.nodes:
            screen_type = url_screen_types.get(node, "")
            if screen_type in BUSINESS_SCREEN_LABELS:
                # 連続する同種画面は 1 つに畳む
                if not business_types or business_types[-1] != screen_type:
                    business_types.append(screen_type)
        if not business_types:
            continue
        flow_name = "→".join(BUSINESS_SCREEN_LABELS[t] for t in business_types)
        flows.append(
            BusinessFlow(
                flow_name=flow_name,
                path_id=path.path_id,
                nodes=path.nodes,
                screen_types=tuple(business_types),
                priority=PRIORITY_HIGH,
            )
        )
    return flows


def business_flows_to_dict(flows: list[BusinessFlow]) -> list[dict]:
    """BusinessFlow リストを JSON シリアライズ可能な dict リストに変換する。"""
    return [
        {
            "flow_name": flow.flow_name,
            "path_id": flow.path_id,
            "nodes": list(flow.nodes),
            "screen_types": list(flow.screen_types),
            "priority": flow.priority,
        }
        for flow in flows
    ]


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
