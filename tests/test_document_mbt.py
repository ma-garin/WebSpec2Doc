"""第3弾 S1: 文書駆動MBTエンジンの公開契約。"""

from __future__ import annotations

import json
from pathlib import Path

from mbt.document_model import build_document_mbt, save_document_mbt


def _graph() -> dict:
    return {
        "nodes": [
            {"id": "P001", "title": "入口", "url": "https://example.com/"},
            {"id": "P002", "title": "検索", "url": "https://example.com/search"},
            {"id": "P003", "title": "一覧", "url": "https://example.com/list"},
            {"id": "P004", "title": "詳細", "url": "https://example.com/detail"},
        ],
        "edges": [
            {"from": "P001", "to": "P002", "trace_id": "P001->P002"},
            {"from": "P001", "to": "P003", "trace_id": "P001->P003"},
            {"from": "P002", "to": "P004", "trace_id": "P002->P004"},
            {"from": "P003", "to": "P004", "trace_id": "P003->P004"},
        ],
        "entry_nodes": ["P001"],
    }


def _requirements() -> dict:
    return {
        "meta": {"source_files": ["requirements.xlsx"]},
        "requirements": [
            {"req_id": "REQ-01", "page_id": "P002", "status": "screen_only"},
            {"req_id": "REQ-02", "page_id": "P004", "status": "covered"},
        ],
    }


def test_vertex_coverage_returns_deterministic_paths_with_requirement_trace() -> None:
    result = build_document_mbt(_graph(), _requirements(), criterion="vertex_coverage")

    assert [path["node_ids"] for path in result["paths"]] == [
        ["P001"],
        ["P001", "P002"],
        ["P001", "P003"],
        ["P001", "P002", "P004"],
    ]
    assert result["paths"][1]["requirement_ids"] == ["REQ-01"]
    assert result["paths"][3]["requirement_ids"] == ["REQ-01", "REQ-02"]
    assert result["coverage"] == {
        "covered": 4,
        "total": 4,
        "rate": 1.0,
        "unreachable_node_ids": [],
    }
    assert result["source_files"] == ["requirements.xlsx"]


def test_edge_coverage_returns_one_reachable_path_per_measured_edge() -> None:
    result = build_document_mbt(_graph(), _requirements(), criterion="edge_coverage")

    assert [path["node_ids"] for path in result["paths"]] == [
        ["P001", "P002"],
        ["P001", "P003"],
        ["P001", "P002", "P004"],
        ["P001", "P003", "P004"],
    ]
    assert result["coverage"] == {
        "covered": 4,
        "total": 4,
        "rate": 1.0,
        "unreachable_node_ids": [],
    }


def test_reached_target_returns_shortest_path_to_requested_measured_screen() -> None:
    result = build_document_mbt(
        _graph(),
        _requirements(),
        criterion="reached_target",
        target_page_id="P004",
    )

    assert [path["node_ids"] for path in result["paths"]] == [["P001", "P002", "P004"]]
    assert result["paths"][0]["requirement_ids"] == ["REQ-01", "REQ-02"]
    assert result["coverage"] == {
        "covered": 1,
        "total": 1,
        "rate": 1.0,
        "unreachable_node_ids": [],
    }


def test_cycle_without_natural_entry_uses_stable_fallback_and_records_reason() -> None:
    graph = {
        "nodes": [{"id": "P002"}, {"id": "P001"}],
        "edges": [
            {"from": "P001", "to": "P002"},
            {"from": "P002", "to": "P001"},
        ],
        "entry_nodes": [],
    }

    result = build_document_mbt(graph, {"requirements": []}, criterion="vertex_coverage")

    assert [path["node_ids"] for path in result["paths"]] == [
        ["P001"],
        ["P001", "P002"],
    ]
    assert result["summary"]["entry_node_ids"] == ["P001"]
    assert result["summary"]["entry_strategy"] == "cycle_fallback"


