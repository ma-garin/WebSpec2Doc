from __future__ import annotations

import subprocess

import pytest

import browser_detect as bd

TABLES = {
    "darwin": {"chrome": ("/mac/chrome",), "msedge": ("/mac/edge",)},
    "windows": {
        "chrome": ("%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe",),
        "msedge": ("%ProgramFiles%\\Microsoft\\Edge\\Application\\msedge.exe",),
    },
    "linux": {"chrome": ("google-chrome",), "msedge": ("microsoft-edge",)},
}


def _no_subprocess(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("subprocess 禁止")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(subprocess, "Popen", boom)


def test_none_installed_raises_blocked_with_tried(monkeypatch):
    _no_subprocess(monkeypatch)
    with pytest.raises(bd.BrowserUnavailable) as ei:
        bd.detect_browser(system="darwin", env={}, tables=TABLES, exists=lambda p: False)
    assert ei.value.reason == "browser unavailable"
    assert ei.value.tried == ["/mac/chrome", "/mac/edge"]


def test_chrome_preferred_and_env_override():
    kw = dict(system="darwin", tables=TABLES, exists=lambda p: True)
    assert bd.detect_browser(env={}, **kw).channel == "chrome"
    c = bd.detect_browser(env={"WEBSPEC2DOC_BROWSER": "msedge"}, **kw)
    assert (c.channel, c.source, c.path) == ("msedge", "env", "/mac/edge")


def test_edge_only():
    c = bd.detect_browser(system="darwin", env={}, tables=TABLES, exists=lambda p: p == "/mac/edge")
    assert c.channel == "msedge"


def test_windows_expands_env_and_linux_uses_which(monkeypatch):
    _no_subprocess(monkeypatch)
    seen = []
    c = bd.detect_browser(
        system="win32",
        env={"ProgramFiles": "C:\\PF"},
        tables=TABLES,
        exists=lambda p: seen.append(p) or p.startswith("C:\\PF\\Microsoft"),
    )
    assert c.channel == "msedge" and all(p.startswith("C:\\PF") for p in seen)
    c = bd.detect_browser(
        system="linux", env={}, tables=TABLES, which=lambda n: "/usr/bin/" + n if n == "google-chrome" else None
    )
    assert (c.channel, c.path) == ("chrome", "/usr/bin/google-chrome")


def test_launch_browser_uses_channel(monkeypatch):
    monkeypatch.setattr(bd, "detect_browser", lambda *a, **k: bd.BrowserChoice("msedge", "/x", "auto"))
    calls = {}

    class Chromium:
        def launch(self, **kw):
            calls.update(kw)
            return "B"

    class P:
        chromium = Chromium()

    assert bd.launch_browser(P(), headless=False, args=["--lang=ja"]) == "B"
    assert calls["channel"] == "msedge" and calls["headless"] is False
    assert "executable_path" not in calls


def test_launch_failure_becomes_unavailable(monkeypatch):
    monkeypatch.setattr(bd, "detect_browser", lambda *a, **k: bd.BrowserChoice("chrome", "/x", "auto"))

    class P:
        class chromium:
            @staticmethod
            def launch(**kw):
                raise RuntimeError("policy")

    with pytest.raises(bd.BrowserUnavailable):
        bd.launch_browser(P())
