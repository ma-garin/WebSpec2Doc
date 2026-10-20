"""B3 contract: executor は Node 系を起動しない／TS の 3 区分／BLOCKED の伝搬。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from web.services import playwright_executor as pe
from web.services.testcase_spec_generator import generate_spec
from web.services.ts_export import merge_meta, ts_export_status

_FORBIDDEN = ("npx", "npm", "node")


def _spec(tmp_path: Path) -> Path:
    spec = tmp_path / "x_spec.py"
    spec.write_text('@case("a")\ndef c(page):\n    pass\n', encoding="utf-8")
    return spec


def test_executor_never_spawns_node_tools(tmp_path, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, *a, **kw):
        calls.append(list(cmd))
        (tmp_path / "out" / "playwright_raw.json").write_text(
            json.dumps({"suites": [], "stats": {"expected": 1, "unexpected": 0, "skipped": 0, "duration": 5}}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("shutil.which", lambda name, *a, **k: (_ for _ in ()).throw(AssertionError("which")))
    pe.run_playwright(_spec(tmp_path), tmp_path / "out")
    assert calls, "runner not spawned"
    for cmd in calls:
        assert not any(Path(part).name in _FORBIDDEN for part in cmd)
        assert cmd[1:3] == ["-m", "web.services.pw_runner"]
    src = Path(pe.__file__).read_text(encoding="utf-8")
    for word in _FORBIDDEN:
        assert word not in src.replace("node_modules", "")


def test_ts_spec_is_refused_not_executed(tmp_path):
    ts = tmp_path / "a.spec.ts"
    ts.write_text("test('x', async () => {});", encoding="utf-8")
    res = pe.run_playwright(ts, tmp_path / "out")
    assert res["ok"] is False and "エクスポート専用" in res["error"]


def test_blocked_is_propagated_not_success(tmp_path, monkeypatch):
    def fake_run(cmd, *a, **kw):
        (tmp_path / "out" / "playwright_raw.json").write_text(
            json.dumps({"status": "BLOCKED", "reason": "browser unavailable", "tried": ["x"]}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 3, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    res = pe.run_playwright(_spec(tmp_path), tmp_path / "out")
    assert res["ok"] is False and res["blocked"] is True and res["unavailable"] is True
    assert "browser unavailable" in res["error"] and "Chrome" in res["error"]
    assert "npm" not in res["error"] and "npx" not in res["error"]
    assert res["passed"] == 0 and res["failed"] == 0


def test_ts_export_three_states_in_meta_and_status(tmp_path):
    meta = tmp_path / "autorun.meta.json"
    meta.write_text(json.dumps({"tests": [{"test_title": "t"}]}), encoding="utf-8")
    merged = merge_meta(meta, {"tests": [], "ts_export": {"generated": True, "executed": False, "verified": False}})
    assert merged["tests"] == [{"test_title": "t"}]  # py 側の meta を上書きしない
    assert merged["ts_export"] == {"generated": True, "executed": False, "verified": False}
    status = ts_export_status(merged, True)
    assert status["labels"] == ["生成済み", "未実行", "未検証"] and status["legacy"] is False
    legacy = ts_export_status(None, True)
    assert legacy["legacy"] is True and "旧形式" in legacy["note"]


def test_testcase_generation_runs_py_and_exports_ts(tmp_path):
    row = {
        "case_id": "TC1", "name": "n", "automation": "自動化可",
        "actions": [{"type": "goto", "url": "http://e.test/"}],
        "assertions": [{"type": "expect_no_server_error"}],
    }
    gen = generate_spec([row], tmp_path)
    assert gen["spec_path"].endswith("testcases_spec.py") and gen["ts_path"].endswith("testcases.spec.ts")
    import ast

    ast.parse(Path(gen["spec_path"]).read_text(encoding="utf-8"))
    assert "not executed" in Path(gen["ts_path"]).read_text(encoding="utf-8")
    meta = json.loads(Path(gen["ts_meta_path"]).read_text(encoding="utf-8"))
    assert meta["ts_export"]["executed"] is False and meta["ts_export"]["verified"] is False
