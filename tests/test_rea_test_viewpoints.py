"""リバース解析の根拠 → System 02 テスト観点候補（web/services/rea_test_viewpoints.py）。"""

from web.services.rea_test_viewpoints import build_viewpoints


def _ev(i, group, origin, value, method=None, state="static", loc="a.js:1:2"):
    return {"id": i, "group": group, "kind_label": group, "value": value, "state": state, "origin": origin,
            "method": method, "location": loc, "claim": f"claim {i}", "limitations": ["lim"]}  # fmt: skip


def _ok(evidence, deps=()):
    return {"state": "ok", "evidence": list(evidence), "dependencies": list(deps)}


def test_static_route_is_not_reached():
    out = build_viewpoints(_ok([_ev("r1", "route", "static", "settings", state="inferred")]), before=10)
    (v,) = out["viewpoints"]
    assert "到達は未確認" in v["text"] and "到達済み" not in v["text"] and "実行済み" not in v["text"]
    assert v["source_label"] == "静的候補由来" and v["evidence_state"] == "inferred"
    assert out["metrics"] == {"before": 10, "after": 11, "new": 1, "with_evidence": 1,
                              "runnable": 0, "executed": None, "probed": 0, "before_basis": "既存のテスト候補数"}  # fmt: skip


def test_null_method_is_not_filled_with_get():
    out = build_viewpoints(_ok([_ev("a1", "api", "static", "/api/x", method=None)]), before=0)
    text = out["viewpoints"][0]["text"]
    assert "不明" in text and "GET" not in text


def test_explicit_method_kept():
    out = build_viewpoints(_ok([_ev("a1", "api", "static", "/api/x", method="post")]), before=0)
    assert "POST" in out["viewpoints"][0]["text"]


def test_runtime_api_not_counted_and_same_path_static_not_new():
    ev = [_ev("rt", "api", "runtime", "/api/users", method="GET", state="observed"),
          _ev("st", "api", "static", "https://h.example/api/users/?q=1", method=None),
          _ev("st2", "api", "static", "/api/orders")]  # fmt: skip
    out = build_viewpoints(_ok(ev), before=5)
    assert out["metrics"]["new"] == 1 and out["metrics"]["after"] == 6
    assert [c["evidence_id"] for c in out["covered_by_runtime"]] == ["st"]
    rt = [v for v in out["viewpoints"] if v["source"] == "runtime"]
    assert len(rt) == 1 and rt[0]["is_new"] is False and rt[0]["source_label"] == "実測由来"


def test_before_falls_back_to_runtime_count():
    ev = [_ev("rt", "api", "runtime", "/api/a", method="GET", state="observed"), _ev("r", "route", "static", "x")]
    out = build_viewpoints(_ok(ev), before=None)
    assert out["metrics"]["before"] == 1 and out["metrics"]["after"] == 2


def test_state_never_raised():
    ev = [_ev("a", "api", "static", "/api/u", state="unavailable"), _ev("b", "route", "static", "r", state="ambiguous")]
    states = {v["evidence_id"]: v["evidence_state"] for v in build_viewpoints(_ok(ev), 0)["viewpoints"]}
    assert states == {"a": "unavailable", "b": "ambiguous"}


def test_module_dependency_excludes_external_and_dedupes():
    deps = [{"source": "a.js", "target": "b.js", "relation_label": "静的 import", "state": "static", "location": "a.js:1:1", "external": False, "limitations": []},
            {"source": "a.js", "target": "b.js", "relation_label": "静的 import", "state": "static", "location": "a.js:2:1", "external": False, "limitations": []},
            {"source": "a.js", "target": "react", "relation_label": "静的 import", "state": "static", "location": "a.js:3:1", "external": True, "limitations": []}]  # fmt: skip
    out = build_viewpoints(_ok([], deps), before=0)
    assert len(out["viewpoints"]) == 1
    v = out["viewpoints"][0]
    assert "b.js" in v["text"] and "実行は未証明" in v["text"] and v["evidence_state"] == "static"


