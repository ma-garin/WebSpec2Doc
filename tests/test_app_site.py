"""/api/site ルートと site.json 連携のテスト（Flask テストクライアント）"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.history as history_mod
import web.routes.site as site_mod

from registry.site_registry import SiteConfig, save_site


def _client():
    return appmod.app.test_client()


def test_api_site_returns_saved_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(site_mod, "OUTPUT_DIR", tmp_path)
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
    monkeypatch.setattr(site_mod, "OUTPUT_DIR", tmp_path)
    data = _client().get("/api/site?domain=nope.com").get_json()
    assert data["site"] is None


def test_delete_site_success(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(history_mod, "OUTPUT_DIR", tmp_path)
    site_dir = tmp_path / "example.com"
    site_dir.mkdir()
    (site_dir / "report.html").write_text("<html></html>", encoding="utf-8")

    res = _client().delete("/api/site/example.com")

    assert res.status_code == 200
    assert res.get_json() == {"ok": True, "domain": "example.com"}
    assert not site_dir.exists()


def test_delete_site_invalid_domain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(history_mod, "OUTPUT_DIR", tmp_path)

    # Flask が URL 正規化で ../etc を処理するため、ハンドラに届く不正ドメイン文字列で検証
    res = _client().delete("/api/site/!!invalid!!")

    assert res.status_code == 400


def test_delete_site_not_found(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(history_mod, "OUTPUT_DIR", tmp_path)

    res = _client().delete("/api/site/missing.example")

    assert res.status_code == 404
