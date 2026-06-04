"""ログインフォームへの自動入力・送信・セッション保存を担う。

GUI の「自動ログイン」フローと CLI の --login-simple / --login-scrape / --login-submit
コマンドを実装する。パスワードはメモリ内のみで保持し、送信後は変数を破棄する。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

from analyzer.login_wall import PageAuthSignals, detect_login_wall
from crawler.link_extractor import extract_forms, has_password_field
from crawler.page_crawler import DEFAULT_TIMEOUT_MS, USER_AGENT, _close_browser, normalize_url

SUBMIT_TIMEOUT_MS = 15_000
FILL_TIMEOUT_MS = 3_000
EXCLUDED_TYPES = frozenset({"hidden", "submit", "button", "reset", "image"})

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoginField:
    name: str
    field_type: str
    label: str
    placeholder: str
    required: bool
    element_id: str


@dataclass(frozen=True)
class ScrapeResult:
    ok: bool
    fields: tuple[LoginField, ...]
    current_url: str
    error: str = ""


@dataclass(frozen=True)
class SubmitResult:
    success: bool
    needs_more_fields: bool
    fields: tuple[LoginField, ...]
    current_url: str
    error: str = ""


def scrape_login_fields(url: str) -> ScrapeResult:
    """ログインページのフォームフィールドを取得する。"""
    normalized = normalize_url(url)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(user_agent=USER_AGENT)
            page = ctx.new_page()
            page.set_default_timeout(DEFAULT_TIMEOUT_MS)
            try:
                page.goto(normalized, wait_until="networkidle", timeout=DEFAULT_TIMEOUT_MS)
            except Exception as exc:
                return ScrapeResult(ok=False, fields=(), current_url=normalized, error=str(exc))
            fields = _visible_fields(page)
            return ScrapeResult(ok=bool(fields), fields=tuple(fields), current_url=page.url)
        finally:
            _close_browser(browser)


def submit_login_form(
    field_values: dict[str, str],
    current_url: str,
    auth_path: Path,
    temp_session_path: Path | None = None,
) -> SubmitResult:
    """フォームに値を入力して送信し、成功時はセッションを auth_path に保存する。
    MFA 等で追加入力が必要な場合は needs_more_fields=True と新フィールドを返す。
    パスワード等の値は送信後にメモリから自動破棄される（保存しない）。"""
    normalized = normalize_url(current_url)
    storage = str(temp_session_path) if temp_session_path and temp_session_path.exists() else None
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(user_agent=USER_AGENT, storage_state=storage)
            page = ctx.new_page()
            page.set_default_timeout(DEFAULT_TIMEOUT_MS)
            try:
                page.goto(normalized, wait_until="networkidle", timeout=DEFAULT_TIMEOUT_MS)
            except Exception as exc:
                return SubmitResult(
                    success=False,
                    needs_more_fields=False,
                    fields=(),
                    current_url=normalized,
                    error=str(exc),
                )
            _fill(page, field_values)
            _submit(page)

            verdict = detect_login_wall(
                PageAuthSignals(
                    requested_url=normalized,
                    final_url=page.url,
                    status=200,
                    has_password_field=has_password_field(page),
                )
            )
            if not verdict.is_login_required:
                auth_path.parent.mkdir(parents=True, exist_ok=True)
                ctx.storage_state(path=str(auth_path))
                return SubmitResult(
                    success=True, needs_more_fields=False, fields=(), current_url=page.url
                )

            new_fields = _visible_fields(page)
            if new_fields and temp_session_path is not None:
                temp_session_path.parent.mkdir(parents=True, exist_ok=True)
                ctx.storage_state(path=str(temp_session_path))

            if not new_fields:
                return SubmitResult(
                    success=False,
                    needs_more_fields=False,
                    fields=(),
                    current_url=page.url,
                    error="認証に失敗しました。IDまたはパスワードをご確認ください。",
                )
            return SubmitResult(
                success=False,
                needs_more_fields=True,
                fields=tuple(new_fields),
                current_url=page.url,
            )
        finally:
            _close_browser(browser)


def submit_login_simple(
    username: str,
    password: str,
    login_url: str,
    auth_path: Path,
) -> SubmitResult:
    """text/email入力にusername、password入力にpasswordを自動マッピングして送信する。
    フィールドのname属性に依存せず、input[type]で対象を特定するためサイト差異に強い。"""
    normalized = normalize_url(login_url)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(user_agent=USER_AGENT)
            page = ctx.new_page()
            page.set_default_timeout(DEFAULT_TIMEOUT_MS)
            try:
                page.goto(normalized, wait_until="networkidle", timeout=DEFAULT_TIMEOUT_MS)
            except Exception as exc:
                return SubmitResult(
                    success=False,
                    needs_more_fields=False,
                    fields=(),
                    current_url=normalized,
                    error=str(exc),
                )
            _fill_generic(page, username, password)
            _submit(page)
            verdict = detect_login_wall(
                PageAuthSignals(
                    requested_url=normalized,
                    final_url=page.url,
                    status=200,
                    has_password_field=has_password_field(page),
                )
            )
            if not verdict.is_login_required:
                auth_path.parent.mkdir(parents=True, exist_ok=True)
                ctx.storage_state(path=str(auth_path))
                return SubmitResult(
                    success=True, needs_more_fields=False, fields=(), current_url=page.url
                )
            return SubmitResult(
                success=False,
                needs_more_fields=False,
                fields=(),
                current_url=page.url,
                error="認証に失敗しました。IDまたはパスワードをご確認ください。",
            )
        finally:
            _close_browser(browser)


def _fill_generic(page: Page, username: str, password: str) -> None:
    """ページ上の最初のテキスト/メール入力にusername、パスワード入力にpasswordを入力する。"""
    if username:
        try:
            page.locator('input[type="email"], input[type="text"], input:not([type])').first.fill(
                username, timeout=FILL_TIMEOUT_MS
            )
        except Exception as exc:
            logger.warning("ユーザーID入力失敗: %s", exc)
    if password:
        try:
            page.locator('input[type="password"]').first.fill(password, timeout=FILL_TIMEOUT_MS)
        except Exception as exc:
            logger.warning("パスワード入力失敗: %s", exc)


def _visible_fields(page: Page) -> list[LoginField]:
    forms = extract_forms(page)
    seen: set[str] = set()
    result: list[LoginField] = []
    for form in forms:
        for f in form.fields:
            if f.field_type in EXCLUDED_TYPES:
                continue
            key = f.name or f.element_id
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(
                LoginField(
                    name=f.name,
                    field_type=f.field_type,
                    label=f.placeholder or f.name,
                    placeholder=f.placeholder,
                    required=f.required,
                    element_id=f.element_id,
                )
            )
    return result


def _fill(page: Page, field_values: dict[str, str]) -> None:
    for name, value in field_values.items():
        if not value:
            continue
        try:
            page.locator(f'[name="{name}"]').first.fill(str(value), timeout=FILL_TIMEOUT_MS)
        except Exception:
            try:
                page.locator(f"#{name}").first.fill(str(value), timeout=FILL_TIMEOUT_MS)
            except Exception as exc:
                logger.warning("フィールド入力失敗: name=%s, %s", name, exc)


def _submit(page: Page) -> None:
    try:
        page.locator("button[type=submit], input[type=submit]").first.click(timeout=FILL_TIMEOUT_MS)
    except Exception:
        try:
            page.keyboard.press("Enter")
        except Exception as exc:
            logger.warning("フォーム送信失敗: %s", exc)
    try:
        page.wait_for_load_state("networkidle", timeout=SUBMIT_TIMEOUT_MS)
    except Exception as exc:
        logger.warning("送信後待機タイムアウト: %s", exc)
