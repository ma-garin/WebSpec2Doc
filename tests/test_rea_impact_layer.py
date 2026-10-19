"""System 09 の REA 依存層（web/services/rea_impact_layer.py）。"""
from __future__ import annotations

import copy

from web.services import rea_impact_layer as L


def _dep(src, tgt, state="inferred", ext=False, loc=None):
    return {"source": src, "target": tgt, "relation_label": "依存", "state": state,
            "location": loc or f"{src}:1:1", "external": ext, "limitations": ["静的"]}  # fmt: skip


def _ev(deps, evidence=()):
    return {"state": "ok", "dependencies": list(deps), "evidence": list(evidence)}


def _route(i, f, group="route", origin="static", state="inferred"):
    return {"id": i, "group": group, "value": f"/{i}", "state": state, "origin": origin, "method": None,
            "location": f"{f}:3:4" if origin == "static" else "実行記録 https://x/"}  # fmt: skip


DEPS = [_dep("a.js", "./b.js"), _dep("b.js", "./c.js", state="ambiguous"), _dep("d.js", "./b.js", state="unknown"),
        _dep("b.js", "lodash", ext=True)]  # fmt: skip
EVID = [_route("r1", "b.js"), _route("r2", "d.js"), _route("api1", "c.js", group="api"),
        _route("rt", "x", group="api", origin="runtime", state="observed")]  # fmt: skip


def test_reverse_and_forward_bfs():
    r = L.build_layer("s", _ev(DEPS, EVID), "b.js")
    rev = {c["module"] for c in r["impacted"] if c["direction"] == "reverse"}
    fwd = {c["module"] for c in r["impacted"] if c["direction"] == "forward"}
    assert rev == {"a.js", "d.js"} and fwd == {"c.js"}
    assert r["layer"] == "code_static" and r["metrics"]["after"]["candidates"] == 3


def test_bfs_depth_transitive_reverse():
    r = L.build_layer("s", _ev(DEPS), "c.js")
    depth = {c["module"]: c["depth"] for c in r["impacted"]}
    assert depth == {"b.js": 1, "a.js": 2, "d.js": 2}


def test_state_is_passed_through_not_raised():
    r = L.build_layer("s", _ev(DEPS), "b.js")
    st = {(c["via"]["source"], c["via"]["target"]): c["via"]["state"] for c in r["impacted"]}
    assert st[("b.js", "c.js")] == "ambiguous" and st[("d.js", "b.js")] == "unknown" and st[("a.js", "b.js")] == "inferred"
    assert all(c["via"]["state"] not in ("observed", "static", "confirmed") for c in r["impacted"])


def test_static_not_labeled_runtime():
    r = L.build_layer("s", _ev(DEPS, EVID), "b.js")
    assert all(c["via"]["kind"] == "static_dependency" and c["note"] == L.NOTICE for c in r["impacted"])
    items = [i for c in r["impacted"] for i in c["routes"] + c["apis"]] + r["own"]["routes"]
    assert items and all(i["origin"] == "static" for i in items)
    assert "実行時の依存ではない" in L.NOTICE


def test_runtime_api_not_linked_and_routes_apis_attached():
    r = L.build_layer("s", _ev(DEPS, EVID), "b.js")
    assert [i["id"] for i in r["own"]["routes"]] == ["r1"]
    by = {c["module"]: c for c in r["impacted"]}
    assert [i["id"] for i in by["c.js"]["apis"]] == ["api1"] and [i["id"] for i in by["d.js"]["routes"]] == ["r2"]
    assert r["metrics"]["after"]["apis"] == 1 and r["metrics"]["after"]["routes"] == 2


def test_external_separated_from_candidates():
    r = L.build_layer("s", _ev(DEPS), "b.js")
    assert "lodash" not in {c["module"] for c in r["impacted"]}
    assert [e["raw_target"] for e in r["external"]] == ["lodash"]


