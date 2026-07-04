"""Playwright を使った Web サイトクローラー。

BFS でリンクを追跡し、各ページのメタ・フォーム・スクリーンショットと
ネットワーク API 呼び出し・技術スタック情報を PageData として収集する。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

from playwright.sync_api import Browser, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from crawler.playwright_runtime import configure_playwright_browsers_path
from crawler.politeness import (
    RETRYABLE_STATUS_CODES,
    OriginRateLimiter,
    RetryableHTTPError,
    TokenBucketLimiter,
    append_audit_log,
    backoff_delays,
    build_user_agent,
    crawl_interval_from_env,
    robots_crawl_delay,
)
from crawler.session_guard import SessionExpiredError
from crawler.url_safety import is_safe_target

if TYPE_CHECKING:
    from analyzer.stack_detector import StackInfo
    from ux.axe_runner import AxeViolation

CRAWL_DELAY_SEC = 0
DEFAULT_DEPTH = 3
DEFAULT_MAX_PAGES = 50
DEFAULT_TIMEOUT_MS = 30_000
STABILITY_TIMEOUT_MS = 3_000
HTTP_DEFAULT_PORT = 80
HTTPS_DEFAULT_PORT = 443
PAGE_ID_PREFIX = "P"
PAGE_ID_WIDTH = 3
SCREENSHOTS_DIR_NAME = "screenshots"
USER_AGENT = build_user_agent()
BROWSER_LOCALE = "ja-JP"
NEXT_DEPTH_INCREMENT = 1

_SENSITIVE_KEYWORDS = ("payment", "checkout", "billing", "personal", "private")
_DUMMY_EMAIL = "test@example.com"
_DUMMY_PASSWORD = "Test1234!"
_DUMMY_DATE = "2024-01-01"
_DUMMY_NUMBER = "1"
_DUMMY_TEXT = "テスト入力値"

logger = logging.getLogger(__name__)

CrawlEventCallback = Callable[[dict[str, object]], None]
CheckpointCallback = Callable[[list["PageData"]], None]
StopRequested = Callable[[], bool]
# --ux-review 時、画面ごとの axe 検査結果をサイドチャネルで受け取るコールバック。
# PageData のスキーマは変更しない（report.json 互換保護。SPEC-3-4 §5-2）
UxResultCallback = Callable[[str, tuple["AxeViolation", ...]], None]


class LoginWallDetected(RuntimeError):
    def __init__(self, url: str, login_url: str, reasons: tuple[str, ...]) -> None:
        super().__init__(f"ログインウォールを検出しました: {url}")
        self.url = url
        self.login_url = login_url
        self.reasons = reasons


@dataclass(frozen=True)
class SourceEvidence:
    """フィールドや観点の出所を示す根拠情報。

    selector: 対象要素の CSS セレクタ
    html_attribute: 根拠となった HTML 属性名（属性由来でない場合は None）
    screenshot_path: 該当画面のスクリーンショットパス
    bbox: スクリーンショット上の要素位置 (x, y, width, height)
    """

    selector: str
    html_attribute: str | None = None
    screenshot_path: str | None = None
    bbox: tuple[int, int, int, int] | None = None


def evidence_to_dict(evidence: SourceEvidence | None) -> dict[str, object] | None:
    """SourceEvidence を JSON シリアライズ可能な dict に変換する（None はそのまま）。"""
    if evidence is None:
        return None
    return {
        "selector": evidence.selector,
        "html_attribute": evidence.html_attribute,
        "screenshot_path": evidence.screenshot_path,
        "bbox": list(evidence.bbox) if evidence.bbox is not None else None,
    }


def evidence_from_dict(data: object) -> SourceEvidence | None:
    """dict（JSON 由来）から SourceEvidence を復元する。不正・欠落時は None を返す。"""
    if not isinstance(data, dict):
        return None
    raw_bbox = data.get("bbox")
    bbox: tuple[int, int, int, int] | None = None
    if isinstance(raw_bbox, list | tuple) and len(raw_bbox) == 4:
        try:
            bbox = (int(raw_bbox[0]), int(raw_bbox[1]), int(raw_bbox[2]), int(raw_bbox[3]))
        except (TypeError, ValueError):
            bbox = None
    raw_attr = data.get("html_attribute")
    raw_shot = data.get("screenshot_path")
    return SourceEvidence(
        selector=str(data.get("selector") or ""),
        html_attribute=str(raw_attr) if raw_attr else None,
        screenshot_path=str(raw_shot) if raw_shot else None,
        bbox=bbox,
    )


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
    aria_label: str = ""
    aria_required: bool = False
    role: str = ""
    has_visible_label: bool = False
    # DOM 実測由来のため confidence は 1.0 固定
    evidence: SourceEvidence | None = None
    confidence: float = 1.0


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
class PageState:
    """ページ内アクション（クリック等）で出現した画面状態。"""

    state_id: str  # DOM 状態シグネチャ
    trigger_selector: str  # 状態を出現させた要素のセレクタ
    kind: str  # "modal" / "tabpanel" / "accordion" / "dom_change"
    description: str = ""


@dataclass(frozen=True)
class ValidationObservation:
    """バリデーション実測（dry-run 送信）で観測されたメッセージ。"""

    field_name: str
    message: str
    evidence: SourceEvidence | None = None
    # 実測値のため confidence は 1.0 固定
    confidence: float = 1.0


@dataclass(frozen=True)
class SpaTransition:
    """pushState / replaceState / hashchange による SPA 遷移の記録。"""

    from_url: str
    to_url: str
    kind: str  # "pushstate" / "replacestate" / "hashchange" / "dom_change"


@dataclass(frozen=True)
class EmbeddedFrame:
    """ページ内 iframe・closed shadow root の記録。

    readable=False は「検出したが読めない」ことを示す（evidence-only 原則:
    無いことにせず、確認できなかった旨を明示する）。
    src は iframe の場合は絶対 URL、closed shadow root の場合は
    "shadow:<タグ名>" 形式。
    """

    src: str
    readable: bool
    note: str = ""


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
    a11y_issues: tuple[str, ...] = ()
    page_states: tuple[PageState, ...] = ()
    validation_observations: tuple[ValidationObservation, ...] = ()
    spa_transitions: tuple[SpaTransition, ...] = ()
    embedded_frames: tuple[EmbeddedFrame, ...] = ()


@contextmanager
def _browser_page(auth_state: Path | None) -> Iterator[Page]:
    """Open a Playwright Chromium page with shared context settings."""
    configure_playwright_browsers_path()
    with sync_playwright() as playwright:
        # --lang でブラウザ UI 言語を日本語にし、HTML5 バリデーション
        # メッセージが日本語で得られるようにする（context の locale だけでは
        # validationMessage の言語は変わらないため launch 引数で指定する）
        browser = playwright.chromium.launch(headless=True, args=[f"--lang={BROWSER_LOCALE}"])
        try:
            context = browser.new_context(
                user_agent=USER_AGENT,
                storage_state=str(auth_state) if auth_state else None,
                # 日本語ロケール: HTML5 バリデーションメッセージ実測を
                # 日本のエンドユーザーが目にする文言（日本語）で取得する
                locale=BROWSER_LOCALE,
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
    on_event: CrawlEventCallback | None = None,
    on_checkpoint: CheckpointCallback | None = None,
    stop_requested: StopRequested | None = None,
    ux_review: bool = False,
    on_ux_result: UxResultCallback | None = None,
) -> list[PageData]:
    base_url = normalize_url(url)
    robots = _load_robots_parser(base_url)
    limiter = _make_rate_limiter(robots)
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(base_url, 0)]
    pages: list[PageData] = []
    _emit_event(on_event, "crawl_started", total=max_pages, parallelism=1)
    append_audit_log(
        output_dir,
        {
            "event": "crawl_started",
            "mode": "site",
            "base_url": base_url,
            "robots_allowed": robots.can_fetch(USER_AGENT, base_url),
            "robots_crawl_delay_sec": robots_crawl_delay(robots, USER_AGENT),
            "interval_sec": limiter.interval_sec,
            "user_agent": USER_AGENT,
            "depth": depth,
            "max_pages": max_pages,
            "mutations_allowed": _mutations_allowed_with_warning(),
        },
    )

    with _browser_page(auth_state) as page:
        while queue and len(pages) < max_pages:
            if stop_requested and stop_requested():
                break
            current_url, current_depth = queue.pop(0)
            skip_reason = _skip_reason(current_url, current_depth, depth, visited, robots)
            if skip_reason:
                if skip_reason not in {"visited", "depth"}:
                    _emit_event(on_event, "page_skipped", url=current_url, reason=skip_reason)
                continue
            visited.add(current_url)
            page_id = _format_page_id(len(pages) + 1)
            started_at = time.monotonic()
            _emit_event(
                on_event,
                "page_started",
                url=current_url,
                index=len(pages) + 1,
                total=max_pages,
            )
            limiter.acquire()
            page_data = _crawl_page_with_id(
                page,
                current_url,
                page_id,
                output_dir,
                auth_state=auth_state,
                on_event=on_event,
                ux_review=ux_review,
                on_ux_result=on_ux_result,
            )
            if page_data is None:
                _polite_delay(page)
                continue
            pages.append(page_data)
            if on_checkpoint:
                on_checkpoint(list(pages))
            _emit_event(
                on_event,
                "page_completed",
                url=current_url,
                completed=len(pages),
                total=max_pages,
                elapsed_sec=round(time.monotonic() - started_at, 3),
            )
            queue.extend(_next_urls(page_data.links, current_depth, visited, depth))
            _polite_delay(page)

    event = "crawl_cancelled" if stop_requested and stop_requested() else "crawl_completed"
    _emit_event(on_event, event, completed=len(pages), total=max_pages)
    return pages


def discover_pages(
    url: str,
    depth: int = DEFAULT_DEPTH,
    max_pages: int = DEFAULT_MAX_PAGES,
    auth_state: Path | None = None,
    on_page_found: Callable[[dict[str, object]], None] | None = None,
    on_event: CrawlEventCallback | None = None,
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
            prev_count = len(found)
            current_url, current_depth = queue.pop(0)
            skip_reason = _skip_reason(current_url, current_depth, depth, visited, robots)
            if skip_reason:
                if skip_reason not in {"visited", "depth"}:
                    _emit_event(on_event, "page_skipped", url=current_url, reason=skip_reason)
                continue
            visited.add(current_url)
            links = _discover_one(page, current_url, found)
            if on_page_found is not None and len(found) > prev_count:
                on_page_found(found[-1])
            queue.extend(_next_urls(links, current_depth, visited, depth))
            _polite_delay(page)

    return found


def crawl_urls(
    urls: list[str],
    output_dir: Path | None = None,
    auth_state: Path | None = None,
    parallelism: int = 1,
    respect_robots: bool = True,
    on_event: CrawlEventCallback | None = None,
    on_checkpoint: CheckpointCallback | None = None,
    stop_requested: StopRequested | None = None,
    ux_review: bool = False,
    on_ux_result: UxResultCallback | None = None,
) -> list[PageData]:
    """Crawl an explicit list of URLs (no link following). Backs the GUI
    'selected pages' / 'manual URL' modes."""
    targets = list(dict.fromkeys(normalize_url(u) for u in urls if u.strip()))
    requested_total = len(targets)
    worker_count = max(1, min(parallelism, requested_total or 1))
    _emit_event(on_event, "crawl_started", total=requested_total, parallelism=worker_count)
    robots_skipped: list[str] = []
    origin_delays: dict[str, float] = {}
    if respect_robots:
        targets, robots_skipped, origin_delays = _filter_robots_targets(targets, on_event)
    # オリジンごとに独立した間隔制御（別サイトの Crawl-Delay に巻き込まれない）
    limiter = OriginRateLimiter(crawl_interval_from_env())
    for origin, delay in origin_delays.items():
        limiter.set_crawl_delay(origin, delay)
    max_delay = max(origin_delays.values(), default=None) if origin_delays else None
    append_audit_log(
        output_dir,
        {
            "event": "crawl_started",
            "mode": "urls",
            "target_urls": targets,
            "respect_robots": respect_robots,
            "robots_skipped_urls": robots_skipped,
            "robots_crawl_delay_sec": max_delay,
            "interval_sec": max(limiter.interval_sec, max_delay or 0.0),
            "per_origin_crawl_delays": origin_delays,
            "user_agent": USER_AGENT,
            "parallelism": worker_count,
            "mutations_allowed": _mutations_allowed_with_warning(),
        },
    )
    if not targets:
        _emit_event(on_event, "crawl_completed", completed=0, total=requested_total)
        return []
    worker_count = max(1, min(parallelism, len(targets) or 1))
    if worker_count > 1:
        from crawler.parallel_crawler import crawl_urls_parallel

        return crawl_urls_parallel(
            targets,
            output_dir,
            auth_state,
            worker_count,
            on_event,
            on_checkpoint,
            stop_requested,
            limiter=limiter,
            ux_review=ux_review,
            on_ux_result=on_ux_result,
        )

    pages: list[PageData] = []
    with _browser_page(auth_state) as page:
        for index, target in enumerate(targets, 1):
            if stop_requested and stop_requested():
                break
            page_id = _format_page_id(len(pages) + 1)
            started_at = time.monotonic()
            _emit_event(on_event, "page_started", url=target, index=index, total=len(targets))
            limiter.acquire(target)
            if auth_state is None and on_event is None and not ux_review:
                page_data = _crawl_page_with_id(page, target, page_id, output_dir)
            else:
                page_data = _crawl_page_with_id(
                    page,
                    target,
                    page_id,
                    output_dir,
                    auth_state=auth_state,
                    on_event=on_event,
                    ux_review=ux_review,
                    on_ux_result=on_ux_result,
                )
            if page_data is not None:
                pages.append(page_data)
                if on_checkpoint:
                    on_checkpoint(list(pages))
                _emit_event(
                    on_event,
                    "page_completed",
                    url=target,
                    completed=len(pages),
                    total=len(targets),
                    elapsed_sec=round(time.monotonic() - started_at, 3),
                )
            _polite_delay(page)

    event = "crawl_cancelled" if stop_requested and stop_requested() else "crawl_completed"
    _emit_event(on_event, event, completed=len(pages), total=len(targets))
    return pages


def _goto_stable(page: Page, url: str) -> Any:
    """DOM構築を待って返し、networkidleは短時間だけ補助的に待つ。"""
    response = page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
    try:
        page.wait_for_load_state("networkidle", timeout=STABILITY_TIMEOUT_MS)
    except PlaywrightError:
        logger.debug("networkidle待機を打ち切りました: %s", url)
    return response


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
        response = _goto_stable(page, normalized)
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
        response = _goto_stable(page, normalized)
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
    if verdict.is_login_required:
        return ()
    return tuple(extract_internal_links(page, normalized))


def crawl_page(
    page: Page,
    url: str,
    output_dir: Path | None,
    auth_state: Path | None = None,
    ux_review: bool = False,
    on_ux_result: UxResultCallback | None = None,
) -> PageData:
    from analyzer.login_wall import PageAuthSignals, detect_login_wall
    from analyzer.stack_detector import detect_stack
    from crawler.action_explorer import explore_page_actions, measure_required_validation
    from crawler.link_extractor import (
        collect_embedded_frames,
        compute_state_signature,
        extract_a11y_issues,
        extract_buttons_all_scopes,
        extract_forms_including_frames,
        extract_headings_all_scopes,
        extract_links_all_scopes,
        extract_page_title,
        has_password_field,
    )
    from crawler.network_interceptor import MutationBlocker, NetworkCapture
    from crawler.spa_monitor import SpaTransitionMonitor

    normalized_url = normalize_url(url)
    capture = NetworkCapture()
    blocker = MutationBlocker()
    spa_monitor = SpaTransitionMonitor()
    spa_monitor.attach(page)
    capture.attach(page)
    blocker.attach(page)
    try:
        response = _goto_stable(page, normalized_url)
        if response is not None and response.status in RETRYABLE_STATUS_CODES:
            raise RetryableHTTPError(normalized_url, response.status)
        signals = PageAuthSignals(
            requested_url=normalized_url,
            final_url=page.url,
            status=response.status if response else 0,
            has_password_field=has_password_field(page),
        )
        verdict = detect_login_wall(signals)
        if verdict.is_login_required:
            if auth_state is not None:
                raise SessionExpiredError(f"保存セッションが失効しています: {normalized_url}")
            raise LoginWallDetected(normalized_url, signals.final_url, verdict.reasons)
        response_headers = dict(response.headers) if response else {}
        page_id = str(getattr(page, "_webspec2doc_page_id", _format_page_id(1)))
        screenshot_path = _save_screenshot(page, output_dir, page_id)
        stack = detect_stack(page, response_headers)
        title = extract_page_title(page)
        headings = tuple(extract_headings_all_scopes(page, normalized_url))
        links = tuple(extract_links_all_scopes(page, normalized_url))
        forms = _attach_screenshot_evidence(
            tuple(extract_forms_including_frames(page, normalized_url)), screenshot_path
        )
        buttons = tuple(extract_buttons_all_scopes(page, normalized_url))
        a11y_issues = tuple(extract_a11y_issues(page))
        embedded_frames = tuple(collect_embedded_frames(page, normalized_url))
        if ux_review:
            # axe-core 検査は既存抽出の後に実行する（AC-1〜3）。
            # 結果は PageData に追加せず（スキーマ互換保護 §5-2）、
            # コールバック経由のサイドチャネルで収集する。
            from ux.axe_runner import run_axe

            axe_violations = run_axe(page, screenshot_path)
            if on_ux_result is not None:
                on_ux_result(normalized_url, axe_violations)
        page_html = page.content()
        state_id = compute_state_signature(page_html)
        # DOM を変更する探索・実測は静的抽出の完了後に行う
        page_states = explore_page_actions(page)
        validation_observations = measure_required_validation(page, forms, screenshot_path)
        spa_transitions = spa_monitor.collect(page)
    finally:
        blocker.detach()
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
        a11y_issues=a11y_issues,
        page_states=page_states,
        validation_observations=validation_observations,
        spa_transitions=spa_transitions,
        embedded_frames=embedded_frames,
    )


def _attach_screenshot_evidence(
    forms: tuple[FormData, ...],
    screenshot_path: str | None,
) -> tuple[FormData, ...]:
    """抽出済みフォームの各フィールド evidence にスクリーンショットパスを補完する。"""
    if screenshot_path is None:
        return forms
    updated_forms: list[FormData] = []
    for form in forms:
        fields = tuple(
            (
                replace(field, evidence=replace(field.evidence, screenshot_path=screenshot_path))
                if field.evidence is not None
                else field
            )
            for field in form.fields
        )
        updated_forms.append(replace(form, fields=fields))
    return tuple(updated_forms)


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
    auth_state: Path | None = None,
    on_event: CrawlEventCallback | None = None,
    ux_review: bool = False,
    on_ux_result: UxResultCallback | None = None,
) -> PageData | None:
    try:
        page._webspec2doc_page_id = page_id  # type: ignore[attr-defined,unused-ignore]
        return _crawl_page_with_backoff(
            page, url, output_dir, auth_state, on_event, ux_review, on_ux_result
        )
    except LoginWallDetected as exc:
        logger.warning("ログインウォールによりスキップしました: %s", url)
        _emit_event(
            on_event,
            "login_wall_detected",
            url=exc.url,
            login_url=exc.login_url,
            reasons=list(exc.reasons),
        )
        return None
    except RetryableHTTPError as exc:
        logger.warning("リトライ上限に達したためスキップしました: %s (HTTP %d)", url, exc.status)
        _emit_event(
            on_event, "page_failed", url=url, reason="retry_exhausted", detail=str(exc.status)
        )
        return None
    except PlaywrightError as exc:
        logger.warning("ページのクロールに失敗しました: %s (%s)", url, exc)
        _emit_event(on_event, "page_failed", url=url, reason="playwright", detail=str(exc))
        return None


def _crawl_page_with_backoff(
    page: Page,
    url: str,
    output_dir: Path | None,
    auth_state: Path | None,
    on_event: CrawlEventCallback | None,
    ux_review: bool = False,
    on_ux_result: UxResultCallback | None = None,
) -> PageData:
    """HTTP 429/503 受信時に exponential backoff（初期2秒・最大60秒・最大5回）でリトライする。"""
    delays = backoff_delays()
    while True:
        try:
            return crawl_page(page, url, output_dir, auth_state, ux_review, on_ux_result)
        except RetryableHTTPError as exc:
            delay = next(delays, None)
            if delay is None:
                raise
            logger.warning(
                "HTTP %d を受信したため %.1f 秒待機してリトライします: %s",
                exc.status,
                delay,
                url,
            )
            _emit_event(on_event, "page_retry", url=url, status=exc.status, wait_sec=delay)
            time.sleep(delay)


def _mutations_allowed_with_warning() -> bool:
    """破壊的リクエスト許可状態を返し、許可時は警告ログを残す（監査ログ記録用）。"""
    from crawler.network_interceptor import mutations_allowed

    allowed = mutations_allowed()
    if allowed:
        logger.warning(
            "WEBSPEC2DOC_ALLOW_MUTATION=1 が設定されています。"
            "POST/PUT/DELETE/PATCH リクエストの遮断が解除されています。"
        )
    return allowed


def _make_rate_limiter(robots: RobotFileParser | None) -> TokenBucketLimiter:
    """環境変数の間隔設定と robots.txt の Crawl-Delay から rate limiter を構築する。"""
    limiter = TokenBucketLimiter(crawl_interval_from_env())
    if robots is not None:
        limiter.apply_crawl_delay(robots_crawl_delay(robots, USER_AGENT))
    return limiter


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
    return _skip_reason(url, current_depth, max_depth, visited, robots) is not None


def _skip_reason(
    url: str,
    current_depth: int,
    max_depth: int,
    visited: set[str],
    robots: RobotFileParser,
) -> str | None:
    if current_depth > max_depth:
        return "depth"
    if url in visited:
        return "visited"
    if not is_safe_target(url):
        logger.warning("安全でない URL をスキップしました: %s", url)
        return "unsafe_url"
    if not robots.can_fetch(USER_AGENT, url):
        logger.warning("robots.txt によりスキップしました: %s", url)
        return "robots"
    return None


def _filter_robots_targets(
    targets: list[str],
    on_event: CrawlEventCallback | None,
) -> tuple[list[str], list[str], dict[str, float]]:
    """robots.txt で許可された URL・スキップされた URL・オリジン別 Crawl-Delay を返す。"""
    parsers: dict[str, RobotFileParser] = {}
    allowed: list[str] = []
    skipped: list[str] = []
    origin_delays: dict[str, float] = {}
    for target in targets:
        parsed = urlparse(target)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        parser = parsers.get(origin)
        if parser is None:
            parser = _load_robots_parser(origin)
            parsers[origin] = parser
            delay = robots_crawl_delay(parser, USER_AGENT)
            if delay is not None:
                origin_delays[origin] = delay
        reason = _skip_reason(target, 0, 0, set(), parser)
        if reason:
            skipped.append(target)
            _emit_event(on_event, "page_skipped", url=target, reason=reason)
        else:
            allowed.append(target)
    return allowed, skipped, origin_delays


def _emit_event(callback: CrawlEventCallback | None, event: str, **details: object) -> None:
    if callback is not None:
        callback({"event": event, **details})


def _polite_delay(page: Page) -> None:
    if CRAWL_DELAY_SEC > 0:
        page.wait_for_timeout(CRAWL_DELAY_SEC * 1000)


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
