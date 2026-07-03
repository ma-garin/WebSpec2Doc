"""ページ内アクション探索とバリデーション実測。

安全ホワイトリスト要素（button・[role=button]・details > summary・[role=tab]・
[aria-expanded]）のクリックで出現するモーダル・タブパネル・アコーディオンを
「画面状態」として検出する。また、必須フィールド未入力での dry-run 送信により
バリデーションメッセージを実測する。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from crawler.page_crawler import (
    FormData,
    PageState,
    SourceEvidence,
    ValidationObservation,
)

logger = logging.getLogger(__name__)

# submit を除外した安全ホワイトリスト要素
SAFE_ACTION_SELECTOR = ", ".join(
    [
        "button:not([type=submit])",
        "[role=button]:not([type=submit]):not(button)",
        "details > summary",
        "[role=tab]",
        "[aria-expanded]",
    ]
)

MAX_ACTIONS_ENV = "WEBSPEC2DOC_MAX_ACTIONS_PER_PAGE"
DEFAULT_MAX_ACTIONS = 10
_CLICK_TIMEOUT_MS = 2_000
_SETTLE_TIMEOUT_MS = 300

# クリック後の DOM 差分から状態種別を判定するためのマーカー
_MODAL_MARKERS = ('role="dialog"', "role='dialog'", "<dialog")
_TABPANEL_MARKERS = ('role="tabpanel"', "role='tabpanel'")
_EXPANDED_MARKERS = ('aria-expanded="true"', "aria-expanded='true'", "<details open")

_ELEMENT_DESCRIPTOR_JS = """
(el) => {
  if (el.id) return '#' + el.id;
  const role = el.getAttribute('role');
  const tag = el.tagName.toLowerCase();
  const text = (el.innerText || '').trim().slice(0, 20);
  if (role) return tag + '[role=' + role + ']' + (text ? ':has-text(\"' + text + '\")' : '');
  return tag + (text ? ':has-text(\"' + text + '\")' : '');
}
"""

_VALIDATION_MESSAGES_JS = """
() => {
  const out = [];
  document.querySelectorAll(':invalid').forEach((el) => {
    if (!el.validationMessage) return;
    const name = el.getAttribute('name') || el.getAttribute('id') || '';
    const selector = el.id
      ? '#' + el.id
      : (name ? "[name='" + name + "']" : el.tagName.toLowerCase());
    out.push({ name: name, message: el.validationMessage, selector: selector });
  });
  const alertSelector = '[role=alert], [aria-live], .error, .error-message, .invalid-feedback';
  document.querySelectorAll(alertSelector).forEach((el) => {
    const text = (el.innerText || '').trim();
    if (!text) return;
    const selector = el.id
      ? '#' + el.id
      : (el.getAttribute('role') ? '[role=' + el.getAttribute('role') + ']'
        : el.tagName.toLowerCase());
    out.push({ name: '', message: text, selector: selector });
  });
  return out;
}
"""


def max_actions_from_env() -> int:
    """環境変数から 1 ページあたりの最大アクション数を取得する（既定 10）。"""
    raw = os.environ.get(MAX_ACTIONS_ENV, "")
    if not raw:
        return DEFAULT_MAX_ACTIONS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "%s の値が不正です（%r）。既定値 %d を使用します。",
            MAX_ACTIONS_ENV,
            raw,
            DEFAULT_MAX_ACTIONS,
        )
        return DEFAULT_MAX_ACTIONS
    return max(0, value)


def _count_markers(html_content: str, markers: tuple[str, ...]) -> int:
    return sum(html_content.count(marker) for marker in markers)


def _detect_state_kind(before_html: str, after_html: str) -> str:
    """クリック前後の DOM 差分からモーダル・タブパネル・アコーディオンの出現を判定する。"""
    if _count_markers(after_html, _MODAL_MARKERS) > _count_markers(before_html, _MODAL_MARKERS):
        return "modal"
    if _count_markers(after_html, _TABPANEL_MARKERS) > _count_markers(
        before_html, _TABPANEL_MARKERS
    ):
        return "tabpanel"
    if _count_markers(after_html, _EXPANDED_MARKERS) > _count_markers(
        before_html, _EXPANDED_MARKERS
    ):
        return "accordion"
    return "dom_change"


def _describe_element(handle: Any) -> str:
    """要素のセレクタ風の説明文字列を取得する。"""
    try:
        descriptor = handle.evaluate(_ELEMENT_DESCRIPTOR_JS)
    except Exception as exc:
        logger.debug("要素説明の取得に失敗しました: %s", exc)
        return ""
    return descriptor if isinstance(descriptor, str) else ""


def explore_page_actions(page: Page, max_actions: int | None = None) -> tuple[PageState, ...]:
    """安全ホワイトリスト要素をクリックし、出現した画面状態を検出して返す。

    クリックはリクエスト遮断（MutationBlocker）下で行う前提。ページ遷移が
    発生した場合は元の URL に戻る。1 ページあたり最大 max_actions 回試行する。
    """
    from crawler.link_extractor import compute_state_signature

    limit = max_actions_from_env() if max_actions is None else max(0, max_actions)
    if limit == 0:
        return ()
    try:
        handles = page.query_selector_all(SAFE_ACTION_SELECTOR)
    except Exception as exc:
        logger.warning("アクション要素の列挙に失敗しました: %s", exc)
        return ()
    if not isinstance(handles, list) or not handles:
        return ()

    base_url = page.url
    states: list[PageState] = []
    seen_states: set[str] = set()
    attempts = 0

    for handle in handles:
        if attempts >= limit:
            break
        attempts += 1
        try:
            before_html = page.content()
        except PlaywrightError as exc:
            logger.warning("アクション探索を中断しました（DOM 取得失敗）: %s", exc)
            break
        before_sig = compute_state_signature(before_html)
        descriptor = _describe_element(handle)
        try:
            handle.click(timeout=_CLICK_TIMEOUT_MS)
        except Exception as exc:
            logger.debug("アクションクリックをスキップしました: %s (%s)", descriptor, exc)
            continue
        try:
            page.wait_for_timeout(_SETTLE_TIMEOUT_MS)
        except PlaywrightError:
            pass
        if page.url != base_url:
            # 遷移してしまった場合は探索対象外として元に戻る
            try:
                page.go_back(timeout=_CLICK_TIMEOUT_MS)
            except PlaywrightError as exc:
                logger.warning("アクション探索中の遷移から戻れませんでした: %s", exc)
                break
            continue
        try:
            after_html = page.content()
        except PlaywrightError:
            continue
        after_sig = compute_state_signature(after_html)
        if after_sig == before_sig or after_sig in seen_states:
            continue
        seen_states.add(after_sig)
        kind = _detect_state_kind(before_html, after_html)
        states.append(
            PageState(
                state_id=after_sig,
                trigger_selector=descriptor,
                kind=kind,
                description=f"{descriptor} クリックで {kind} 状態が出現",
            )
        )
        # モーダル等を閉じて次のアクションに備える
        try:
            page.keyboard.press("Escape")
        except Exception as exc:
            logger.debug("Escape キー送出に失敗しました: %s", exc)

    return tuple(states)


def measure_required_validation(
    page: Page,
    forms: tuple[FormData, ...],
    screenshot_path: str | None = None,
) -> tuple[ValidationObservation, ...]:
    """必須フィールド未入力での送信を dry-run 実行し、バリデーションメッセージを実測する。

    送信中は全リクエストを遮断するため、サーバへリクエストは到達しない。
    """
    observations: list[ValidationObservation] = []
    for form in forms:
        if not any(field.required for field in form.fields):
            continue
        observations.extend(_dry_run_form_validation(page, form, screenshot_path))
    return tuple(observations)


def _dry_run_form_validation(
    page: Page,
    form: FormData,
    screenshot_path: str | None,
) -> list[ValidationObservation]:
    """1 フォーム分の dry-run 送信とメッセージ収集を行う。"""

    def _abort(route: Any) -> None:
        try:
            route.abort()
        except Exception as exc:
            logger.debug("dry-run route.abort に失敗しました: %s", exc)

    selector = (
        f"form[action='{form.action}'] [type=submit]" if form.action else "[type=submit]"
    )
    raw_messages: Any = []
    try:
        page.route("**/*", _abort)
        page.click(selector, timeout=_CLICK_TIMEOUT_MS)
        try:
            page.wait_for_timeout(_SETTLE_TIMEOUT_MS)
        except PlaywrightError:
            pass
        raw_messages = page.evaluate(_VALIDATION_MESSAGES_JS)
    except Exception as exc:
        logger.debug("バリデーション実測をスキップしました: %s (%s)", selector, exc)
    finally:
        try:
            page.unroute("**/*", _abort)
        except Exception as exc:
            logger.debug("dry-run route 解除に失敗しました: %s", exc)

    if not isinstance(raw_messages, list):
        return []
    observations: list[ValidationObservation] = []
    for item in raw_messages:
        if not isinstance(item, dict):
            continue
        message = str(item.get("message") or "").strip()
        if not message:
            continue
        observations.append(
            ValidationObservation(
                field_name=str(item.get("name") or ""),
                message=message,
                evidence=SourceEvidence(
                    selector=str(item.get("selector") or ""),
                    html_attribute=None,
                    screenshot_path=screenshot_path,
                    bbox=None,
                ),
                confidence=1.0,
            )
        )
    return observations
