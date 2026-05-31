from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, current_app, request

from web.config import OUTPUT_DIR
from web.validation import _valid_domain

bp = Blueprint("site", __name__)


def save_site_config(
    domain: str,
    urls: str,
    crawl_mode: str,
    depth: str,
    max_pages: str,
    formats: list[str],
    auth: str,
) -> None:
    """クロール成功時に再クロール用の設定を site.json へ保存する。"""
    from registry.site_registry import SiteConfig, save_site

    try:
        save_site(
            SiteConfig(
                domain=domain,
                urls=tuple(u for u in urls.split(",") if u),
                crawl_mode=crawl_mode,
                depth=int(depth),
                max_pages=int(max_pages),
                formats=tuple(formats),
                auth_path=auth,
            ),
            OUTPUT_DIR,
        )
    except (OSError, ValueError) as exc:
        current_app.logger.warning("site.json の保存に失敗しました: %s (%s)", domain, exc)


@bp.get("/api/site")
def api_site() -> dict:
    from registry.site_registry import load_site

    domain = request.args.get("domain", "").strip()
    if not domain or not _valid_domain(domain):
        return {"site": None}
    config = load_site(domain, OUTPUT_DIR)
    return {"site": asdict(config) if config else None}
