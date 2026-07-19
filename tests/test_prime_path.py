"""プライムパス網羅（第7弾 C）の契約。

守るべきは「エッジ網羅を包含すること」「決定性」「到達不能プライムパスを記録すること」。
"""

from __future__ import annotations

from mbt.document_model import (
    EDGE_COVERAGE,
    PRIME_PATH_COVERAGE,
    build_document_mbt,
)


def _graph(nodes, edges, entries=None):
    return {
        "nodes": [{"id": n} for n in nodes],
        "edges": [{"from": a, "to": b} for a, b in edges],
        "entry_nodes": entries or [nodes[0]],
    }


def _reqs():
    return {"requirements": [], "meta": {"source_files": []}}


def _node_paths(model):
    return [p["node_ids"] for p in model["paths"]]


# ─────────────────── 基本 ───────────────────


def test_linear_graph_has_single_prime_path() -> None:
    model = build_document_mbt(
        _graph(["A", "B", "C"], [("A", "B"), ("B", "C")]), _reqs(), criterion=PRIME_PATH_COVERAGE
    )

    assert _node_paths(model) == [["A", "B", "C"]]
    assert model["coverage"]["rate"] == 1.0


def test_self_loop_is_captured_as_one_cycle() -> None:
    """自己ループ B->B を1周として含む（エッジ網羅はこれを踏み損ねうる）。"""
    model = build_document_mbt(
        _graph(["A", "B"], [("A", "B"), ("B", "B")]), _reqs(), criterion=PRIME_PATH_COVERAGE
    )

    paths = _node_paths(model)
    assert any("B" in p and p.count("B") == 2 for p in paths)  # B,B の周回を含む


def test_diamond_graph_prime_paths_match_hand_calculation() -> None:
    # A->B->D, A->C->D
    model = build_document_mbt(
        _graph(["A", "B", "C", "D"], [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]),
        _reqs(),
        criterion=PRIME_PATH_COVERAGE,
    )

    paths = {tuple(p) for p in _node_paths(model)}
    assert ("A", "B", "D") in paths
    assert ("A", "C", "D") in paths


def test_prime_paths_subsume_edge_coverage() -> None:
    """プライムパス網羅の実行パス群は、全エッジを踏む（エッジ網羅を包含）。"""
    edges = [("A", "B"), ("A", "C"), ("B", "C"), ("C", "A")]
    model = build_document_mbt(
        _graph(["A", "B", "C"], edges), _reqs(), criterion=PRIME_PATH_COVERAGE
    )

    walked_edges = set()
    for path in _node_paths(model):
        for a, b in zip(path, path[1:], strict=False):
            walked_edges.add((a, b))
    assert set(edges) <= walked_edges


# ─────────────────── 決定性・到達不能 ───────────────────


def test_generation_is_deterministic() -> None:
    g = _graph(["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "A")])

    first = build_document_mbt(g, _reqs(), criterion=PRIME_PATH_COVERAGE)
    second = build_document_mbt(g, _reqs(), criterion=PRIME_PATH_COVERAGE)

    assert _node_paths(first) == _node_paths(second)


def test_unreachable_prime_paths_are_recorded_not_dropped() -> None:
    # D->E は A から到達不能
    g = _graph(["A", "B", "D", "E"], [("A", "B"), ("D", "E")], entries=["A"])

    model = build_document_mbt(g, _reqs(), criterion=PRIME_PATH_COVERAGE)

    unreachable = model["summary"]["unreachable_prime_paths"]
    assert ["D", "E"] in unreachable


def test_summary_has_prime_specific_fields() -> None:
    model = build_document_mbt(
        _graph(["A", "B"], [("A", "B")]), _reqs(), criterion=PRIME_PATH_COVERAGE
    )

    assert "unreachable_prime_paths" in model["summary"]
    assert model["summary"]["enumeration_truncated"] is False


def test_edge_and_prime_criteria_both_valid() -> None:
    g = _graph(["A", "B"], [("A", "B")])

    edge_model = build_document_mbt(g, _reqs(), criterion=EDGE_COVERAGE)
    prime_model = build_document_mbt(g, _reqs(), criterion=PRIME_PATH_COVERAGE)

    assert edge_model["selection_criterion"] == EDGE_COVERAGE
    assert prime_model["selection_criterion"] == PRIME_PATH_COVERAGE
