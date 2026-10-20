"""実 REA 6.7.0 の原本出力（tests/fixtures/reverse_analysis/real/raw）による回帰。

raw は実 REA の stdout から絶対 input_path を ``<input>`` に置き換え、commitment を計算し直したもの
（加工内容は real/PROVENANCE.md）。偽の rea 実行ファイルがそれを返し、service と CLI 要約を通す。
"""

from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Any

import pytest

from reverse_analysis.models import SourceLocation, StaticCandidate
from reverse_analysis.reconcile import BASIS_ROUTE_STATIC_ONLY, route_relations
from reverse_analysis.reporter import (
    PROVIDER_EVIDENCE_KEY,
    TOP_LEVEL_KEYS,
    ReportSchemaError,
    format_summary,
    validate_document,
)
from reverse_analysis.service import (
    LIMIT_PROVIDER_NO_ROUTE,
    ReverseAnalysisRequest,
    run_reverse_analysis,
)
from test_reverse_analysis_cli import _fake_rea, _snapshot

REAL = Path(__file__).parent / "fixtures" / "reverse_analysis" / "real"
ROUTE_PATHS = {"/users", "/settings", "/users/:id", "/items"}


def _run(tmp_path: Path, case: str, app: str, *, opt_in: bool = False, cancel: bool = False) -> Any:
    raw = tmp_path / "raw.json"
    shutil.copyfile(REAL / "raw" / f"{case}.rea.json", raw)
    shutil.copytree(REAL / app, tmp_path / "input")
    rea = _fake_rea(tmp_path, f"sys.stdout.write(open({str(raw)!r}).read())\n")
    request = ReverseAnalysisRequest(
        str(tmp_path / "input"), str(_snapshot(tmp_path)), str(rea), str(tmp_path / "out"), opt_in
    )
    event = threading.Event()
    if cancel:
        event.set()
    return run_reverse_analysis(request, cancel_event=event)


