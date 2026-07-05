"""registry.site_registry のユニットテスト（tmp ディレクトリで永続化を検証）"""

from __future__ import annotations

from pathlib import Path

from registry.site_registry import SiteConfig, list_sites, load_site, save_site


def _config(**kw) -> SiteConfig:
    base = dict(
        domain="example.com",
        urls=("https://example.com/",),
        crawl_mode="crawl",
        depth=2,
        max_pages=30,
        formats=("html", "md"),
        auth_path="",
    )
    base.update(kw)
    return SiteConfig(**base)


class TestSiteRegistry:
    def test_save_then_load_roundtrip(self, tmp_path: Path) -> None:
        config = _config()
        save_site(config, tmp_path)
        assert load_site("example.com", tmp_path) == config

    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        assert load_site("nope.com", tmp_path) is None

    def test_load_malformed_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.com" / "site.json"
        path.parent.mkdir(parents=True)
        path.write_text("{ not json", encoding="utf-8")
        assert load_site("broken.com", tmp_path) is None

    def test_list_sites_enumerates_all(self, tmp_path: Path) -> None:
        save_site(_config(domain="a.com"), tmp_path)
        save_site(_config(domain="b.com"), tmp_path)
        domains = {c.domain for c in list_sites(tmp_path)}
        assert domains == {"a.com", "b.com"}

    def test_list_sites_empty_when_no_base_dir(self, tmp_path: Path) -> None:
        assert list_sites(tmp_path / "missing") == []

    def test_login_urls_roundtrip(self, tmp_path: Path) -> None:
        """認証必須ページの URL とログイン着地 URL が保存・復元できる（再クロール復元用）。"""
        config = _config(
            urls=("https://example.com/", "https://example.com/mypage.html"),
            login_urls=("https://example.com/mypage.html",),
            login_landing_url="https://example.com/login.html",
        )
        save_site(config, tmp_path)
        loaded = load_site("example.com", tmp_path)
        assert loaded == config
        assert loaded.login_urls == ("https://example.com/mypage.html",)
        assert loaded.login_landing_url == "https://example.com/login.html"

    def test_login_urls_default_empty(self, tmp_path: Path) -> None:
        """login_urls/login_landing_url 省略時は空既定値（オプトイン・後方互換）。"""
        config = _config()
        save_site(config, tmp_path)
        loaded = load_site("example.com", tmp_path)
        assert loaded.login_urls == ()
        assert loaded.login_landing_url == ""

    def test_load_old_site_json_without_login_fields(self, tmp_path: Path) -> None:
        """login_urls キーが存在しない旧 site.json（過去の保存分）も安全に読み込める。"""
        import json

        path = tmp_path / "legacy.com" / "site.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(
                {
                    "domain": "legacy.com",
                    "urls": ["https://legacy.com/"],
                    "crawl_mode": "crawl",
                    "depth": 2,
                    "max_pages": 30,
                    "formats": ["html"],
                    "auth_path": "",
                }
            ),
            encoding="utf-8",
        )
        loaded = load_site("legacy.com", tmp_path)
        assert loaded is not None
        assert loaded.login_urls == ()
        assert loaded.login_landing_url == ""
