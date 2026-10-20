from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import browser_detect as bd
from web.services import pw_runner as r


def _args(tmp_path: Path, spec: Path, **kw):
    argv = ["--spec", str(spec), "--out", str(tmp_path / "out")]
    for k, v in kw.items():
        argv += [f"--{k}", str(v)]
    return r.parse_args(argv)


SPEC = """
def _mk(label, skip=False):
    def deco(fn):
        fn.__pw_case__ = {"label": label, "skip": skip}
        return fn
    return deco

@_mk("ok")
def a(page): pass

@_mk("skipme", skip=True)
def b(page): pass
"""


def test_blocked_when_no_browser(tmp_path, monkeypatch):
    spec = tmp_path / "x_spec.py"
    spec.write_text(SPEC, encoding="utf-8")

    def none(*a, **k):
        raise bd.BrowserUnavailable("none", ["/a"])

    monkeypatch.setattr(bd, "detect_browser", none)
    code = r.run(_args(tmp_path, spec))
    raw = json.loads((tmp_path / "out" / "playwright_raw.json").read_text())
    assert code == r.EXIT_BLOCKED == 3
    assert (raw["status"], raw["reason"], raw["ok"]) == ("BLOCKED", "browser unavailable", False)
    assert raw["passed"] == raw["failed"] == 0


def test_raw_json_shape_matches_playwright_reporter():
    results = [
        {"title": "ok", "status": "passed", "duration": 5, "error": "", "failed_step": ""},
        {"title": "ng", "status": "failed", "duration": 7, "error": "boom", "failed_step": "S2"},
        {"title": "sk", "status": "skipped", "duration": 0, "error": "", "failed_step": ""},
    ]
    raw = r.build_raw("x_spec.py", results, 12, status="FAILED", ok=False)
    specs = raw["suites"][0]["specs"]
    assert [s["tests"][0]["status"] for s in specs] == ["expected", "unexpected", "skipped"]
    assert specs[1]["tests"][0]["results"][0]["errors"][0]["message"] == "boom"
    assert specs[1]["tests"][0]["results"][0]["steps"][0] == {
        "title": "S2",
        "error": {"message": "boom"},
    }
    assert raw["stats"] == {"duration": 12, "expected": 1, "unexpected": 1, "skipped": 1, "flaky": 0}
    # 既存パーサが読める
    from web.services.playwright_executor import _parse_results

    parsed = _parse_results(raw, "", "", 1)
    assert (parsed["passed"], parsed["failed"], parsed["skipped"]) == (1, 1, 1)
    assert parsed["tests"][1]["failed_step"] == "S2"


def test_load_cases_and_progress_independent_of_browser(tmp_path):
    spec = tmp_path / "x_spec.py"
    spec.write_text(SPEC, encoding="utf-8")
    cases = r.load_cases(spec)
    assert [(c.label, c.skip) for c in cases] == [("ok", False), ("skipme", True)]


def test_egress_denies_private_and_logs(tmp_path):
    log = tmp_path / "e.ndjson"
    eg = r.Egress({"budgetPerWorker": 1}, log)
    assert eg.deny_reason("http://localhost:8765/") == "private_address"
    assert eg.deny_reason("http://169.254.169.254/") == "private_address"
    assert eg.deny_reason("ftp://example.com/") == "scheme"
    assert eg.deny_reason("https://example.com/") is None
    assert r.Egress({"allowLocal": True}, log).deny_reason("http://127.0.0.1/") is None
    assert r.Egress({"blockAll": True}, log).deny_reason("https://example.com/") == "block_all"

    class Req:
        url = "http://localhost/x"

    class Route:
        request = Req()
        aborted = False

        def abort(self):
            self.aborted = True

    route = Route()
    eg.handler("t1")(route)
    entry = json.loads(log.read_text().splitlines()[0])
    assert route.aborted and entry["action"] == "denied" and entry["reason"] == "private_address"


def test_egress_budget(tmp_path):
    eg = r.Egress({"budgetPerWorker": 1}, tmp_path / "e.ndjson")

    class Route:
        def __init__(self, url):
            self.request = type("R", (), {"url": url})()
            self.out = None

        def abort(self):
            self.out = "abort"

        def continue_(self):
            self.out = "continue"

    h = eg.handler("t")
    a, b = Route("https://example.com/a"), Route("https://example.com/b")
    h(a), h(b)
    assert (a.out, b.out) == ("continue", "abort")
    assert "budget" in (tmp_path / "e.ndjson").read_text()