def test_no_rea_means_zero_and_unconfirmed():
    for rea in (None, {"state": "empty", "message": "まだありません"}, {"state": "mismatch"}, {"state": "error"}):
        out = build_viewpoints(rea, before=7)
        assert out["state"] == "no_evidence" and out["viewpoints"] == []
        assert out["metrics"]["new"] == 0 and out["metrics"]["after"] == 7
        assert "未確認" in out["message"] and "System01" in out["next_action"]


def test_only_ok_state_is_used():
    rea = {"state": "mismatch", "evidence": [_ev("r", "route", "static", "x")]}
    assert build_viewpoints(rea, 0)["viewpoints"] == []


def _probe(**by_id):
    return {k: {"evidence_id": k, "status": s, "reason": "r", "observed_at": "2026-10-20T00:00:00" if s == "observed" else None,
                "final_url": None} for k, s in by_id.items()}  # fmt: skip


_ROUTES = [_ev(f"r{i}", "route", "static", f"p{i}") for i in range(1, 7)]


def test_probe_none_keeps_legacy_and_marks_not_probed():
    out = build_viewpoints(_ok(_ROUTES[:1]), before=0)
    (v,) = out["viewpoints"]
    assert v["reach_status"] == "not_probed" and v["reach_label"] == "未探索" and v["runnable"] is False
    assert out["metrics"]["runnable"] == 0 and out["metrics"]["probed"] == 0
    assert out["metrics"]["new"] == 1 and out["metrics"]["after"] == 1


def test_only_observed_route_is_runnable():
    probe = _probe(r1="observed", r2="unreached", r3="auth_required", r4="ambiguous", r5="failed")
    out = build_viewpoints(_ok(_ROUTES), before=0, probe=probe)
    by = {v["evidence_id"]: v for v in out["viewpoints"]}
    assert [k for k, v in by.items() if v["runnable"]] == ["r1"]
    assert by["r1"]["source"] == "static" and by["r1"]["runnable_label"] == "実行対象（実測で到達）"
    assert by["r2"]["reach_label"] == "未到達" and by["r3"]["reach_label"] == "認証等で未確認"
    assert by["r6"]["reach_status"] == "not_probed"
    assert out["metrics"]["runnable"] == 1 and out["metrics"]["probed"] == 5


def test_empty_probe_all_not_probed():
    out = build_viewpoints(_ok(_ROUTES), before=0, probe={})
    assert {v["reach_status"] for v in out["viewpoints"]} == {"not_probed"}
    assert out["metrics"]["runnable"] == 0 and out["metrics"]["probed"] == 0


def _probe_auth(**by_id):
    return {k: {"evidence_id": k, "status": s, "authenticated": a, "auth_attempted": t, "reason": "r",
                "observed_at": "2026-10-20T00:00:00" if s == "observed" else None, "final_url": None}
            for k, (s, a, t) in by_id.items()}  # fmt: skip


def test_authenticated_splits_reach_label():
    probe = _probe_auth(r1=("observed", True, True), r2=("observed", False, False), r3=("auth_required", False, True),
                        r4=("auth_required", False, False))
    out = build_viewpoints(_ok(_ROUTES[:5]), before=0, probe=probe)
    by = {v["evidence_id"]: v for v in out["viewpoints"]}
    assert by["r1"]["reach_label"] == "実測で到達（認証済み）" and by["r1"]["reach_authenticated"] is True
    assert by["r1"]["text"].endswith("（System 03 が GET の遷移で到達を確認済み）（認証状態を使用）")
    assert by["r2"]["reach_label"] == "実測で到達（未認証）" and by["r2"]["reach_authenticated"] is False
    assert by["r2"]["text"].endswith("確認済み）")
    assert by["r1"]["runnable"] and by["r2"]["runnable"]