def test_unmatched_document_requirement_remains_visible_without_invented_node() -> None:
    requirements = _requirements()
    requirements["requirements"].append(
        {
            "req_id": "REQ-99",
            "title": "未観測の管理画面",
            "page_id": "",
            "status": "unimplemented_suspect",
            "near_page_id": "P004",
        }
    )

    result = build_document_mbt(_graph(), requirements, criterion="vertex_coverage")

    assert [node["id"] for node in result["nodes"]] == ["P001", "P002", "P003", "P004"]
    assert result["unmatched_requirements"] == [
        {
            "req_id": "REQ-99",
            "title": "未観測の管理画面",
            "status": "unimplemented_suspect",
            "near_page_id": "P004",
        }
    ]


def test_mbt_paths_select_only_playwright_candidates_traced_to_their_nodes_and_edges() -> None:
    candidates = {
        "candidates": [
            {"id": "PW-0001", "trace_id": "P001"},
            {"id": "PW-0002", "trace_id": "P001->P002"},
            {"id": "PW-0003", "trace_id": "P002-F01-I01"},
            {"id": "PW-9999", "trace_id": "P999"},
        ]
    }

    result = build_document_mbt(
        _graph(),
        _requirements(),
        criterion="reached_target",
        target_page_id="P002",
        candidates_data=candidates,
    )

    assert result["paths"][0]["candidate_ids"] == ["PW-0001", "PW-0002", "PW-0003"]
    assert result["selected_candidate_ids"] == ["PW-0001", "PW-0002", "PW-0003"]


def test_save_document_mbt_writes_model_and_filtered_spec_candidates(tmp_path: Path) -> None:
    candidates = {
        "domain": "example.com",
        "candidates": [
            {"id": "PW-0001", "trace_id": "P001"},
            {"id": "PW-9999", "trace_id": "P999"},
        ],
    }
    model = build_document_mbt(
        _graph(),
        _requirements(),
        criterion="reached_target",
        target_page_id="P001",
        candidates_data=candidates,
    )

    paths = save_document_mbt(model, candidates, tmp_path)

    saved_model = json.loads(paths["document_mbt_json"].read_text(encoding="utf-8"))
    saved_candidates = json.loads(paths["document_candidates_json"].read_text(encoding="utf-8"))
    assert saved_model == model
    assert saved_candidates["domain"] == "example.com"
    assert saved_candidates["selection_source"] == "document_mbt"
    assert [item["id"] for item in saved_candidates["candidates"]] == ["PW-0001"]


def test_path_limit_marks_only_actual_truncation() -> None:
    graph = {
        "nodes": [{"id": f"P{index:03d}"} for index in range(100)],
        "edges": [{"from": f"P{index:03d}", "to": f"P{index + 1:03d}"} for index in range(99)],
        "entry_nodes": ["P000"],
    }

    exact_limit = build_document_mbt(graph, {"requirements": []}, criterion="vertex_coverage")
    graph["nodes"].append({"id": "P100"})
    graph["edges"].append({"from": "P099", "to": "P100"})
    over_limit = build_document_mbt(graph, {"requirements": []}, criterion="vertex_coverage")

    assert exact_limit["summary"]["truncated"] is False
    assert exact_limit["summary"]["truncation_reason"] == ""
    assert exact_limit["summary"]["omitted_path_count"] == 0
    assert exact_limit["summary"]["available_path_count"] == 100
    assert over_limit["summary"]["truncated"] is True
    assert over_limit["summary"]["truncation_reason"] == "max_paths_exceeded"
    assert over_limit["summary"]["omitted_path_count"] == 1
    assert over_limit["summary"]["available_path_count"] == 101


def test_empty_measured_graph_does_not_claim_full_coverage() -> None:
    result = build_document_mbt(
        {"nodes": [], "edges": [], "entry_nodes": []},
        {"requirements": []},
        criterion="vertex_coverage",
    )

    assert result["coverage"]["rate"] == 0.0
    assert result["paths"] == []
