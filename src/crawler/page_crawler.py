"""Playwright を使った Web サイトクローラー。

BFS でリンクを追跡し、各ページのメタ・フォーム・スクリーンショットと
ネットワーク API 呼び出し・技術スタック情報を PageData として収集する。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

from playwright.sync_api import Browser, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from crawler.url_safety import is_safe_target

if TYPE_CHECKING:
    from analyzer.stack_detector import StackInfo

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

_SENSITIVE_KEYWORDS = ("payment", "checkout", "billing", "personal", "private")
_DUMMY_EMAIL = "test@example.com"
_DUMMY_PASSWORD = "Test1234!"
_DUMMY_DATE = "2024-01-01"
_DUMMY_NUMBER = "1"
_DUMMY_TEXT = "テスト入力値"

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
class ApiEndpoint:
    """クロール中に傍受した API 呼び出しの記録。"""

    method: str
    path: str
    status_code: int
    content_type: str
    sample_fields: tuple[str, ...]


@dataclass(frozen=True)
class PageData:
    url: str
    title: str
    headings: tuple[str, ...]
    links: tuple[str, ...]
    forms: tuple[FormData, ...]
    screenshot_path: str | None
    buttons: tuple[str, ...] = ()
    api_calls: tuple[ApiEndpoint, ...] = ()
    stack_info: StackInfo | None = None
    state_id: str = "default"  # DOM シグネチャ由来の状態識別子


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
        if max_pages > 0:
            _guard_session(page, base_url, auth_state)
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
) -> list[dict[str, object]]:
    """Lightweight BFS listing reachable pages (url + title + login wall 判定)
    without screenshots or form extraction. Backs the GUI '画面リスト取得' step."""
    base_url = normalize_url(url)
    robots = _load_robots_parser(base_url)
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(base_url, 0)]
    found: list[dict[str, object]] = []

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
        if targets:
            _guard_session(page, targets[0], auth_state)
        for target in targets:
            page_id = _format_page_id(len(pages) + 1)
            page_data = _crawl_page_with_id(page, target, page_id, output_dir)
            if page_data is not None:
                pages.append(page_data)
            time.sleep(CRAWL_DELAY_SEC)

    return pages


def _guard_session(page: Page, url: str, auth_state: Path | None) -> None:
    """認証付きクロールの入口で保存セッションの失効を確認する（#7）。
    失効（login wall 検出）時は SessionExpiredError を送出しクロールを中断する。
    中断により snapshot 保存に到達しないため、古い結果を上書きしない。"""
    from analyzer.login_wall import PageAuthSignals
    from crawler.link_extractor import has_password_field
    from crawler.session_guard import SessionExpiredError, is_session_expired

    if auth_state is None:
        return
    normalized = normalize_url(url)
    try:
        response = page.goto(normalized, wait_until="networkidle", timeout=DEFAULT_TIMEOUT_MS)
    except PlaywrightError as exc:
        logger.warning("セッション確認のためのアクセスに失敗しました: %s (%s)", url, exc)
        return
    signals = PageAuthSignals(
        requested_url=normalized,
        final_url=page.url,
        status=response.status if response is not None else 0,
        has_password_field=has_password_field(page),
    )
    if is_session_expired(auth_state, signals):
        raise SessionExpiredError(f"保存セッションが失効しています: {url}")


def _discover_one(page: Page, url: str, found: list[dict[str, object]]) -> tuple[str, ...]:
    from analyzer.login_wall import PageAuthSignals, detect_login_wall
    from crawler.link_extractor import (
        extract_internal_links,
        extract_page_title,
        has_password_field,
    )

    normalized = normalize_url(url)
    try:
        response = page.goto(normalized, wait_until="networkidle", timeout=DEFAULT_TIMEOUT_MS)
    except PlaywrightError as exc:
        logger.warning("画面リスト取得に失敗しました: %s (%s)", url, exc)
        return ()
    signals = PageAuthSignals(
        requested_url=normalized,
        final_url=page.url,
        status=response.status if response is not None else 0,
        has_password_field=has_password_field(page),
    )
    verdict = detect_login_wall(signals)
    found.append(
        {
            "url": normalized,
            "title": extract_page_title(page),
            "login_required": verdict.is_login_required,
            "login_reasons": list(verdict.reasons),
            "login_url": signals.final_url if verdict.is_login_required else "",
        }
    )
    return tuple(extract_internal_links(page, normalized))


def crawl_page(page: Page, url: str, output_dir: Path | None) -> PageData:
    from analyzer.stack_detector import detect_stack
    from crawler.link_extractor import (
        compute_dom_signature,
        extract_buttons,
        extract_forms_including_frames,
        extract_headings,
        extract_internal_links,
        extract_page_title,
    )
    from crawler.network_interceptor import NetworkCapture

    normalized_url = normalize_url(url)
    capture = NetworkCapture()
    capture.attach(page)
    try:
        response = page.goto(normalized_url, wait_until="networkidle", timeout=DEFAULT_TIMEOUT_MS)
        response_headers = dict(response.headers) if response else {}
        page_id = str(getattr(page, "_webspec2doc_page_id", _format_page_id(1)))
        screenshot_path = _save_screenshot(page, output_dir, page_id)
        stack = detect_stack(page, response_headers)
        title = extract_page_title(page)
        headings = tuple(extract_headings(page))
        links = tuple(extract_internal_links(page, normalized_url))
        forms = tuple(extract_forms_including_frames(page))
        buttons = tuple(extract_buttons(page))
        page_html = page.content()
        state_id = compute_dom_signature(page_html)
    finally:
        capture.detach()

    return PageData(
        url=normalized_url,
        title=title,
        headings=headings,
        links=links,
        forms=forms,
        screenshot_path=screenshot_path,
        buttons=buttons,
        api_calls=capture.finalize(),
        stack_info=stack,
        state_id=state_id,
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
        page._webspec2doc_page_id = page_id  # type: ignore[attr-defined,unused-ignore]
        return crawl_page(page, url, output_dir)
    except PlaywrightError as exc:
        logger.warning("ページのクロールに失敗しました: %s (%s)", url, exc)
        return None


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


def _save_screenshot(page: Page, output_dir: Path | None, page_id: str) -> str | None:
    if output_dir is None:
        return None
    screenshots_dir = output_dir / SCREENSHOTS_DIR_NAME
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = screenshots_dir / f"{page_id}.png"
    try:
        page.screenshot(path=str(screenshot_path), full_page=False)
    except PlaywrightError as exc:
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


def _is_spa_navigation(prev_url: str, new_url: str) -> bool:
    """pushState/hashchange による同一ドメイン内の URL 変化かどうかを判定する。

    host が同一でパス or ハッシュが変化した場合に True を返す。
    """
    prev = urlparse(normalize_url(prev_url))
    new = urlparse(normalize_url(new_url))
    same_host = _netloc_without_default_port(prev) == _netloc_without_default_port(new)
    path_changed = prev.path != new.path
    hash_changed = prev.fragment != new.fragment
    return same_host and (path_changed or hash_changed)


def _is_sensitive_form(form_data: FormData) -> bool:
    """決済・個人情報フォームか判定する（action URL にキーワードが含まれる場合）。"""
    action_lower = form_data.action.lower()
    return any(kw in action_lower for kw in _SENSITIVE_KEYWORDS)


def _dummy_value(field: FieldData) -> str:
    """フィールド種別に応じたダミー値を返す。maxlength がある場合は truncate する。"""
    ftype = field.field_type.lower()
    if ftype == "email":
        value = _DUMMY_EMAIL
    elif ftype == "password":
        value = _DUMMY_PASSWORD
    elif ftype in ("number", "range"):
        value = field.min_value if field.min_value else _DUMMY_NUMBER
    elif ftype == "date":
        value = _DUMMY_DATE
    elif ftype == "checkbox":
        value = "checked"
    elif ftype == "select":
        value = field.options[0] if field.options else ""
    else:
        value = _DUMMY_TEXT
    if field.maxlength is not None and len(value) > field.maxlength:
        value = value[: field.maxlength]
    return value


def _fill_form_fields(page: Page, form_data: FormData) -> None:
    """フォームの各フィールドにダミー値を入力する。"""
    for field in form_data.fields:
        if not field.name and not field.element_id:
            continue
        selector = f"#{field.element_id}" if field.element_id else f"[name='{field.name}']"
        ftype = field.field_type.lower()
        try:
            if ftype == "checkbox":
                page.check(selector)
            elif ftype == "select":
                val = field.options[0] if field.options else None
                if val:
                    page.select_option(selector, val)
            else:
                dummy = _dummy_value(field)
                if dummy:
                    page.fill(selector, dummy)
        except PlaywrightError as exc:
            logger.warning("フィールド入力をスキップしました: %s (%s)", selector, exc)


def crawl_form_flow(
    page: Page,
    form_data: FormData,
    output_dir: Path | None = None,
    page_id_prefix: str = "F",
    dry_run: bool = True,
) -> list[PageData]:
    """フォームにダミー値を入力し送信後の画面を取得する。

    dry_run=True: submit をインターセプトしてキャンセルし、確認画面への遷移は試みない。
    dry_run=False: 実際に送信（副作用あり・本番環境での使用禁止）。
    決済/個人情報フォームは action URL に "payment"/"checkout"/"billing"/"personal"/"private"
    が含まれる場合は dry_run=True を強制する。
    """
    if _is_sensitive_form(form_data):
        dry_run = True

    try:
        _fill_form_fields(page, form_data)
    except PlaywrightError as exc:
        logger.warning("フォームへの入力に失敗しました: %s", exc)
        return []

    if dry_run:
        return _crawl_form_dry_run(page, form_data, output_dir, page_id_prefix)
    return _crawl_form_submit(page, form_data, output_dir, page_id_prefix)


def _crawl_form_dry_run(
    page: Page,
    form_data: FormData,
    output_dir: Path | None,
    page_id_prefix: str,
) -> list[PageData]:
    """submit をインターセプトしてキャンセルし、現在ページの PageData を返す。"""
    prev_url = page.url

    def _abort(route: Any) -> None:
        try:
            route.abort()
        except PlaywrightError:
            pass

    try:
        page.route("**", _abort)
        selector = (
            f"form[action='{form_data.action}'] [type=submit]"
            if form_data.action
            else "[type=submit]"
        )
        page.click(selector, timeout=3_000)
    except PlaywrightError as exc:
        logger.warning("dry_run submit クリックをスキップしました: %s", exc)
    finally:
        try:
            page.unroute("**")
        except PlaywrightError:
            pass

    try:
        page_id = f"{page_id_prefix}001"
        screenshot_path = _save_screenshot(page, output_dir, page_id)
        return [
            PageData(
                url=page.url or prev_url,
                title=page.title(),
                headings=(),
                links=(),
                forms=(),
                screenshot_path=screenshot_path,
            )
        ]
    except PlaywrightError as exc:
        logger.warning("dry_run PageData 取得に失敗しました: %s", exc)
        return []


def _crawl_form_submit(
    page: Page,
    form_data: FormData,
    output_dir: Path | None,
    page_id_prefix: str,
) -> list[PageData]:
    """実際に submit して遷移先の PageData を返す。"""
    from crawler.link_extractor import extract_page_title

    prev_url = page.url
    try:
        selector = (
            f"form[action='{form_data.action}'] [type=submit]"
            if form_data.action
            else "[type=submit]"
        )
        page.click(selector, timeout=DEFAULT_TIMEOUT_MS)
        page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT_MS)
    except PlaywrightError as exc:
        logger.warning("フォーム送信に失敗しました: %s", exc)
        return []

    new_url = page.url
    if new_url == prev_url:
        return []

    try:
        page_id = f"{page_id_prefix}001"
        screenshot_path = _save_screenshot(page, output_dir, page_id)
        return [
            PageData(
                url=new_url,
                title=extract_page_title(page),
                headings=(),
                links=(),
                forms=(),
                screenshot_path=screenshot_path,
            )
        ]
    except PlaywrightError as exc:
        logger.warning("フォーム送信後の PageData 取得に失敗しました: %s", exc)
        return []


def _close_browser(browser: Browser) -> None:
    try:
        browser.close()
    except PlaywrightError as exc:
        logger.warning("ブラウザ終了時にエラーが発生しました: %s", exc)
