from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

from crawler.url_safety import is_safe_target

logger = logging.getLogger(__name__)

DEFAULT_DISCOVER_DELAY_SEC = 0.2
DEFAULT_DISCOVER_TIMEOUT_MS = 10_000
FAST_BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
USER_AGENT = "WebSpec2Doc"
NEXT_DEPTH_INCREMENT = 1


@dataclass(frozen=True)
class DiscoveryPage:
    url: str
    title: str
    login_required: bool
    login_reasons: list[str]
    login_url: str

    def to_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "title": self.title,
            "login_required": self.login_required,
            "login_reasons": self.login_reasons,
            "login_url": self.login_url,
        }


def discover_pages_fast(
    url: str,
    depth: int,
    max_pages: int,
    auth_state: str | None = None,
    on_page_found: Callable[[dict[str, object]], None] | None = None,
    delay_sec: float = DEFAULT_DISCOVER_DELAY_SEC,
    timeout_ms: int = DEFAULT_DISCOVER_TIMEOUT_MS,
    fast_mode: bool = True,
) -> list[dict[str, object]]:
    """Fast page discovery for the GUI screen analysis step.

    This intentionally gathers only the information needed by the screen selection UI:
    URL, title, login-wall signals, and internal links. It avoids screenshots, form
    extraction, network interception, and the previous networkidle wait.
    """
    base_url = normalize_url(url)
    robots = _load_robots_parser(base_url)
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(base_url, 0)]
    found: list[dict[str, object]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent=USER_AGENT,
                storage_state=auth_state or None,
            )
            page = context.new_page()
            page.set_default_timeout(timeout_ms)
            if fast_mode:
                _enable_fast_mode(page)

            while queue and len(found) < max_pages:
                current_url, current_depth = queue.pop(0)
                if _should_skip(current_url, current_depth, depth, visited, robots):
                    continue
                visited.add(current_url)

                page_info, links = _discover_one_fast(page, current_url, timeout_ms)
                if page_info is None:
                    if delay_sec:
                        time.sleep(delay_sec)
                    continue

                item = page_info.to_dict()
                found.append(item)
                if on_page_found is not None:
                    on_page_found(item)
                queue.extend(_next_urls(links, current_depth, visited, depth))
                if delay_sec:
                    time.sleep(delay_sec)
        finally:
            try:
                browser.close()
            except PlaywrightError as exc:
                logger.warning("ブラウザ終了時にエラーが発生しました: %s", exc)

    return found


def stream_discovery_events(
    url: str,
    depth: int,
    max_pages: int,
    auth_state: str | None = None,
) -> Iterator[str]:
    """Yield SSE payloads for the discovery endpoint."""

    def _emit(page: dict[str, object]) -> None:
        events.append(json.dumps({"page": page}, ensure_ascii=False))

    events: list[str] = []
    try:
        pages = discover_pages_fast(
            url=url,
            depth=depth,
            max_pages=max_pages,
            auth_state=auth_state,
            on_page_found=_emit,
        )
        for event in events:
            yield f"data: {event}\n\n"
        yield f"data: {json.dumps({'done': True, 'total': len(pages)}, ensure_ascii=False)}\n\n"
    except Exception as exc:  # pragma: no cover - defensive SSE boundary
        logger.exception("高速画面リスト取得に失敗しました")
        yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"


def _discover_one_fast(
    page: Page,
    url: str,
    timeout_ms: int,
) -> tuple[DiscoveryPage | None, tuple[str, ...]]:
    from analyzer.login_wall import PageAuthSignals, detect_login_wall
    from crawler.link_extractor import (
        extract_internal_links,
        extract_page_title,
        has_password_field,
    )

    normalized = normalize_url(url)
    try:
        response = page.goto(normalized, wait_until="domcontentloaded", timeout=timeout_ms)
    except PlaywrightError as exc:
        logger.warning("高速画面リスト取得に失敗しました: %s (%s)", url, exc)
        return None, ()

    signals = PageAuthSignals(
        requested_url=normalized,
        final_url=page.url,
        status=response.status if response is not None else 0,
        has_password_field=has_password_field(page),
    )
    verdict = detect_login_wall(signals)
    item = DiscoveryPage(
        url=normalized,
        title=extract_page_title(page),
        login_required=verdict.is_login_required,
        login_reasons=list(verdict.reasons),
        login_url=signals.final_url if verdict.is_login_required else "",
    )
    return item, tuple(extract_internal_links(page, normalized))


def _enable_fast_mode(page: Page) -> None:
    def _block_heavy_resources(route):
        if route.request.resource_type in FAST_BLOCKED_RESOURCE_TYPES:
            route.abort()
            return
        route.continue_()

    page.route("**/*", _block_heavy_resources)


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    normalized_path = path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, normalized_path, "", parsed.query, ""))


def _load_robots_parser(base_url: str) -> RobotFileParser:
    robots_url = urljoin(base_url, "/robots.txt")
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except OSError as exc:
        logger.warning("robots.txt を取得できませんでした: %s (%s)", robots_url, exc)
        parser.allow_all = True  # type: ignore[attr-defined]
    return parser


def _should_skip(
    url: str,
    current_depth: int,
    max_depth: int,
    visited: set[str],
    robots: RobotFileParser,
) -> bool:
    if current_depth > max_depth or url in visited:
        return True
    if not is_safe_target(url):
        logger.warning("安全でない URL をスキップしました: %s", url)
        return True
    if not robots.can_fetch(USER_AGENT, url):
        logger.warning("robots.txt によりスキップしました: %s", url)
        return True
    return False


def _next_urls(
    links: tuple[str, ...],
    current_depth: int,
    visited: set[str],
    max_depth: int,
) -> list[tuple[str, int]]:
    next_depth = current_depth + NEXT_DEPTH_INCREMENT
    if next_depth > max_depth:
        return []
    return [(link, next_depth) for link in links if link not in visited]