@pytest.fixture(scope="module")
def controlled(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return _run(tmp_path_factory.mktemp("controlled"), "controlled", "app", opt_in=True)


def test_route_は_api_と分けて_inferred_にし_provider_の構文状態を別に残す(controlled: Any) -> None:
    doc = controlled.document
    routes = [c for c in doc["static_candidates"] if c["kind"] == "route"]
    assert {c["path"] for c in routes} == ROUTE_PATHS
    assert all(c["epistemic_state"] == "inferred" and c["method"] is None for c in routes)
    assert all("provider_syntax_state:observed" in c["limitations"] for c in routes)
    assert not [
        c for c in doc["static_candidates"] if c["kind"] == "api" and c["path"] in ROUTE_PATHS
    ]
    provenance = {p["candidate_id"]: p for p in doc[PROVIDER_EVIDENCE_KEY]["candidate_provenance"]}
    for route in routes:
        record = provenance[route["id"]]
        assert record["endpoint_kind"] == "route" and record["provider_state"] == "observed"
        assert (
            record["upstream_node_id"].startswith("jag_node_")
            and record["mechanism"] == "property:path"
        )
        assert record["location"]["value"]["kind"] == "source-range"
    assert LIMIT_PROVIDER_NO_ROUTE not in doc["coverage"]["static"]["limitations"]
    assert "provider_route_not_provided" not in {d["code"] for d in doc["diagnostics"]}


def test_route_は_runtime_API_と比べず_関係は_unknown(controlled: Any) -> None:
    doc = controlled.document
    route_ids = {c["id"] for c in doc["static_candidates"] if c["kind"] == "route"}
    related = [r for r in doc["relations"] if set(r["static_ids"]) & route_ids]
    assert len(related) == 4
    assert all(r["classification"] == "unknown" and r["runtime_ids"] == [] for r in related)
    assert all(r["basis"] == BASIS_ROUTE_STATIC_ONLY for r in related)


def test_route_の純粋ルール_同一path複数は_ambiguous_path不明は_unknown() -> None:
    def route(line: int, path: str | None, resolution: str = "exact") -> StaticCandidate:
        loc = SourceLocation("a.js", "line_column_utf16", line, 0, line, 1)
        return StaticCandidate(
            f"sc-{line}", "route", "a.js", "x", loc, resolution, "inferred", "a", path=path
        )

    relations = route_relations(
        [route(1, "/a"), route(2, "/a"), route(3, None, "partial"), route(4, "/b")]
    )
    by_ids = {r.static_ids: (r.classification, r.basis) for r in relations}
    assert by_ids[("sc-1", "sc-2")] == ("ambiguous", BASIS_ROUTE_STATIC_ONLY)
    assert by_ids[("sc-3",)] == ("unknown", "path_unresolved")
    assert by_ids[("sc-4",)] == ("unknown", BASIS_ROUTE_STATIC_ONLY)


def test_HTTP_method_は_Evidence_に無いので全て欠測のまま(controlled: Any) -> None:
    doc = controlled.document
    apis = [c for c in doc["static_candidates"] if c["kind"] == "api"]
    # method は静的な構文（fetch の options・XHR#open の引数）から読めたものだけ。実測の値とは扱わない
    assert apis and all(c["method"] is None or "method_from_static_syntax" in c["limitations"] for c in apis)
    api_ids = {c["id"] for c in apis}
    for relation in doc["relations"]:
        if set(relation["static_ids"]) & api_ids:
            # method/path が揃っても推定（inferred）止まり。matched にはしない
            assert relation["classification"] in ("unknown", "ambiguous", "inferred")
            assert relation["classification"] != "matched"


def test_imports_を上流の_node_参照と出典つきで保存する(controlled: Any) -> None:
    edges = controlled.document[PROVIDER_EVIDENCE_KEY]["dependency_edges"]
    assert len(edges) == 14 and all(e["relation"] == "imports" for e in edges)
    assert all(
        e["source_node_id"].startswith("jag_node_") and e["target_node_id"].startswith("jag_node_")
        for e in edges
    )
    assert all(
        e["provider_state"] == "inferred"
        and e["provider_authority"] == "static-relationship-inference"
        for e in edges
    )
    main = {
        e["properties"]["specifier"]
        for e in edges
        if e["location"]["value"]["source"] == "modules/main.js"
    }
    text = (REAL / "app" / "modules" / "main.js").read_text(encoding="utf-8")
    assert main and all(spec in text for spec in main)
    assert [e["edge_id"] for e in edges] == sorted(e["edge_id"] for e in edges)


def test_source_map_は元ソース名だけを信用し鮮度と行対応は未確認と明記する(controlled: Any) -> None:
    sources = [c for c in controlled.document["static_candidates"] if c["kind"] == "source"]
    assert [c["path"] for c in sources] == ["src/app.ts"]
    assert {"source_map_freshness_not_verified", "generated_to_original_range_not_provided"} <= set(
        sources[0]["limitations"]
    )


def test_既定では_provider_evidence_を出さず従来のキーのまま(tmp_path: Path) -> None:
    outcome = _run(tmp_path, "controlled", "app")
    assert tuple(outcome.document) == TOP_LEVEL_KEYS and outcome.exit_code == 0


def test_同じ入力から同じバイト列_絶対パスを含まない(tmp_path: Path, controlled: Any) -> None:
    again = _run(tmp_path, "controlled", "app", opt_in=True)
    first, second = controlled.output_path.read_bytes(), again.output_path.read_bytes()
    assert first == second
    assert (
        b"/Users/" not in first
        and b"/private/" not in first
        and str(tmp_path).encode() not in first
    )


def test_source_map_欠落は_provider_の理由つき診断で_complete(tmp_path: Path) -> None:
    outcome = _run(tmp_path, "missing", "missing", opt_in=True)
    doc = outcome.document
    assert (outcome.status, outcome.exit_code) == ("complete", 0)
    finding = doc[PROVIDER_EVIDENCE_KEY]["source_map_findings"]
    assert [(f["finding"], f["path"], f["provider_state"]) for f in finding] == [
        ("map_not-found", "app.js.map", "inferred")
    ]
    diag = next(d for d in doc["diagnostics"] if d["code"] == "provider_source_map_not_found")
    assert "app.js.map" in diag["message"] and "REA の理由" in diag["message"]
    assert (
        "provider_source_map:map_not-found:app.js.map" in doc["coverage"]["static"]["limitations"]
    )
    assert any("app.js.map" in line for line in format_summary(doc, "out"))


def test_source_map_破損は_unavailable_と_partial_を保ち_exit2(tmp_path: Path) -> None:
    outcome = _run(tmp_path, "malformed", "malformed", opt_in=True)
    doc = outcome.document
    assert (outcome.status, outcome.exit_code) == ("partial", 2)
    finding = doc[PROVIDER_EVIDENCE_KEY]["source_map_findings"]
    assert [(f["finding"], f["provider_state"], f["coverage_status"]) for f in finding] == [
        ("map_parse_failed", "unavailable", "partial")
    ]
    assert "provider:Source map is not valid JSON." in finding[0]["provider_limitations"]
    diag = next(d for d in doc["diagnostics"] if d["code"] == "provider_source_map_parse_failed")
    assert "Source map is not valid JSON." in diag["message"]


def test_取消は_opt_in_でも空の出典で_cancelled(tmp_path: Path) -> None:
    outcome = _run(tmp_path, "controlled", "app", opt_in=True, cancel=True)
    assert (outcome.status, outcome.exit_code) == ("cancelled", 130)
    assert outcome.document[PROVIDER_EVIDENCE_KEY] == {
        "candidate_provenance": [], "dependency_edges": [], "source_map_findings": []
    }  # fmt: skip


def test_provider_evidence_の形が違えば拒否する(controlled: Any) -> None:
    broken = {**controlled.document, PROVIDER_EVIDENCE_KEY: {"dependency_edges": []}}
    with pytest.raises(ReportSchemaError):
        validate_document(broken)
    with pytest.raises(ReportSchemaError):
        validate_document({**controlled.document, "extra": 1})