def test_no_rea_is_zero_and_unconfirmed():
    for ev in ({"state": "empty", "message": "なし"}, {"state": "error"}, None):
        r = L.build_layer("s", ev, "b.js")
        assert r["state"] == "unconfirmed" and r["impacted"] == []
        assert r["metrics"]["after"] == {"dependency_edges": 0, "candidates": 0, "routes": 0, "apis": 0, "tests": 0,
                                         "observed_routes": 0, "observed_routes_authenticated": 0}
        assert r["message"]


def test_before_is_zero_with_reason_and_tests_from_system02():
    r = L.build_layer("s", _ev(DEPS, EVID), "")
    assert r["metrics"]["before"]["dependency_edges"] == 0 and r["metrics"]["before"]["reason"]
    assert r["metrics"]["after"]["dependency_edges"] == 4 and "System 02" in r["tests"]["note"]
    # 関連テストは System 02 の REA 由来観点（静的 route r1・r2 と静的 API api1）だけ。実測 API は数えない
    assert r["metrics"]["after"]["tests"] == 3
    assert r["sources"][0]["module"] == "b.js"


def test_impacted_module_carries_system02_viewpoints_as_static():
    r = L.build_layer("s", _ev(DEPS, EVID), "b.js")
    d = next(c for c in r["impacted"] if c["module"] == "d.js")
    assert [t["evidence_id"] for t in d["tests"]] == ["r2"]
    assert all(t["source"] == "static" for t in d["tests"])
    assert [t["evidence_id"] for t in r["own"]["tests"]] == ["r1"]


def test_input_not_mutated_and_existing_bfs_untouched():
    ev = _ev(DEPS, EVID)
    before = copy.deepcopy(ev)
    L.build_layer("s", ev, "b.js")
    assert ev == before
    from web.services.impact import analyze  # 既存の文書項目 BFS は置換していない
    assert hasattr(analyze, "__name__")


def test_unknown_module_and_normalization():
    assert L.build_layer("s", _ev(DEPS), "zzz.js")["state"] == "unknown_module"
    assert L.norm_module("./dir/chunk-A.js?x=1") == "chunk-A.js"
    assert L.loc_file("main.js:1:79") == "main.js" and L.loc_file("実行記録 https://x/") == ""


def test_observed_routes_in_after_metrics():
    probe = {"r1": {"status": "observed"}, "r2": {"status": "unreached"}}
    r = L.build_layer("s", _ev(DEPS, EVID), "b.js", probe)
    assert r["metrics"]["after"]["observed_routes"] == 1
    routes = {i["id"]: i for c in r["impacted"] for i in c["routes"]} | {i["id"]: i for i in r["own"]["routes"]}
    assert routes["r1"]["reach_status"] == "observed" and routes["r1"]["reach_label"] == "実測で到達（未認証）"
    assert routes["r2"]["reach_label"] == "未到達"
    assert r["notice"] == L.NOTICE


def test_no_probe_all_not_probed():
    for probe in (None, {}):
        r = L.build_layer("s", _ev(DEPS, EVID), "b.js", probe)
        assert r["metrics"]["after"]["observed_routes"] == 0
        assert {i["reach_label"] for c in r["impacted"] for i in c["routes"]} == {"未探索"}
    assert L.build_layer("s", _ev(DEPS, EVID))["metrics"]["after"]["observed_routes"] == 0


def test_authenticated_observed_label_and_metric():
    probe = {"r1": {"status": "observed", "authenticated": True}, "r2": {"status": "auth_required", "auth_attempted": True}}
    r = L.build_layer("s", _ev(DEPS, EVID), "b.js", probe)
    assert r["metrics"]["after"]["observed_routes"] == 1
    assert r["metrics"]["after"]["observed_routes_authenticated"] == 1
    routes = {i["id"]: i for c in r["impacted"] for i in c["routes"]} | {i["id"]: i for i in r["own"]["routes"]}
    assert routes["r1"]["reach_label"] == "実測で到達（認証済み）" and routes["r1"]["reach_authenticated"] is True
    assert routes["r2"]["reach_label"] == "保存済みの認証状態でも未確認"
    r0 = L.build_layer("s", _ev(DEPS, EVID), "b.js", None)
    assert r0["metrics"]["after"]["observed_routes_authenticated"] == 0
