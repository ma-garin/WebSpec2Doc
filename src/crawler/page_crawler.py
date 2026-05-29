from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

from playwright.sync_api import Browser, Page, sync_playwright

CRAWL_DELAY_SEC = 1
DEFAULT_DEPTH = 3
DEFAULT_MAX_PAGES = 50
DEFAULT_TIMEOUT_MS = 30_000
HTTP_DEFAULT_PORT = 80
HTTPS_DEFAULT_PORT = 443
PAGE_ID_PREFIX = "P"
PAGE_ID_WIDTH = 3
SCREENSHOTS_DIR_NAME = "screenshots"
USER_AGENT = "WebSpec2Doc"
NEXT_DEPTH_INCREMENT = 1

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FieldData:
    field_type: str
    name: str
    placeholder: str
    required: bool
    maxlength: int | None = None
    minlength: int | None = None
    min_value: str = ""
    max_value: str = ""
    pattern: str = ""
    default: str = ""
    options: tuple[str, ...] = ()
    element_id: str = ""


@dataclass(frozen=True)
class FormData:
    action: str
    method: str
    fields: tuple[FieldData, ...]


@dataclass(frozen=True)
class PageData:
    url: str
    title: str
    headings: tuple[str, ...]
    links: tuple[str, ...]
    forms: tuple[FormData, ...]
    screenshot_path: str | None
    buttons: tuple[str, ...] = ()


