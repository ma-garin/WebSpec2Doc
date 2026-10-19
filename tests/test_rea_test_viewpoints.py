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
                              "before_basis": "既存のテスト候補数"}  # fmt: skip


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
