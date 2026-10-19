"""リバース解析の画面 API（表示 GET・実行 POST）。

- 結果は run.json（対象サイト・snapshot digest）と一致するときだけ表示する
- 状態を取り違えない（静的 route を到達済みにしない・method 不明を GET にしない 等）
- 実行は CLI と同じ service を通す（実 REA が導入済みの環境だけ実行系を通しで確かめる）
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import threading
from pathlib import Path

import pytest
from web.services import reverse_analysis_run as runner

ROOT = Path(__file__).resolve().parents[1]
REAL_PROVIDER_STATUS = runner.provider_status
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
    monkeypatch.setattr(
        runner, "provider_status", lambda: runner.ProviderStatus(True, "6.7.0", None, None)
    )
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
        "producer": {"provider_version": "6.7.0"},
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


def test_provider_unavailable_blocks_run_but_keeps_result(client, monkeypatch):
    c, base = client
    sha = _snapshot(base)
    _place(base, _doc(sha), _run(sha))
    monkeypatch.setattr(
        runner, "provider_status",
        lambda: runner.ProviderStatus(False, None, "静的解析ツール（REA）が導入されていません。", "依頼"),
    )  # fmt: skip
    body = _get(c)
    assert body["state"] == "ok" and body["can_run"] is False
    assert body["provider_status"]["available"] is False
    r = c.post(f"/api/sites/{DOMAIN}/reverse-analysis/run", headers=ORIGIN)
    assert r.status_code == 422 and r.get_json()["result"] == "provider_unavailable"


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
    not Path(runner.rea_command()).is_file() or importlib.util.find_spec("reverse_analysis") is None,
    reason="実 REA 6.7.0 またはリバース解析機能が導入されていない環境",
)
def test_run_end_to_end_with_real_rea(client, monkeypatch):
    """実 REA で service を通しで実行し、結果がこのサイトに結び付くこと。"""
    c, base = client
    monkeypatch.setattr(runner, "provider_status", REAL_PROVIDER_STATUS)
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
    assert all(e["method"] is None for e in body["evidence"] if e["origin"] == "static")


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
