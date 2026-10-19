"""GET /api/reverse-analysis: 画面向けに状態を取り違えず返すこと（実 REA 6.7.0 の出力で確認）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# 比較測定ファイル（value_measurement.json）の形。値は 2026-10-19 の実 REA 6.7.0 測定と同じ。
MEASUREMENT = {
    "conditions": {"repetitions": 1},
    "before": {"metrics": {"static_candidates": 0, "route_candidates": 0, "api_candidates": 0,
                           "module_dependency_edges": 0, "runtime_observations": 3}},
    "after": {"metrics": {"static_candidates": 35, "route_candidates": 4, "api_candidates": 9,
                          "module_dependency_edges": 14, "runtime_observations": 3}},
    "added_wall_seconds": 4.8129,
    "relative_score": {"before_answered": 3, "after_answered": 10, "total_questions": 11},
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    import web.routes.reverse_analysis as mod

    monkeypatch.setattr(mod, "scoped_output_dir", lambda _base: tmp_path)
    from web import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client(), tmp_path


def _doc() -> dict:
    """製品の出力形式（reverse_analysis.json）を最小構成で組む。値は実測の形に合わせる。"""
    return {
        "status": "partial",
        "producer": {"provider_version": "6.7.0"},
        "inputs": {"static_root_label": "app"},
        "static_candidates": [
            {"id": "s1", "kind": "route", "path": "/users/:id", "epistemic_state": "inferred",
             "resolution": "exact", "method": None,
             "location": {"artifact_path": "routes/app.js", "start_line": 3, "start_column": 71},
             "limitations": ["route_candidate_from_static_syntax"]},
            {"id": "s2", "kind": "api", "path": "/api/hidden", "epistemic_state": "observed",
             "resolution": "exact", "method": None,
             "location": {"artifact_path": "modules/api.js", "start_line": 1, "start_column": 31},
             "limitations": ["method_not_provided_by_provider"]},
        ],
        "runtime_observations": [
            {"id": "r1", "method": "GET", "path": "/api/items", "status_code": 200,
             "page_url": "https://app.example.com/items", "epistemic_state": "observed"},
        ],
        "relations": [{"static_ids": ["s1"], "basis": "route_static_only"}],
        "provider_evidence": {"dependency_edges": [
            {"properties": {"kind": "static-import", "specifier": "react-router-dom",
                            "resolution_status": "external"},
             "provider_state": "inferred",
             "location": {"value": {"source": "routes/app.js", "start": {"line": 2, "column": 0}}}},
        ]},
        "diagnostics": [
            {"code": "static_node_unsupported", "severity": "info",
             "message": "未対応の node（kind=artifact node_id=jag_node_x）", "next_action": "x"},
        ],
        "coverage": {"static": {"limitations": []}, "runtime": {"limitations": []}},
    }


def _place(base: Path, doc: dict | str, measurement: bool = False) -> None:
    d = base / "app.example.com" / "reverse_analysis"
    d.mkdir(parents=True)
    (d / "reverse_analysis.json").write_text(doc if isinstance(doc, str) else json.dumps(doc))
    if measurement:
        (d / "value_measurement.json").write_text(json.dumps(MEASUREMENT))
    (d / "source_map_checks.json").write_text(json.dumps(
        [{"case": "missing", "status": "complete"}, {"case": "malformed", "status": "partial"}]))


def test_empty_when_no_result(client):
    c, _ = client
    body = c.get("/api/reverse-analysis?domain=app.example.com").get_json()
    assert body["state"] == "empty"


def test_invalid_domain_is_error(client):
    c, _ = client
    r = c.get("/api/reverse-analysis?domain=../x")
    assert r.status_code == 400 and r.get_json()["state"] == "error"


def test_broken_json_is_error_not_crash(client):
    c, base = client
    _place(base, "{broken")
    assert c.get("/api/reverse-analysis?domain=app.example.com").get_json()["state"] == "error"


def test_states_are_not_upgraded(client):
    c, base = client
    _place(base, _doc())
    body = c.get("/api/reverse-analysis?domain=app.example.com").get_json()
    assert body["state"] == "ok" and body["status"] == "partial"
    ev = {e["id"]: e for e in body["evidence"]}
    # 静的 route は実測にしない・到達済みにしない
    assert ev["s1"]["state"] == "inferred" and ev["s1"]["origin"] == "static"
    assert "未確認" in ev["s1"]["claim"]
    # method 不明を GET で補完しない
    assert ev["s2"]["method"] is None and ev["s2"]["state"] == "static"
    # 実測だけが observed
    assert ev["r1"]["state"] == "observed" and ev["r1"]["origin"] == "runtime"
    assert [d["external"] for d in body["dependencies"]] == [True]
    # source map の成功を「正常」にしない
    sm = {s["case"]: s for s in body["source_map"]}
    assert sm["missing"]["outcome"] == "success" and "できない" in sm["missing"]["meaning"]
    assert sm["malformed"]["outcome"] == "partial"
    # 内部 ID を含む診断はまとめて出す
    assert all("jag_node" not in d["message"] for d in body["diagnostics"])


def test_summary_without_measurement_is_unmeasured(client):
    c, base = client
    _place(base, _doc())
    body = c.get("/api/reverse-analysis?domain=app.example.com").get_json()
    rows = {r["key"]: r for r in body["summary"]}
    assert body["added_seconds"] is None
    assert rows["qa"]["before"] is None and rows["qa"]["after"] is None
    assert rows["api_runtime"]["before"] == rows["api_runtime"]["after"] == 1


def test_summary_uses_real_measurement(client):
    c, base = client
    _place(base, _doc(), measurement=True)
    body = c.get("/api/reverse-analysis?domain=app.example.com").get_json()
    m = MEASUREMENT
    rows = {r["key"]: r for r in body["summary"]}
    assert rows["route"]["after"] == m["after"]["metrics"]["route_candidates"]
    assert rows["module_dep"]["after"] == m["after"]["metrics"]["module_dependency_edges"]
    assert rows["api_runtime"]["before"] == rows["api_runtime"]["after"]
    assert body["added_seconds"] == m["added_wall_seconds"]
