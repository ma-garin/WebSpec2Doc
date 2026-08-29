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

# ライブ DOM から「開閉・選択・可視」状態を読み取るスナップショット。
# HTML 文字列の正規表現ではなく実際の DOM プロパティ（.open / aria-selected /
# aria-expanded / 可視性）を見るため、表示/非表示トグル型のモーダルにも対応する。
# document.querySelectorAll は native API のため open shadow root を貫通
# できない。scan() が各 shadow root を再帰的に辿ることで、Web Components に
# 包まれたモーダル・タブ・アコーディオンも検出できるようにする。
_LIVE_STATE_JS = """
() => {
  const isVisible = (el) => {
    if (el.hidden) return false;
    const s = window.getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const key = (el, i) => el.id || (el.getAttribute('aria-controls') || '') || ('idx' + i);
  const parts = [];
  let idx = 0;
  const scan = (root) => {
    // モーダル/ダイアログの可視状態
    root.querySelectorAll('[role=dialog], dialog').forEach((el) => {
      if (isVisible(el)) parts.push('dialog:' + key(el, idx++));
    });
    // タブの選択状態
    root.querySelectorAll('[role=tab][aria-selected=true]').forEach((el) => {
      parts.push('tab:' + key(el, idx++));
    });
    // アコーディオン（details[open]）
    root.querySelectorAll('details[open]').forEach((el) => {
      parts.push('details:' + key(el, idx++));
    });
    // aria-expanded=true
    root.querySelectorAll('[aria-expanded=true]').forEach((el) => {
      parts.push('expanded:' + key(el, idx++));
    });
    // open shadow root を再帰的に辿る
    root.querySelectorAll('*').forEach((el) => {
      if (el.shadowRoot) scan(el.shadowRoot);
    });
  };
  scan(document);
  return parts.sort();
}
"""


def _live_state(page: Page) -> tuple[str, ...]:
    """ライブ DOM から開閉・選択・可視状態のスナップショットを取得する。"""
    try:
        raw = page.evaluate(_LIVE_STATE_JS)
    except Exception as exc:
        logger.debug("ライブ状態の取得に失敗しました: %s", exc)
        return ()
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in raw)


def state_signature(parts: tuple[str, ...]) -> str:
    """ライブ状態パーツから画面状態のシグネチャを計算する。

    クロール時（PageState.state_id）と操作記録時（探索カバレッジの接合キー）で
    共用する。アルゴリズムを変える場合は両者を同時に更新すること。
    """
    import hashlib

    if not parts:
        return "default"
    key = "|".join(sorted(parts))
    return hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:8]  # noqa: S324


def _state_kind_from_live(new_parts: set[str]) -> str:
    """新規に出現した状態パーツから画面状態の種別を判定する。"""
    if any(p.startswith("dialog:") for p in new_parts):
        return "modal"
    if any(p.startswith("tab:") for p in new_parts):
        return "tabpanel"
    if any(p.startswith("details:") or p.startswith("expanded:") for p in new_parts):
        return "accordion"
    return "dom_change"


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
        before_parts = set(_live_state(page))
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
        after_parts = set(_live_state(page))
        new_parts = after_parts - before_parts
        after_sig = state_signature(tuple(after_parts))
        if not new_parts or after_sig in seen_states:
            continue
        seen_states.add(after_sig)
        kind = _state_kind_from_live(new_parts)
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


# JS フレームワーク（React Hook Form 等）の遅延表示エラーを待つセレクタと上限
_FEEDBACK_SELECTOR = ":invalid, [role=alert], .error, .error-message, .invalid-feedback"
_FEEDBACK_TIMEOUT_MS = 1_500


def _wait_for_validation_feedback(page: Page) -> None:
    """バリデーションフィードバックの出現を明示的に待つ。

    固定 sleep ではなくエラー表示要素の出現を待つことで、JS フレームワークの
    遅延表示エラーを取りこぼしにくくする。出現しなければ短い settle 待ちに
    フォールバックする（HTML5 ネイティブ検証は :invalid で即時ヒットする）。
    """
    try:
        page.wait_for_selector(_FEEDBACK_SELECTOR, timeout=_FEEDBACK_TIMEOUT_MS, state="attached")
        return
    except Exception as exc:
        logger.debug("バリデーション表示の待機がタイムアウトしました: %s", exc)
    try:
        page.wait_for_timeout(_SETTLE_TIMEOUT_MS)
    except PlaywrightError:
        pass


def _try_click_submit(page: Page, form: FormData) -> bool:
    """フォームの submit を best-effort でクリックする（失敗は致命ではない）。

    submit クリックは JS フレームワーク（React Hook Form 等）の遅延バリデーションを
    誘発するために行う。ただし HTML5 ネイティブの :invalid は未 submit でも
    validationMessage を保持するため、クリックできなくても後段の収集は成立する。
    複合セレクタ（action 指定）が一致しない場合はフォームスコープにフォールバックする。
    """
    candidates: list[str] = []
    if form.action:
        candidates.append(f"form[action='{form.action}'] [type=submit]")
    candidates.append("[type=submit]")
    for selector in candidates:
        try:
            page.click(selector, timeout=_CLICK_TIMEOUT_MS)
            return True
        except Exception as exc:
            logger.debug("submit クリック試行に失敗しました: %s (%s)", selector, exc)
    return False


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

    raw_messages: Any = []
    try:
        page.route("**/*", _abort)
        # submit を試行して遅延バリデーションも誘発するが、クリック成否に関わらず
        # 後段で :invalid を収集する（クリック失敗で観測を落とさない）。
        _try_click_submit(page, form)
        _wait_for_validation_feedback(page)
        raw_messages = page.evaluate(_VALIDATION_MESSAGES_JS)
    except Exception as exc:
        # 収集自体が失敗した場合は黙殺せず warning で可視化する（原因究明のため）。
        logger.warning("バリデーション実測に失敗しました（action=%s）: %s", form.action, exc)
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
