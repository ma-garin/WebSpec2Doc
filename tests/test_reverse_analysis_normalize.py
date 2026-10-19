"""REA Evidence → reverse analysis モデルの正規化の契約。

守るべきは「静的構文の事実を実測や確定仕様に昇格させないこと」。method を推定しない・
partial を exact にしない・source map が欠損/古い/未解決なら元ソースを捏造しない・
未知 kind を黙って捨てない・source 本文と絶対 path を残さない。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from reverse_analysis.models import Diagnostic, to_json_value
from reverse_analysis.normalize import (
    LIMIT_DIGEST_MISMATCH,
    LIMIT_FILE_NOT_VERIFIED,
    LIMIT_LOCATION_COLLISION,
    LIMIT_METHOD_NOT_PROVIDED,
    LIMIT_ORIGINAL_CONTENT_UNAVAILABLE,
    LIMIT_SHARED_ENDPOINT,
    LIMIT_SOURCE_MAP_STALE,
    LIMIT_SOURCE_MAP_UNRESOLVED,
    LIMIT_UNRESOLVED_EXPRESSION,
    normalize_static,
)
from reverse_analysis.rea_adapter import AdapterResult, referenced_paths, validate_evidence, verify_file
from reverse_analysis.reconcile import reconcile, summarize
from test_reverse_analysis_adapter import copy_app, load_fixture, recommit


def adapt(evidence: dict[str, Any], root: Path) -> AdapterResult:
    """adapter の検証済み出力を、実行ファイル無しで組み立てる。"""
    result = validate_evidence(evidence)
    files = tuple(verify_file(root, path) for path in referenced_paths(result))
    status = "complete" if result["graph"]["coverage"]["status"] == "complete" else "partial"
    return AdapterResult(status, "6.7.0", (), result, evidence["evidence_id"], files)


def nodes_of(evidence: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [n for n in evidence["normalized_result"]["graph"]["nodes"] if n["kind"] == kind]


def api_by_expression(normalized: Any) -> dict[str, Any]:
    return {c.expression: c for c in normalized.candidates if c.kind == "api"}


def test_endpoints_become_api_candidates_without_inventing_method(tmp_path: Path) -> None:
    root = copy_app(tmp_path)
    normalized = normalize_static(adapt(load_fixture(), root))
    assert normalized.status == "complete"
    apis = api_by_expression(normalized)
    items = apis["/api/items"]
    assert (items.method, items.path, items.origin, items.resolution) == (None, "/api/items", None, "exact")
    assert items.epistemic_state == "observed" and items.authority == "ast-static-analysis"
    assert LIMIT_METHOD_NOT_PROVIDED in items.limitations
    assert items.location.unit == "line_column_utf16"
    line = (root / "dist" / "app.js").read_text().splitlines()[0]
    assert line[items.location.start_column : items.location.end_column].startswith('fetch("/api/items")')
    assert items.artifact_path == "dist/app.js" and items.artifact_sha256 == next(
        a.sha256 for a in normalized.artifacts if a.path == "dist/app.js"
    )


def test_partial_endpoint_keeps_expression_and_is_not_resolved(tmp_path: Path) -> None:
    normalized = normalize_static(adapt(load_fixture(), copy_app(tmp_path)))
    user = api_by_expression(normalized)["`/api/users/${id}`"]
    assert (user.resolution, user.path, user.origin) == ("partial", None, None)
    assert LIMIT_UNRESOLVED_EXPRESSION in user.limitations


def test_absolute_static_url_keeps_its_own_origin_and_query_flag(tmp_path: Path) -> None:
    normalized = normalize_static(adapt(load_fixture(), copy_app(tmp_path)))
    orders = api_by_expression(normalized)["https://api.example.test/v1/orders?limit=5"]
    assert (orders.origin, orders.path, orders.query_dependent) == ("https://api.example.test", "/v1/orders", True)


def _items_node(evidence: dict[str, Any]) -> dict[str, Any]:
    return next(n for n in nodes_of(evidence, "endpoint") if n["observations"][0]["properties"]["value"] == "/api/items")


def test_colliding_candidates_at_one_location_are_all_kept(tmp_path: Path) -> None:
    evidence = load_fixture()
    node = _items_node(evidence)
    other = json.loads(json.dumps(node["observations"][0]))
    other["properties"]["value"] = "/api/other"
    node["observations"].append(other)
    twin = json.loads(json.dumps(node))  # 同じ位置・同じ値を別 node（別 identity）からも出す
    twin["identity"]["key"] = "/api/items#twin"
    twin["observations"] = twin["observations"][:1]
    evidence["normalized_result"]["graph"]["nodes"].append(twin)
    normalized = normalize_static(adapt(recommit(evidence), copy_app(tmp_path)))
    at_items = [c for c in normalized.candidates if c.kind == "api" and c.expression in ("/api/items", "/api/other")]
    assert sorted(c.expression for c in at_items) == ["/api/items", "/api/items", "/api/other"]
    assert len({c.id for c in at_items}) == 3
    assert all(f"{LIMIT_LOCATION_COLLISION}:3" in c.limitations for c in at_items)
    assert all(c.method is None for c in at_items)
    assert any(d.code == "static_candidate_location_collision" for d in normalized.diagnostics)
    again = normalize_static(adapt(recommit(evidence), copy_app(tmp_path / "again")))
    assert [c.id for c in again.candidates] == [c.id for c in normalized.candidates]


def test_same_path_at_different_locations_keeps_ambiguity(tmp_path: Path) -> None:
    evidence = load_fixture()
    twin = json.loads(json.dumps(_items_node(evidence)))
    twin["identity"]["key"] = "/api/items#second-call"
    twin["observations"][0]["evidence"]["location"]["value"]["start"]["column"] += 1
    evidence["normalized_result"]["graph"]["nodes"].append(twin)
    normalized = normalize_static(adapt(recommit(evidence), copy_app(tmp_path)))
    items = [c for c in normalized.candidates if c.kind == "api" and c.path == "/api/items"]
    assert len(items) == 2 and items[0].id != items[1].id
    assert all(f"{LIMIT_SHARED_ENDPOINT}:2" in c.limitations for c in items)
    assert not any(lim.startswith(LIMIT_LOCATION_COLLISION) for c in items for lim in c.limitations)


def test_static_candidates_are_never_matched_against_runtime(tmp_path: Path) -> None:
    normalized = normalize_static(adapt(load_fixture(), copy_app(tmp_path)))
    relations = reconcile(normalized.candidates, ())
    summary = summarize(normalized.candidates, (), relations)
    assert summary.matched_relations == 0
    assert all(r.epistemic_state != "observed" for r in relations)


def test_source_map_without_content_records_original_name_only(tmp_path: Path) -> None:
    normalized = normalize_static(adapt(load_fixture(), copy_app(tmp_path)))
    (source,) = [c for c in normalized.candidates if c.kind == "source"]
    assert source.path == "../src/app.ts" and source.resolution == "partial"
    assert LIMIT_ORIGINAL_CONTENT_UNAVAILABLE in source.limitations
    assert source.artifact_path == "dist/app.js.map"


def test_stale_source_map_is_unknown_and_status_partial(tmp_path: Path) -> None:
    root = copy_app(tmp_path)
    (root / "dist" / "app.js.map").write_text('{"version":3,"sources":["../src/other.ts"],"mappings":""}')
    normalized = normalize_static(adapt(load_fixture(), root))
    (source,) = [c for c in normalized.candidates if c.kind == "source"]
    assert (source.epistemic_state, source.resolution) == ("unknown", "unavailable")
    assert LIMIT_SOURCE_MAP_STALE in source.limitations and LIMIT_DIGEST_MISMATCH in source.limitations
    assert normalized.status == "partial"
    assert {d.code for d in normalized.diagnostics} >= {"source_map_stale", "static_artifact_digest_mismatch"}


def test_missing_source_map_is_unknown_not_original_source(tmp_path: Path) -> None:
    root = copy_app(tmp_path)
    (root / "dist" / "app.js.map").rename(tmp_path / "moved.map")
    normalized = normalize_static(adapt(load_fixture(), root))
    (source,) = [c for c in normalized.candidates if c.kind == "source"]
    assert (source.epistemic_state, source.resolution) == ("unknown", "unavailable")
    assert "dist/app.js.map" not in {a.path for a in normalized.artifacts}
    # coverage には実在する理由だけを足す（digest 不一致と偽らない）
    assert normalized.coverage.status == "partial"
    assert LIMIT_FILE_NOT_VERIFIED in normalized.coverage.limitations
    assert LIMIT_DIGEST_MISMATCH not in normalized.coverage.limitations


def test_changed_source_map_adds_only_digest_mismatch_to_coverage(tmp_path: Path) -> None:
    root = copy_app(tmp_path)
    (root / "dist" / "app.js.map").write_text("{not json")
    normalized = normalize_static(adapt(load_fixture(), root))
    assert normalized.coverage.status == "partial"
    assert LIMIT_DIGEST_MISMATCH in normalized.coverage.limitations
    assert LIMIT_FILE_NOT_VERIFIED not in normalized.coverage.limitations


def test_both_file_problems_are_added_in_fixed_order(tmp_path: Path) -> None:
    root = copy_app(tmp_path)
    (root / "dist" / "app.js.map").write_text("{not json")
    (root / "dist" / "app.js").rename(tmp_path / "moved.js")
    limits = normalize_static(adapt(load_fixture(), root)).coverage.limitations
    tail = [lim for lim in limits if lim in (LIMIT_DIGEST_MISMATCH, LIMIT_FILE_NOT_VERIFIED)]
    assert tail == [LIMIT_DIGEST_MISMATCH, LIMIT_FILE_NOT_VERIFIED]


def test_unresolved_source_map_reference_is_unknown(tmp_path: Path) -> None:
    evidence = load_fixture()
    (module,) = nodes_of(evidence, "source-module")
    module["observations"][0]["source_map_reference"]["resolution"] = {"kind": "unresolved", "reason": "outside root"}
    normalized = normalize_static(adapt(recommit(evidence), copy_app(tmp_path)))
    (source,) = [c for c in normalized.candidates if c.kind == "source"]
    assert (source.epistemic_state, source.resolution) == ("unknown", "unavailable")
    assert LIMIT_SOURCE_MAP_UNRESOLVED in source.limitations


def test_unknown_and_unmapped_kinds_are_kept_as_unsupported(tmp_path: Path) -> None:
    evidence = load_fixture()
    (asset,) = nodes_of(evidence, "javascript-asset")
    future = json.loads(json.dumps(asset))
    future["kind"] = "future-kind"
    evidence["normalized_result"]["graph"]["nodes"].append(future)
    normalized = normalize_static(adapt(recommit(evidence), copy_app(tmp_path)))
    kinds = sorted(u.kind for u in normalized.unsupported)
    assert kinds == ["future-kind", "javascript-asset", "source-map"]
    assert all(u.json_pointer.startswith("/normalized_result/graph/nodes/") for u in normalized.unsupported)
    assert any(lim.startswith("unsupported_nodes:3(") for lim in normalized.coverage.limitations)


def test_truncated_provider_coverage_is_preserved(tmp_path: Path) -> None:
    evidence = load_fixture()
    evidence["normalized_result"]["graph"]["coverage"] = {
        "status": "partial", "truncated": True, "omitted_count": 2,
        "limits": [{"name": "max_files", "value": 3, "unit": "items"}],
    }  # fmt: skip
    evidence["normalized_result"]["graph"]["limitations"] = ["File limit reached under /Users/someone/app"]
    normalized = normalize_static(adapt(recommit(evidence), copy_app(tmp_path)))
    cov = normalized.coverage
    assert (normalized.status, cov.status, cov.truncated, cov.omitted_count) == ("partial", "partial", True, 2)
    assert "provider_limit:max_files=3items" in cov.limitations
    assert "provider:File limit reached under <path>" in cov.limitations


def test_unknown_coverage_and_missing_skip_count_are_not_complete(tmp_path: Path) -> None:
    evidence = load_fixture()
    result = evidence["normalized_result"]
    result["graph"]["coverage"] = {"status": "unknown", "truncated": False, "omitted_count": None, "limits": []}
    del result["statistics"]["skipped_javascript_files"]
    normalized = normalize_static(adapt(recommit(evidence), copy_app(tmp_path)))
    assert normalized.coverage.status == "partial" and normalized.coverage.omitted_count is None
    assert {"provider_coverage_unknown", "skipped_javascript_files_unknown"} <= set(normalized.coverage.limitations)


def test_parse_failures_make_complete_coverage_partial(tmp_path: Path) -> None:
    evidence = load_fixture()
    evidence["normalized_result"]["statistics"]["parse_failures"] = 1
    normalized = normalize_static(adapt(recommit(evidence), copy_app(tmp_path)))
    assert normalized.status == "partial" and "parse_failures:1" in normalized.coverage.limitations


def test_adapter_failure_yields_explicit_unavailable_not_empty_success() -> None:
    diag = Diagnostic("missing_provider", "error", "provider", "REA が見つかりません。", "導入してください。")
    normalized = normalize_static(AdapterResult("unavailable", None, (diag,)))
    assert (normalized.status, normalized.candidates, normalized.artifacts) == ("unavailable", (), ())
    assert normalized.coverage.status == "unavailable" and "missing_provider" in normalized.coverage.limitations
    assert normalized.diagnostics == (diag,)


def test_normalization_is_deterministic_and_keeps_no_source_body_or_root(tmp_path: Path) -> None:
    root = copy_app(tmp_path)
    first = to_json_value(normalize_static(adapt(load_fixture(), root)))
    second = to_json_value(normalize_static(adapt(load_fixture(), root)))
    assert first == second
    dumped = json.dumps(first, ensure_ascii=False)
    assert "async function" not in dumped and "Promise<unknown>" not in dumped
    assert str(root) not in dumped and str(tmp_path) not in dumped
    ids = [c["id"] for c in first["candidates"]]
    assert ids == sorted(ids) and len(ids) == len(set(ids))
