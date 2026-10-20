"""リバース解析の画面 API（表示 GET・実行 POST）。

- 結果は run.json（対象サイト・snapshot digest）と一致するときだけ表示する
- 状態を取り違えない（静的 route を到達済みにしない・method 不明を GET にしない 等）
- 実行は CLI と同じ service を通す（）
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import threading
from pathlib import Path

import pytest
from web.services import reverse_analysis_run as runner

ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "app.example.com"
ORIGIN = {"Origin": "http://localhost"}
SNAPSHOT = [
    {"url": f"https://{DOMAIN}/items", "api_calls": [
        {"method": "GET", "path": "/api/items", "status_code": 200, "content_type": "application/json"},
    ]},
]  # fmt: skip


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBSPEC2DOC_AUTH_MODE", "off")
    import web.routes.reverse_analysis as mod

    monkeypatch.setattr(mod, "scoped_output_dir", lambda _base: tmp_path)
    from web import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client(), tmp_path


def _snapshot(base: Path, name: str = "20261019-000000.json") -> str:
    snaps = base / DOMAIN / "snapshots"
    snaps.mkdir(parents=True, exist_ok=True)
    path = snaps / name
    path.write_text(json.dumps(SNAPSHOT))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _doc(sha: str, status: str = "complete") -> dict:
    return {
        "status": status,
        "producer": {"engine_version": "webspec2doc-native/1"},
        "inputs": {"runtime_snapshot_sha256": sha},
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
             "page_url": f"https://{DOMAIN}/items", "epistemic_state": "observed"},
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
    }  # fmt: skip


def _place(base: Path, doc: dict | str, run: dict | None) -> None:
    root = base / DOMAIN / "reverse_analysis"
    (root / "result").mkdir(parents=True)
    (root / "result" / "reverse_analysis.json").write_text(
        doc if isinstance(doc, str) else json.dumps(doc)
    )
    if run is not None:
        (root / "run.json").write_text(json.dumps(run))


def _run(sha: str, domain: str = DOMAIN, snapshot: str = "20261019-000000.json") -> dict:
    return {
        "domain": domain, "snapshot": snapshot, "snapshot_sha256": sha, "seconds": 4.8,
        "status": "complete", "repetitions": 1, "js_files": 2, "source_maps": 0,
        "finished_at": "2026-10-19T23:00:00+09:00",
        "before": {"static_candidates": 0, "route_candidates": 0, "runtime_observations": 1},
        "after": {"static_candidates": 2, "route_candidates": 1, "runtime_observations": 1},
    }  # fmt: skip


def _get(c) -> dict:
    return c.get(f"/api/reverse-analysis?domain={DOMAIN}").get_json()


# ------------------------------------------------------------------ 表示


def test_empty_when_no_result_and_can_run(client):
    c, base = client
    _snapshot(base)
    body = _get(c)
    assert body["state"] == "empty" and body["can_run"] is True
    assert body["site"]["domain"] == DOMAIN and body["last_run"] is None


def test_cannot_run_without_runtime_record(client):
    c, _ = client
    body = _get(c)
    assert body["can_run"] is False and "実行時記録" in body["cannot_run_reason"]


def test_invalid_domain_is_error(client):
    c, _ = client
    r = c.get("/api/reverse-analysis?domain=../x")
    assert r.status_code == 400 and r.get_json()["state"] == "error"


def test_broken_json_is_error_not_crash(client):
    c, base = client
    _place(base, "{broken", None)
    assert _get(c)["state"] == "error"


@pytest.mark.parametrize("which", ["no_run", "other_domain", "other_snapshot"])
def test_result_of_other_target_is_not_shown(client, which):
    c, base = client
    sha = _snapshot(base)
    run = {"no_run": None, "other_domain": _run(sha, domain="other.example.com"),
           "other_snapshot": _run("0" * 64)}[which]  # fmt: skip
    _place(base, _doc(sha), run)
    body = _get(c)
    assert body["state"] == "mismatch" and "evidence" not in body


def test_states_are_not_upgraded(client):
    c, base = client
    sha = _snapshot(base)
    _place(base, _doc(sha, status="partial"), _run(sha))
    body = _get(c)
    assert body["state"] == "ok" and body["status"] == "partial"
    ev = {e["id"]: e for e in body["evidence"]}
    assert ev["s1"]["state"] == "inferred" and ev["s1"]["origin"] == "static"
    assert "未確認" in ev["s1"]["claim"]
    assert ev["s2"]["method"] is None and ev["s2"]["state"] == "static"
    assert ev["r1"]["state"] == "observed" and ev["r1"]["origin"] == "runtime"
    assert all("jag_node" not in d["message"] for d in body["diagnostics"])
    sm = body["source_map"][0]
    assert sm["label"] == "source map なし" and "できない" in sm["meaning"]


def test_summary_from_run_record_and_qa_unmeasured(client):
    c, base = client
    sha = _snapshot(base)
    _place(base, _doc(sha), _run(sha))
    body = _get(c)
    rows = {r["key"]: r for r in body["summary"]}
    assert rows["route"]["before"] == 0 and rows["route"]["after"] == 1
    assert rows["api_runtime"]["before"] == rows["api_runtime"]["after"] == 1
    assert rows["qa"]["before"] is None and rows["qa"]["after"] is None
    assert body["added_seconds"] == 4.8 and body["last_run"]["status"] == "complete"


def test_newer_snapshot_is_warned(client):
    c, base = client
    sha = _snapshot(base)
    _place(base, _doc(sha), _run(sha))
    _snapshot(base, "20261020-000000.json")
    body = _get(c)
    assert body["state"] == "ok" and "前の実行時記録" in body["diagnostics"][0]["message"]


def test_no_provider_path_and_no_rea_text_in_api(client):
    """未導入で失敗する経路が無い。API 応答（結果・run 可否）に REA の文字列が出ない。"""
    c, base = client
    sha = _snapshot(base)
    _place(base, _doc(sha), _run(sha))
    body = _get(c)
    assert body["state"] == "ok" and body["can_run"] is True
    assert "provider_status" not in body
    assert not hasattr(runner, "provider_status") and not hasattr(runner, "rea_command")
    assert not re.search(r"\bREA\b", json.dumps(body, ensure_ascii=False))


def test_legacy_run_json_provider_version_is_readable(client):
    """旧形式 run.json（provider_version のみ）と旧 producer でも mismatch にならず version が出る。"""
    c, base = client
    sha = _snapshot(base)
    doc = _doc(sha)
    doc["producer"] = {"provider_version": "6.7.0"}
    run = _run(sha)
    run.pop("engine_version", None)
    run["provider_version"] = "6.7.0"
    _place(base, doc, run)
    body = _get(c)
    assert body["state"] == "ok" and body["engine_version"] == "6.7.0"
    assert not re.search(r"\bREA\b", json.dumps(body, ensure_ascii=False))


# ------------------------------------------------------------------ 実行


def test_run_without_runtime_record(client):
    c, base = client
    (base / DOMAIN).mkdir()
    r = c.post(f"/api/sites/{DOMAIN}/reverse-analysis/run", headers=ORIGIN)
    assert r.status_code == 422 and r.get_json()["result"] == "no_runtime"


def test_run_unknown_site_is_404(client):
    c, _ = client
    r = c.post("/api/sites/nope.example.com/reverse-analysis/run", headers=ORIGIN)
    assert r.status_code == 404


def test_double_run_is_rejected(client, monkeypatch):
    c, base = client
    _snapshot(base)
    gate, entered = threading.Event(), threading.Event()

    def slow(_base, _domain):
        entered.set()
        gate.wait(5)
        return runner.RunResult("success", "ok", "ok")

    monkeypatch.setattr(runner, "_run", slow)
    first = threading.Thread(target=lambda: runner.run_for_site(base, DOMAIN))
    first.start()
    entered.wait(5)
    try:
        assert _get(c)["running"] is True and _get(c)["can_run"] is False
        r = c.post(f"/api/sites/{DOMAIN}/reverse-analysis/run", headers=ORIGIN)
        assert r.status_code == 409 and r.get_json()["result"] == "busy"
    finally:
        gate.set()
        first.join(5)
    assert runner.is_running(DOMAIN) is False


def test_no_js_is_error_and_keeps_previous_result(client, monkeypatch):
    c, base = client
    sha = _snapshot(base)
    _place(base, _doc(sha), _run(sha))
    monkeypatch.setattr(runner, "capture_scripts", lambda pages, domain, dest: (0, 0))
    r = c.post(f"/api/sites/{DOMAIN}/reverse-analysis/run", headers=ORIGIN)
    assert r.status_code == 500 and r.get_json()["result"] == "error"
    assert _get(c)["state"] == "ok"  # 前回の結果は残る


def test_capture_only_same_site(tmp_path, monkeypatch):
    served = {
        f"https://{DOMAIN}/items": b'<script src="/a.js"></script><script src="https://cdn.other.com/x.js"></script>',
        f"https://{DOMAIN}/a.js": b"fetch('/api/x')\n//# sourceMappingURL=a.js.map",
        f"https://{DOMAIN}/a.js.map": b"{}",
    }  # fmt: skip
    fetched: list[str] = []

    def fake_fetch(url, limit):
        fetched.append(url)
        return served.get(url)

    monkeypatch.setattr(runner, "_fetch", fake_fetch)
    scripts, maps = runner.capture_scripts(
        [f"https://{DOMAIN}/items", "https://evil.example.com/"], DOMAIN, tmp_path
    )
    assert (scripts, maps) == (1, 1)
    assert not any("other.com" in u or "evil" in u for u in fetched)
    assert (tmp_path / "a.js").is_file() and (tmp_path / "a.js.map").is_file()


@pytest.mark.skipif(
    importlib.util.find_spec("reverse_analysis.native") is None,
    reason="リバース解析の組立モジュールがこの環境に無い",
)
def test_run_end_to_end_native(client, monkeypatch):
    """service を通しで実行し、結果がこのサイトに結び付くこと（外部プロセスなし）。"""
    c, base = client
    _snapshot(base)
    fixture = ROOT / "tests/fixtures/reverse_analysis/real/app"
    monkeypatch.setattr(
        runner, "capture_scripts",
        lambda pages, domain, dest: (shutil.copytree(fixture, dest, dirs_exist_ok=True), (9, 1))[1],
    )  # fmt: skip
    r = c.post(f"/api/sites/{DOMAIN}/reverse-analysis/run", headers=ORIGIN)
    assert r.get_json()["result"] in ("success", "partial"), r.get_json()
    body = _get(c)
    assert body["state"] == "ok" and body["last_run"]["js_files"] == 9
    rows = {r["key"]: r for r in body["summary"]}
    assert rows["static"]["after"] > 0 and rows["static"]["before"] == 0
    assert rows["api_runtime"]["before"] == rows["api_runtime"]["after"] == 1
    # Native は HTTP method を静的に解決する（REA 6.7.0 は返さなかった）。少なくとも 1 件は具体的な method を持ち、値は既知の集合に限る
    static_methods = [e["method"] for e in body["evidence"] if e["origin"] == "static"]
    assert any(m in {"GET", "POST", "PUT", "PATCH", "DELETE"} for m in static_methods), static_methods
    assert all(m in {None, "UNKNOWN", "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"} for m in static_methods), static_methods


# ------------------------------------------------------------------ C. Hybrid 統合（静的な契約）


def test_gui_uses_ws2d_parts_and_keeps_product_truth():
    """REA タブは WS2D の部品で描き、既存ドロワーを持たず、実測 API を増分に数えない。"""
    js = (ROOT / "static/js/ta2/ws-reverse.js").read_text(encoding="utf-8")
    for part in ("W.status.html", "W.evidence.html", "W.kpis(", "W.state(", "W.reason(", "W.drawer.open("):
        assert part in js, part
    assert "rv-drawer" not in js
    assert "変化なし・増分に数えない" in js
    for label in ("未認証実測", "observed_auth", "未確認"):
        assert label in js, label
    assert "/static-routes/probe" in js


# ------------------------------------------------------------------ route の取得不可・provider の一時失敗


def test_route_not_provided_is_unavailable_not_zero(client):
    """route 宣言を取得できなかったときは「取得不可」。0 件と区別できる印を画面へ渡す。"""
    c, base = client
    sha = _snapshot(base)
    run = _run(sha)
    run["after"] = {"static_candidates": 2, "route_candidates": None, "runtime_observations": 1}
    doc = _doc(sha)
    doc["coverage"] = {"static": {"limitations": ["provider_route_nodes_not_provided"]}}
    _place(base, doc, run)
    body = _get(c)
    route = {r["key"]: r for r in body["summary"]}["route"]
    assert route["unavailable"] is True and route["after"] is None
    assert "0 件という意味ではない" in route["note"]
    assert "provider_route_nodes_not_provided" not in body["coverage_limitations"]
    assert any("route を取得できない" in x for x in body["coverage_limitations"])


def test_route_measured_is_not_unavailable(client):
    c, base = client
    sha = _snapshot(base)
    _place(base, _doc(sha), _run(sha))
    route = {r["key"]: r for r in _get(c)["summary"]}["route"]
    assert route["unavailable"] is False and route["after"] == 1


def test_gui_route_unavailable_wording():
    """route 取得不可を 0 と出さない／解析ツール利用不可で前回結果を「現在の成功」に見せない。"""
    js = (ROOT / "static/js/ta2/ws-reverse.js").read_text(encoding="utf-8")
    assert "取得不可" in js and "0 件という意味ではありません" in js
    assert not re.search(r"\bREA\b", js) and "provider_status" not in js
    assert "到達は System 03 で実測" in js  # 実測済み route に「到達は未確認」と書かない
    assert "いまは実行できません" in js  # 実行できないのに「実行を押す」と案内しない
    spec = (ROOT / "static/js/ta2/ws-spec.js").read_text(encoding="utf-8")
    assert "aria-pressed" in spec and "get('view')" in spec  # ?view=reverse で直接開ける


def test_native_evidence_survives_system01_03_02_09(tmp_path, monkeypatch):
    """Native 保存JSONの同一ID・位置・到達状態を最終影響出力まで運ぶ。"""
    import contextlib
    from reverse_analysis.service import ReverseAnalysisRequest, run_reverse_analysis
    from web.routes import reverse_analysis as view
    from web.services import static_route_probe as probe, static_route_probe_store as store
    from web.services.rea_test_viewpoints import build_viewpoints
    from web.services.rea_impact_layer import build_layer

    base = tmp_path.resolve()
    snap_sha = _snapshot(base)
    snap = runner.latest_snapshot(base, DOMAIN)
    root = runner.site_dir(base, DOMAIN)
    request = ReverseAnalysisRequest(
        str(ROOT / "tests/fixtures/reverse_analysis/real/app"), str(snap),
        str(root / runner.RESULT_DIR), True,
    )
    outcome = run_reverse_analysis(request)
    assert outcome.status == "complete" and outcome.output_path is not None
    (root / runner.RUN_FILE).write_text(json.dumps({
        "domain": DOMAIN, "snapshot_sha256": snap_sha, "snapshot": snap.name,
    }))
    monkeypatch.setattr(view, "_base", lambda: base)
    evidence = view.site_evidence(DOMAIN)
    assert evidence["state"] == "ok"
    edges = evidence["dependencies"]
    edge = next(e for e in edges if e["source"] == "routes/app.js" and e["target"] == "routes/lib.js")
    assert edge["location"] == "routes/app.js:1:1" and edge["state"] == "static"
    assert next(e for e in edges if e["target"] == "react-router-dom")["external"] is True

    class Navigator:
        def goto(self, url):
            return probe.NavResult(200, url)
        def states(self):
            return 2

    @contextlib.contextmanager
    def opener():
        yield Navigator()

    monkeypatch.setattr(probe, "_is_safe_target", lambda url: True)
    assert probe.run_probe(base, DOMAIN, evidence, opener).result == "success"
    reached = store.by_evidence(store.load(base, DOMAIN))
    system02 = build_viewpoints(evidence, 0, reached)
    route = next(e for e in evidence["evidence"] if e["group"] == "route" and e["value"] == "/settings")
    candidate = next(v for v in system02["viewpoints"] if v["evidence_id"] == route["id"])
    assert candidate["evidence_state"] == "inferred" and candidate["reach_status"] == "observed"
    assert candidate["runnable"] is True and "正しさは未確認" in candidate["claim"]
    assert system02["metrics"]["executed"] is None
    system09 = build_layer(DOMAIN, evidence, "routes/app.js", reached)
    rows = system09["own"]["routes"]
    propagated = next(r for r in rows if r["id"] == route["id"])
    assert propagated["state"] == "inferred" and propagated["reach_status"] == "observed"
    assert propagated["location"] == route["location"]
    assert any(t["evidence_id"] == route["id"] for t in system09["own"]["tests"])
    assert system09["metrics"]["after"]["tests"] > 0