@contextmanager
def _browser_page(auth_state: Path | None) -> Iterator[Page]:
    """Open a Playwright Chromium page with shared context settings."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent=USER_AGENT,
                storage_state=str(auth_state) if auth_state else None,
            )
            page = context.new_page()
            page.set_default_timeout(DEFAULT_TIMEOUT_MS)
            yield page
        finally:
            _close_browser(browser)


def crawl_site(
    url: str,
    depth: int = DEFAULT_DEPTH,
    max_pages: int = DEFAULT_MAX_PAGES,
    output_dir: Path | None = None,
    auth_state: Path | None = None,
) -> list[PageData]:
    base_url = normalize_url(url)
    robots = _load_robots_parser(base_url)
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(base_url, 0)]
    pages: list[PageData] = []

    with _browser_page(auth_state) as page:
        while queue and len(pages) < max_pages:
            current_url, current_depth = queue.pop(0)
            if _should_skip(current_url, current_depth, depth, visited, robots):
                continue
            visited.add(current_url)
            page_id = _format_page_id(len(pages) + 1)
            page_data = _crawl_page_with_id(page, current_url, page_id, output_dir)
            if page_data is None:
                time.sleep(CRAWL_DELAY_SEC)
                continue
            pages.append(page_data)
            queue.extend(_next_urls(page_data.links, current_depth, visited, depth))
            time.sleep(CRAWL_DELAY_SEC)

    return pages


def discover_pages(
    url: str,
    depth: int = DEFAULT_DEPTH,
    max_pages: int = DEFAULT_MAX_PAGES,
    auth_state: Path | None = None,
) -> list[dict[str, str]]:
    """Lightweight BFS listing reachable pages (url + title) without
    screenshots or form extraction. Backs the GUI '画面リスト取得' step."""
    base_url = normalize_url(url)
    robots = _load_robots_parser(base_url)
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(base_url, 0)]
    found: list[dict[str, str]] = []

    with _browser_page(auth_state) as page:
        while queue and len(found) < max_pages:
            current_url, current_depth = queue.pop(0)
            if _should_skip(current_url, current_depth, depth, visited, robots):
                continue
            visited.add(current_url)
            links = _discover_one(page, current_url, found)
            queue.extend(_next_urls(links, current_depth, visited, depth))
            time.sleep(CRAWL_DELAY_SEC)

    return found


def crawl_urls(
    urls: list[str],
    output_dir: Path | None = None,
    auth_state: Path | None = None,
) -> list[PageData]:
    """Crawl an explicit list of URLs (no link following). Backs the GUI
    'selected pages' / 'manual URL' modes."""
    targets = list(dict.fromkeys(normalize_url(u) for u in urls if u.strip()))
    pages: list[PageData] = []

    with _browser_page(auth_state) as page:
        for target in targets:
            page_id = _format_page_id(len(pages) + 1)
            page_data = _crawl_page_with_id(page, target, page_id, output_dir)
            if page_data is not None:
                pages.append(page_data)
            time.sleep(CRAWL_DELAY_SEC)

    return pages


def _discover_one(page: Page, url: str, found: list[dict[str, str]]) -> tuple[str, ...]:
    from crawler.link_extractor import extract_internal_links, extract_page_title

    normalized = normalize_url(url)
    try:
        page.goto(normalized, wait_until="networkidle", timeout=DEFAULT_TIMEOUT_MS)
    except Exception as exc:
        logger.warning("画面リスト取得に失敗しました: %s (%s)", url, exc)
        return ()
    found.append({"url": normalized, "title": extract_page_title(page)})
    return tuple(extract_internal_links(page, normalized))


def crawl_page(page: Page, url: str, output_dir: Path | None) -> PageData:
    from crawler.link_extractor import (
        extract_buttons,
        extract_forms,
        extract_headings,
        extract_internal_links,
        extract_page_title,
    )

    normalized_url = normalize_url(url)
    page.goto(normalized_url, wait_until="networkidle", timeout=DEFAULT_TIMEOUT_MS)
    page_id = str(getattr(page, "_webspec2doc_page_id", _format_page_id(1)))
    screenshot_path = _save_screenshot(page, output_dir, page_id)
    return PageData(
        url=normalized_url,
        title=extract_page_title(page),
        headings=tuple(extract_headings(page)),
        links=tuple(extract_internal_links(page, normalized_url)),
        forms=tuple(extract_forms(page)),
        screenshot_path=screenshot_path,
        buttons=tuple(extract_buttons(page)),
    )


def is_internal_link(base_url: str, link_url: str) -> bool:
    base = urlparse(normalize_url(base_url))
    target = urlparse(normalize_url(urljoin(base_url, link_url)))
    return _netloc_without_default_port(base) == _netloc_without_default_port(target)


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    normalized_path = path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, normalized_path, "", parsed.query, ""))


def _crawl_page_with_id(
    page: Page,
    url: str,
    page_id: str,
    output_dir: Path | None,
) -> PageData | None:
    try:
        setattr(page, "_webspec2doc_page_id", page_id)
        return crawl_page(page, url, output_dir)
    except Exception as exc:
        logger.warning("ページのクロールに失敗しました: %s (%s)", url, exc)
        return None


def _load_robots_parser(base_url: str) -> RobotFileParser:
    robots_url = urljoin(base_url, "/robots.txt")
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception as exc:
        logger.warning("robots.txt を取得できませんでした: %s (%s)", robots_url, exc)
        parser.allow_all = True
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


def _save_screenshot(page: Page, output_dir: Path | None, page_id: str) -> str | None:
    if output_dir is None:
        return None
    screenshots_dir = output_dir / SCREENSHOTS_DIR_NAME
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = screenshots_dir / f"{page_id}.png"
    try:
        page.screenshot(path=str(screenshot_path), full_page=False)
    except Exception as exc:
        logger.warning("スクリーンショット保存に失敗しました: %s (%s)", screenshot_path, exc)
        return None
    return str(screenshot_path)


def _format_page_id(index: int) -> str:
    return f"{PAGE_ID_PREFIX}{index:0{PAGE_ID_WIDTH}d}"


def _netloc_without_default_port(parsed: Any) -> str:
    hostname = parsed.hostname or ""
    port = parsed.port
    if (parsed.scheme == "http" and port == HTTP_DEFAULT_PORT) or (
        parsed.scheme == "https" and port == HTTPS_DEFAULT_PORT
    ):
        return hostname
    return f"{hostname}:{port}" if port else hostname


def _close_browser(browser: Browser) -> None:
    try:
        browser.close()
    except Exception as exc:
        logger.warning("ブラウザ終了時にエラーが発生しました: %s", exc)
