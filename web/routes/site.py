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
    login_urls: str = "",
    login_landing_url: str = "",
) -> None:
    """クロール成功時に再クロール用の設定を site.json へ保存する。

    login_urls: 認証が必要と判定された画面 URL（urls の部分集合）をカンマ区切りで渡す。
    再クロール時（recrawl.js）にログイン必須バナー・フォームを正しく復元するために使う
    （過去、再クロールでは常に login_required=false 扱いになり再発していた: INC参照）。
    """
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
                login_urls=tuple(u for u in login_urls.split(",") if u),
                login_landing_url=login_landing_url,
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
