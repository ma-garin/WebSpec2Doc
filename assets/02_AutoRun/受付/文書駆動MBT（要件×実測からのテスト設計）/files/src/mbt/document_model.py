"""文書要件と実測画面遷移を結合する決定的MBTエンジン。"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import networkx as nx

MAX_PATHS = 100
VERTEX_COVERAGE = "vertex_coverage"
EDGE_COVERAGE = "edge_coverage"
REACHED_TARGET = "reached_target"
PRIME_PATH_COVERAGE = "prime_path"

# プライムパス列挙の安全弁（組合せ爆発対策）。到達時は summary へ明示する。
MAX_PRIME_PATH_LENGTH = 30
MAX_PRIME_ENUMERATION = 5000


def save_document_mbt(
    model: dict[str, Any], candidates_data: dict[str, Any], output_dir: Path
) -> dict[str, Path]:
    """MBTモデルと、そのパスに対応するPlaywright候補を保存する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / "document_mbt.json"
    candidates_path = output_dir / "document_playwright_candidates.json"
    selected_ids = {str(item) for item in model.get("selected_candidate_ids", []) if str(item)}
    selected_candidates = [
        item
        for item in _dict_items(candidates_data.get("candidates", []))
        if str(item.get("id", "")) in selected_ids
    ]
    candidate_payload = {
        **{key: value for key, value in candidates_data.items() if key != "candidates"},
        "selection_source": "document_mbt",
        "selection_criterion": model.get("selection_criterion", ""),
        "candidates": selected_candidates,
    }
    model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8")
    candidates_path.write_text(
        json.dumps(candidate_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "document_mbt_json": model_path,
        "document_candidates_json": candidates_path,
    }


def build_document_mbt(
    graph_data: dict[str, Any],
    requirement_data: dict[str, Any],
    *,
    criterion: str,
    target_page_id: str = "",
    candidates_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """実測グラフと文書要件の追跡結果からMBTモデルを構築する。"""
    if criterion not in {VERTEX_COVERAGE, EDGE_COVERAGE, REACHED_TARGET, PRIME_PATH_COVERAGE}:
        raise ValueError(f"unsupported selection criterion: {criterion}")

    graph = _to_graph(graph_data)
    entries, entry_strategy = _entry_nodes(graph_data, graph)
    reachable = _reachable_nodes(graph, entries)
    requirement_ids = _requirement_ids_by_page(requirement_data)
    prime_extra: dict[str, Any] = {}
    if criterion == PRIME_PATH_COVERAGE:
        primes, enumeration_truncated = _prime_paths(graph)
        paths, unreachable_primes = _prime_path_test_paths(graph, entries, primes)
        covered_prime_set = {
            prime for prime in primes if any(_is_subpath(prime, path) for path in paths)
        }
        covered, total = len(covered_prime_set), len(primes)
        available_path_count = len(primes)
        prime_extra = {
            "unreachable_prime_paths": [list(prime) for prime in unreachable_primes],
            "enumeration_truncated": enumeration_truncated,
        }
    elif criterion == VERTEX_COVERAGE:
        paths = _vertex_paths(graph, entries)
        covered, total = len({node_id for path in paths for node_id in path}), len(graph.nodes)
        available_path_count = len(reachable)
    elif criterion == EDGE_COVERAGE:
        paths = _edge_paths(graph, entries)
        covered_edges = {
            (source, target)
            for path in paths
            for source, target in zip(path, path[1:], strict=False)
        }
        covered, total = len(covered_edges), len(graph.edges)
        available_path_count = sum(1 for source, _target in graph.edges if source in reachable)
    else:
        if not target_page_id or target_page_id not in graph:
            raise ValueError("target_page_id must identify a measured screen")
        paths = _target_paths(graph, entries, target_page_id)
        covered, total = (1 if paths else 0), 1
        available_path_count = len(paths)
    all_nodes = sorted(str(node_id) for node_id in graph.nodes)
    unreachable = [node_id for node_id in all_nodes if node_id not in reachable]
    candidates = _dict_items((candidates_data or {}).get("candidates", []))
    path_payloads = [
        _path_payload(index, node_ids, requirement_ids, candidates)
        for index, node_ids in enumerate(paths, 1)
    ]
    selected_candidate_ids = list(
        dict.fromkeys(
            candidate_id
            for path_payload in path_payloads
            for candidate_id in path_payload["candidate_ids"]
        )
    )

    return {
        "selection_criterion": criterion,
        "nodes": [
            {
                **node,
                "requirement_ids": requirement_ids.get(str(node.get("id", "")), []),
                "evidence": "measured_screen",
            }
            for node in _stable_nodes(graph_data)
        ],
        "edges": _stable_edges(graph_data),
        "paths": path_payloads,
        "selected_candidate_ids": selected_candidate_ids,
        "coverage": {
            "covered": covered,
            "total": total,
            "rate": covered / total if total else 0.0,
            "unreachable_node_ids": unreachable,
        },
        "summary": {
            "entry_node_ids": entries,
            "entry_strategy": entry_strategy,
            "path_limit": MAX_PATHS,
            "available_path_count": available_path_count,
            "truncated": available_path_count > len(paths),
            "truncation_reason": (
                "max_paths_exceeded" if available_path_count > len(paths) else ""
            ),
            "omitted_path_count": max(0, available_path_count - len(paths)),
            **prime_extra,
        },
        "unmatched_requirements": _unmatched_requirements(requirement_data, graph),
        "source_files": [
            Path(str(item)).name
            for item in requirement_data.get("meta", {}).get("source_files", [])
        ],
    }


def _to_graph(graph_data: dict[str, Any]) -> nx.DiGraph:
    graph = nx.DiGraph()
    for node in _stable_nodes(graph_data):
        node_id = str(node.get("id", ""))
        if node_id:
            graph.add_node(node_id)
    for edge in _stable_edges(graph_data):
        source, target = str(edge.get("from", "")), str(edge.get("to", ""))
        if source in graph and target in graph:
            graph.add_edge(source, target)
    return graph


def _stable_nodes(graph_data: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [node for node in graph_data.get("nodes", []) if isinstance(node, dict)]
    return sorted(nodes, key=lambda node: str(node.get("id", "")))


def _stable_edges(graph_data: dict[str, Any]) -> list[dict[str, Any]]:
    edges = [edge for edge in graph_data.get("edges", []) if isinstance(edge, dict)]
    return sorted(
        edges,
        key=lambda edge: (
            str(edge.get("from", "")),
            str(edge.get("to", "")),
            str(edge.get("trace_id", "")),
        ),
    )


def _entry_nodes(graph_data: dict[str, Any], graph: nx.DiGraph) -> tuple[list[str], str]:
    configured = sorted(
        str(node_id) for node_id in graph_data.get("entry_nodes", []) if str(node_id) in graph
    )
    if configured:
        return configured, "configured"
    inferred = sorted(str(node_id) for node_id, degree in graph.in_degree() if degree == 0)
    if inferred:
        return inferred, "inferred"
    if graph:
        return [sorted(str(node_id) for node_id in graph.nodes)[0]], "cycle_fallback"
    return [], "empty"


def _vertex_paths(graph: nx.DiGraph, entries: list[str]) -> list[list[str]]:
    paths: list[list[str]] = []
    for target in sorted(str(node_id) for node_id in graph.nodes):
        candidates: list[list[str]] = []
        for entry in entries:
            try:
                candidates.append(list(nx.shortest_path(graph, entry, target)))
            except nx.NetworkXNoPath:
                continue
        if candidates:
            paths.append(min(candidates, key=lambda path: (len(path), path)))
    return sorted(paths, key=lambda path: (len(path), path))[:MAX_PATHS]


def _edge_paths(graph: nx.DiGraph, entries: list[str]) -> list[list[str]]:
    paths: list[list[str]] = []
    for source, target in sorted((str(source), str(target)) for source, target in graph.edges):
        prefixes: list[list[str]] = []
        for entry in entries:
            try:
                prefixes.append(list(nx.shortest_path(graph, entry, source)))
            except nx.NetworkXNoPath:
                continue
        if prefixes:
            prefix = min(prefixes, key=lambda path: (len(path), path))
            paths.append([*prefix, target])
    return sorted(paths, key=lambda path: (len(path), path))[:MAX_PATHS]


def _target_paths(graph: nx.DiGraph, entries: list[str], target: str) -> list[list[str]]:
    candidates: list[list[str]] = []
    for entry in entries:
        try:
            candidates.append(list(nx.shortest_path(graph, entry, target)))
        except nx.NetworkXNoPath:
            continue
    if not candidates:
        return []
    return [min(candidates, key=lambda path: (len(path), path))]


def _prime_paths(graph: nx.DiGraph) -> tuple[list[tuple[str, ...]], bool]:
    """全プライムパスを列挙する（決定的・辞書順）。

    プライムパス = 単純パス（頂点重複なし。ただし先頭=末尾のサイクル1周は許す）で
    あり、他のいかなる単純パスの真部分パスでもないもの。全頂点起点のDFSで
    「これ以上伸ばせない単純パス」と「単純サイクル」を集め、極大のみ残す。

    戻り値の bool は列挙上限（MAX_PRIME_ENUMERATION）に達したか。
    """
    nodes = sorted(str(node_id) for node_id in graph.nodes)
    simple_maximal: set[tuple[str, ...]] = set()
    truncated = False

    for start in nodes:
        stack: list[tuple[str, ...]] = [(start,)]
        while stack:
            path = stack.pop()
            if len(simple_maximal) >= MAX_PRIME_ENUMERATION:
                truncated = True
                break
            extended = False
            if len(path) <= MAX_PRIME_PATH_LENGTH:
                for nxt in sorted(str(n) for n in graph.successors(path[-1])):
                    if nxt == path[0]:
                        # 先頭へ戻るサイクル（自己ループ含む）: 1周として確定
                        simple_maximal.add((*path, nxt))
                        extended = True
                    elif nxt not in path:
                        stack.append((*path, nxt))
                        extended = True
            if not extended:
                simple_maximal.add(path)
        if truncated:
            break

    # 真部分パスに含まれるものを除き、極大（＝プライム）のみ残す
    ordered = sorted(simple_maximal, key=lambda p: (-len(p), p))
    primes: list[tuple[str, ...]] = []
    for path in ordered:
        if not any(_is_strict_subpath(path, longer) for longer in primes):
            primes.append(path)
    return sorted(primes, key=lambda p: (len(p), p)), truncated


def _prime_path_test_paths(
    graph: nx.DiGraph, entries: list[str], primes: list[tuple[str, ...]]
) -> tuple[list[list[str]], list[tuple[str, ...]]]:
    """各プライムパスを entry からのプレフィクスで実行可能パスへ延長する。"""
    test_paths: list[list[str]] = []
    unreachable: list[tuple[str, ...]] = []
    for prime in primes:
        prefixes: list[list[str]] = []
        for entry in entries:
            if entry == prime[0]:
                prefixes.append([])
                continue
            try:
                shortest = list(nx.shortest_path(graph, entry, prime[0]))
                prefixes.append(shortest[:-1])
            except nx.NetworkXNoPath:
                continue
        if not prefixes:
            unreachable.append(prime)
            continue
        prefix = min(prefixes, key=lambda p: (len(p), p))
        test_paths.append([*prefix, *prime])
    return sorted(test_paths, key=lambda p: (len(p), p))[:MAX_PATHS], unreachable


def _is_subpath(needle: tuple[str, ...], haystack: list[str]) -> bool:
    """needle が haystack の連続部分列か。"""
    n = len(needle)
    return any(tuple(haystack[i : i + n]) == needle for i in range(len(haystack) - n + 1))


def _is_strict_subpath(needle: tuple[str, ...], haystack: tuple[str, ...]) -> bool:
    if len(needle) >= len(haystack):
        return False
    n = len(needle)
    return any(haystack[i : i + n] == needle for i in range(len(haystack) - n + 1))


def _reachable_nodes(graph: nx.DiGraph, entries: list[str]) -> set[str]:
    reachable: set[str] = set(entries)
    for entry in entries:
        reachable.update(str(node_id) for node_id in nx.descendants(graph, entry))
    return reachable


def _requirement_ids_by_page(requirement_data: dict[str, Any]) -> dict[str, list[str]]:
    result: defaultdict[str, list[str]] = defaultdict(list)
    for item in requirement_data.get("requirements", []):
        if not isinstance(item, dict):
            continue
        page_id, req_id = str(item.get("page_id", "")), str(item.get("req_id", ""))
        if page_id and req_id and req_id not in result[page_id]:
            result[page_id].append(req_id)
    return dict(result)


def _unmatched_requirements(
    requirement_data: dict[str, Any], graph: nx.DiGraph
) -> list[dict[str, str]]:
    unmatched: list[dict[str, str]] = []
    for item in requirement_data.get("requirements", []):
        if not isinstance(item, dict):
            continue
        page_id = str(item.get("page_id", ""))
        if page_id and page_id in graph:
            continue
        unmatched.append(
            {
                "req_id": str(item.get("req_id", "")),
                "title": str(item.get("title", "")),
                "status": str(item.get("status", "")),
                "near_page_id": str(item.get("near_page_id", "")),
            }
        )
    return unmatched


def _path_payload(
    index: int,
    node_ids: list[str],
    requirement_ids: dict[str, list[str]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    reqs: list[str] = []
    for node_id in node_ids:
        for req_id in requirement_ids.get(node_id, []):
            if req_id not in reqs:
                reqs.append(req_id)
    return {
        "path_id": f"DMBT-{index:03d}",
        "node_ids": node_ids,
        "edge_ids": [
            f"{source}->{target}" for source, target in zip(node_ids, node_ids[1:], strict=False)
        ],
        "requirement_ids": reqs,
        "candidate_ids": _candidate_ids_for_path(node_ids, candidates),
        "review_required": True,
    }


def _candidate_ids_for_path(node_ids: list[str], candidates: list[dict[str, Any]]) -> list[str]:
    node_set = set(node_ids)
    edge_set = {
        f"{source}->{target}" for source, target in zip(node_ids, node_ids[1:], strict=False)
    }
    result: list[str] = []
    for candidate in candidates:
        candidate_id = str(candidate.get("id", ""))
        trace_id = str(candidate.get("trace_id", ""))
        matched = (
            trace_id in node_set
            or trace_id in edge_set
            or any(trace_id.startswith(f"{node_id}-") for node_id in node_set)
        )
        if matched and candidate_id and candidate_id not in result:
            result.append(candidate_id)
    return result


def _dict_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
