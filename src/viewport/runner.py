"""マルチビューポート観測の実行。

各ビューポートで同じサイトをクロールし、基準との差分を文書化する。
クロール自体は既存の crawl_site をそのまま使う（観測ロジックを二重に持たない）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from viewport.comparison import compare_viewports
from viewport.profiles import DESKTOP, ViewportProfile, resolve_profiles
from viewport.reporter import save_viewport_report

logger = logging.getLogger(__name__)

CrawlFn = Callable[..., list[Any]]


def run_multi_viewport(
    url: str,
    out_dir: Path,
    *,
    viewports: list[str] | tuple[str, ...] | None = None,
    baseline: str = DESKTOP,
    depth: int = 2,
    max_pages: int = 30,
    auth_state: Path | None = None,
    crawl_fn: CrawlFn | None = None,
) -> dict[str, Any]:
    """指定ビューポートで順にクロールし、差分レポートを書き出す。

    crawl_fn を差し替えられるようにしてあるのは、実ブラウザ無しで
    オーケストレーションを検証できるようにするため。
    """
    profiles = resolve_profiles(viewports)
    if baseline not in {profile.name for profile in profiles}:
        raise ValueError(f"基準ビューポート {baseline} が観測対象に含まれていません")

    crawler = crawl_fn or _default_crawl_fn()
    observations: dict[str, list[Any]] = {}
    failures: dict[str, str] = {}

    for profile in profiles:
        try:
            observations[profile.name] = _crawl_one(
                crawler, url, profile, depth, max_pages, auth_state, out_dir
            )
        except Exception as exc:  # noqa: BLE001 - 1ビューポートの失敗で全体を捨てない
            logger.warning("ビューポート %s の観測に失敗: %s", profile.name, exc)
            failures[profile.name] = str(exc)

    if baseline not in observations:
        raise RuntimeError(
            f"基準ビューポート {baseline} の観測に失敗したため比較できません: "
            f"{failures.get(baseline, '原因不明')}"
        )

    report = compare_viewports(observations, baseline=baseline)
    # 失敗したビューポートを黙って無かったことにしない。
    report["meta"]["failed_viewports"] = failures
    outputs = save_viewport_report(report, out_dir)
    report["outputs"] = {key: str(path) for key, path in outputs.items()}
    return report


def _crawl_one(
    crawler: CrawlFn,
    url: str,
    profile: ViewportProfile,
    depth: int,
    max_pages: int,
    auth_state: Path | None,
    out_dir: Path,
) -> list[Any]:
    logger.info("ビューポート観測: %s (%dx%d)", profile.name, profile.width, profile.height)
    return crawler(
        url,
        depth=depth,
        max_pages=max_pages,
        output_dir=out_dir / "viewports" / profile.name,
        auth_state=auth_state,
        viewport=profile,
    )


def _default_crawl_fn() -> CrawlFn:
    from crawler.page_crawler import crawl_site

    return crawl_site
