"""追加アクセスなしで技術ヘルス成果物を構築する。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from crawler.page_crawler import PageData

TECHNICAL_HEALTH_FILE_NAME = "technical_health.json"


def build_technical_health(pages: list[PageData]) -> dict[str, Any]:
    """到達済みページの実測だけから技術ヘルスを構築する。"""
    from crawler.page_crawler import is_internal_link, normalize_url

    observed = {normalize_url(page.url): page for page in pages}
    screens: list[dict[str, Any]] = []
    for page in pages:
        broken_links: list[dict[str, object]] = []
        for link in page.links:
            if not is_internal_link(page.url, link):
                continue
            target = observed.get(normalize_url(link))
            if target is not None and int(target.http_status) >= 400:
                broken_links.append({"url": target.url, "status_code": int(target.http_status)})
        screens.append(
            {
                "url": page.url,
                "title": page.title,
                "status_code": int(page.http_status),
                "http_error": int(page.http_status) >= 400,
                "broken_links": broken_links,
                "console_errors": list(page.console_errors),
                "mixed_content": list(page.mixed_content),
                "screenshot_path": page.screenshot_path,
            }
        )

    return {
        "claim_boundary": "クロール中に到達・観測できた対象のみ",
        "summary": {
            "page_http_errors": sum(1 for screen in screens if screen["http_error"]),
            "broken_links": sum(len(screen["broken_links"]) for screen in screens),
            "console_errors": sum(len(screen["console_errors"]) for screen in screens),
            "mixed_content": sum(len(screen["mixed_content"]) for screen in screens),
        },
        "screens": screens,
    }


def save_technical_health(payload: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / TECHNICAL_HEALTH_FILE_NAME
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
