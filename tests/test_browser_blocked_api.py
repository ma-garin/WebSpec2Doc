"""ブラウザ不在（BrowserUnavailable）の子プロセス出力を BLOCKED として返す契約。"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

from web.services.browser_blocked import (
    BLOCKED_MESSAGE,
    blocked_payload,
    is_browser_unavailable,
)

TRACE = (
    "Traceback (most recent call last):\n"
    "browser_detect.BrowserUnavailable: browser unavailable: Google Chrome または Microsoft Edge が見つかりません\n"
)


def test_marker_detection():
    assert is_browser_unavailable("", TRACE)
    assert not is_browser_unavailable("ValueError: x", None)


def test_payload_is_blocked_not_success():
    p = blocked_payload(pages=[])
    assert p["status"] == "BLOCKED" and p["ok"] is False and p["success"] is False
    assert "Chrome" in p["error"] and "Edge" in p["error"]


def test_discover_api_returns_blocked(monkeypatch):
    from web.routes import discover

    monkeypatch.setattr(
        discover.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr=TRACE),
    )
    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(discover.bp)
    res = app.test_client().post("/api/discover", data={"url": "https://example.com"})
    assert res.status_code == 503
    assert res.get_json()["status"] == "BLOCKED"


def test_record_stage_reports_blocked(monkeypatch):
    from web.routes import record

    monkeypatch.setattr(
        record.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout="", stderr=TRACE),
    )
    ok, detail = record._run_stage(["x"])
    assert ok is False and detail == BLOCKED_MESSAGE
