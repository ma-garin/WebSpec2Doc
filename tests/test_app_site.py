"""/api/site ルートと site.json 連携のテスト（Flask テストクライアント）"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod

from registry.site_registry import SiteConfig, save_site


def _client():
    return appmod.app.test_client()


def test_api_site_returns_saved_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(appmod, "OUTPUT_DIR", tmp_path)
    save_site(
        SiteConfig(
            domain="example.com",
            urls=("https://example.com/",),
            crawl_mode="crawl",
            depth=3,
            max_pages=42,
            formats=("html", "md"),
        ),
        tmp_path,
    )
    data = _client().get("/api/site?domain=example.com").get_json()
    assert data["site"]["depth"] == 3
    assert data["site"]["max_pages"] == 42
    assert data["site"]["urls"] == ["https://example.com/"]


def test_api_site_unknown_domain_returns_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(appmod, "OUTPUT_DIR", tmp_path)
    data = _client().get("/api/site?domain=nope.com").get_json()
    assert data["site"] is None
