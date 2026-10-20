from __future__ import annotations

import pathlib
import re

import browser_detect as bd

CRAWLER = pathlib.Path(__file__).resolve().parents[1] / "src" / "crawler"


def test_no_direct_chromium_launch_in_crawler():
    offenders = [
        p.name for p in CRAWLER.glob("*.py") if re.search(r"\.chromium\.launch\(", p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_crawl_browser_page_launches_with_channel(monkeypatch):
    from crawler import page_crawler

    calls = {}

    class Ctx:
        def new_page(self):
            return type("P", (), {"set_default_timeout": lambda self, t: None})()

    class Browser:
        def new_context(self, **kw):
            return Ctx()

        def close(self):
            pass

    class Chromium:
        def launch(self, **kw):
            calls.update(kw)
            return Browser()

    class PW:
        chromium = Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(page_crawler, "sync_playwright", lambda: PW())
    monkeypatch.setattr(bd, "detect_browser", lambda *a, **k: bd.BrowserChoice("chrome", "/x", "auto"))
    with page_crawler._browser_page(None):
        pass
    assert calls["channel"] == "chrome"
