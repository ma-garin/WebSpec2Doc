"""AutoRun開始設定の正規化。"""

from __future__ import annotations

from typing import Any

from web.config import MAX_DEPTH, MAX_PAGES_LIMIT
from web.validation import _clean_int


def resolve_crawl_limits(form: Any, body: dict[str, Any]) -> tuple[int, int]:
    """未指定時は全対象相当の上限を使い、入力値を安全な範囲へ収める。"""
    depth = _clean_int(
        form.get("depth") or body.get("depth", str(MAX_DEPTH)), MAX_DEPTH, 1, MAX_DEPTH
    )
    max_pages = _clean_int(
        form.get("max_pages") or body.get("max_pages", str(MAX_PAGES_LIMIT)),
        MAX_PAGES_LIMIT,
        1,
        MAX_PAGES_LIMIT,
    )
    return depth, max_pages