def test_auth_attempted_auth_required_is_not_runnable():
    out = build_viewpoints(_ok(_ROUTES[:2]), before=0, probe=_probe_auth(r1=("auth_required", False, True)))
    by = {v["evidence_id"]: v for v in out["viewpoints"]}
    assert by["r1"]["reach_label"] == "保存済みの認証状態でも未確認" and by["r1"]["runnable"] is False
    assert by["r1"]["reach_authenticated"] is False
    assert by["r2"]["reach_label"] == "未探索" and by["r2"]["reach_authenticated"] is False


# ---- 実行対象 ≠ 実行済み / 区分の語彙（C_CONTRACT と一致）----
def _obs(*ids, auth=False):
    return {i: {"status": "observed", "authenticated": auth, "observed_at": "2026-10-20"} for i in ids}


def _routes():
    return _ok([_ev("r1", "route", "static", "a", state="static"), _ev("r2", "route", "static", "b", state="static"),
                _ev("r3", "route", "static", "c", state="inferred"), _ev("r4", "route", "static", "d", state="unverified")])  # fmt: skip


def test_no_test_data_means_executed_is_null_not_zero():
    out = build_viewpoints(_routes(), 0, _obs("r1", "r2"), tests=None)
    assert out["metrics"]["runnable"] == 2 and out["metrics"]["executed"] is None
    assert all(v["execution"]["measured"] is False and v["execution"]["count"] is None for v in out["viewpoints"])


def test_runnable_is_not_executed_without_run_record():
    tests = [{"id": "T1", "status": "new", "last": {}}, {"id": "T2", "status": "pass", "last": {"run_id": "x"}}]  # リンク無し
    out = build_viewpoints(_routes(), 0, _obs("r1", "r2"), tests=tests)
    assert out["metrics"]["runnable"] == 2 and out["metrics"]["executed"] == 0
    r1 = next(v for v in out["viewpoints"] if v["evidence_id"] == "r1")
    assert r1["execution"]["target"] is True and r1["execution"]["label"] == "未実行"


def test_executed_only_when_test_linked_and_ran():
    tests = [{"id": "T1", "evidence_id": "r1", "status": "pass", "last": {"run_id": "a", "at": "2026-10-20T01:00"}},
             {"id": "T2", "evidence_id": "r1", "status": "fail", "last": {"run_id": "b", "at": "2026-10-20T02:00"}},
             {"id": "T3", "evidence_id": "r2", "status": "new", "last": {}}]  # fmt: skip
    out = build_viewpoints(_routes(), 0, _obs("r1", "r2"), tests=tests)
    by = {v["evidence_id"]: v for v in out["viewpoints"]}
    assert out["metrics"]["executed"] == 1 and out["metrics"]["runnable"] == 2
    assert by["r1"]["execution"]["count"] == 2 and by["r1"]["execution"]["last_result"] == "fail"
    assert by["r2"]["execution"]["count"] == 0


def test_origin_vocabulary_matches_contract():
    ev = [*_routes()["evidence"], _ev("rt", "api", "runtime", "/api/z", method="GET", state="observed")]
    out = build_viewpoints(_ok(ev), 3, _obs("r1", auth=True), tests=[])
    by = {v["evidence_id"]: v for v in out["viewpoints"]}
    assert by["r1"]["origin_label"] == "認証済み実測" and by["r1"]["ev_code"] == "observed_auth"
    assert by["r2"]["origin_label"] == "静的" and by["r2"]["ev_code"] == "static"
    assert by["r3"]["origin_label"] == "REA 追加" and by["r3"]["ev_code"] == "inferred"
    assert by["r4"]["origin_label"] == "未確認" and by["r4"]["ev_code"] == "unverified"
    assert by["rt"]["origin_label"] == "元候補"
    probe_noauth = build_viewpoints(_routes(), 0, _obs("r1"), tests=[])["viewpoints"][0]
    assert probe_noauth["origin_label"] == "未認証実測" and probe_noauth["ev_code"] == "observed"
    assert {v["origin_label"] for v in out["viewpoints"]} <= {"元候補", "REA 追加", "静的", "未認証実測", "認証済み実測", "未確認"}
