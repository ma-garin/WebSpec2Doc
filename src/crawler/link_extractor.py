from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, cast

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from crawler.page_crawler import (
    FieldData,
    FormData,
    SourceEvidence,
    is_internal_link,
    normalize_url,
)

DEFAULT_FORM_METHOD = "get"
EMPTY_TEXT = ""

logger = logging.getLogger(__name__)


def compute_dom_signature(html_content: str) -> str:
    """表示中のインタラクティブ要素の構造ハッシュを計算する。

    モーダル・タブ・アコーディオンの開閉で変化する可視要素の集合が対象。
    同一 URL で DOM 状態が変わったことを検出するために使用する。
    """
    identifiers: list[str] = []

    # role="dialog"|"tabpanel" の id を抽出（属性順不同）
    for m in re.finditer(
        r'role=["\'](?:dialog|tabpanel)["\'][^>]*id=["\']([^"\']+)["\']',
        html_content,
    ):
        identifiers.append(m.group(1))
    for m in re.finditer(
        r'id=["\']([^"\']+)["\'][^>]*role=["\'](?:dialog|tabpanel)["\']',
        html_content,
    ):
        identifiers.append(m.group(1))

    # aria-expanded="true" の id / aria-controls を抽出
    for m in re.finditer(
        r'aria-expanded=["\']true["\'][^>]*(?:id|aria-controls)=["\']([^"\']+)["\']',
        html_content,
    ):
        identifiers.append(m.group(1))

    # <form> の id / name を抽出（prefix で form との区別を明示）
    for m in re.finditer(r'<form[^>]+(?:id|name)=["\']([^"\']+)["\']', html_content):
        identifiers.append("form:" + m.group(1))

    if not identifiers:
        return "default"

    key = "|".join(sorted(set(identifiers)))
    return hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:8]  # noqa: S324


_LANDMARK_TAG_PATTERN = re.compile(r"<(main|nav|header|footer|aside)\b", re.IGNORECASE)
_LANDMARK_ROLE_PATTERN = re.compile(
    r'role=["\'](main|navigation|banner|contentinfo|complementary|search)["\']'
)


def compute_state_signature(html_content: str) -> str:
    """可視領域の主要 landmark 構造と開閉状態から DOM 状態シグネチャを計算する。

    fingerprint v2（状態ベース画面同定）用。landmark 構造（main/nav/header 等）と
    ``compute_dom_signature`` の開閉状態（モーダル・タブ・アコーディオン）を合成する。
    """
    landmarks = sorted({m.group(1).lower() for m in _LANDMARK_TAG_PATTERN.finditer(html_content)})
    roles = sorted({m.group(1).lower() for m in _LANDMARK_ROLE_PATTERN.finditer(html_content)})
    open_state = compute_dom_signature(html_content)
    if not landmarks and not roles and open_state == "default":
        return "default"
    key = "|".join([*landmarks, *(f"role:{r}" for r in roles), f"open:{open_state}"])
    return hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()[:8]  # noqa: S324


def extract_internal_links(page: Page, base_url: str) -> list[str]:
    try:
        hrefs = cast(
            list[str],
            page.eval_on_selector_all("a[href]", "(els) => els.map((a) => a.href)"),
        )
    except Exception as exc:
        logger.warning("リンク抽出に失敗しました: %s", exc)
        return []

    normalized_links = [
        normalize_url(href) for href in hrefs if href and is_internal_link(base_url, href)
    ]
    return list(dict.fromkeys(normalized_links))


def has_password_field(page: Page) -> bool:
    """ページ内に <input type=password> が存在するか（login wall 検出の素性）。"""
    try:
        return page.query_selector("input[type=password]") is not None
    except Exception as exc:
        logger.warning("パスワード欄の判定に失敗しました: %s", exc)
        return False


def extract_forms(page: Page) -> list[FormData]:
    try:
        raw_forms = cast(list[dict[str, Any]], page.eval_on_selector_all("form", _FORM_SCRIPT))
    except Exception as exc:
        logger.warning("フォーム抽出に失敗しました: %s", exc)
        return []
    return [_to_form_data(raw_form) for raw_form in raw_forms]


def extract_headings(page: Page) -> list[str]:
    try:
        values = cast(
            list[str],
            page.eval_on_selector_all(
                "h1, h2, h3",
                "(els) => els.map((el) => (el.innerText || '').trim()).filter(Boolean)",
            ),
        )
    except Exception as exc:
        logger.warning("見出し抽出に失敗しました: %s", exc)
        return []
    return values


def extract_page_title(page: Page) -> str:
    try:
        return page.title().strip()
    except Exception as exc:
        logger.warning("タイトル抽出に失敗しました: %s", exc)
        return EMPTY_TEXT


def extract_buttons(page: Page) -> list[str]:
    try:
        values = cast(list[str], page.eval_on_selector_all(_BUTTON_SELECTOR, _BUTTON_SCRIPT))
    except Exception as exc:
        logger.warning("ボタン抽出に失敗しました: %s", exc)
        return []
    return list(dict.fromkeys([value for value in values if value]))


def _frame_to_forms(frame: Any) -> list[FormData]:
    """フレーム内の全フォームを FormData リストに変換する。
    クロスオリジンエラーは呼び出し元でキャッチするので、ここでは素直に実行する。"""
    raw_forms = cast(list[dict[str, Any]], frame.eval_on_selector_all("form", _FORM_SCRIPT))
    return [_to_form_data(raw_form) for raw_form in raw_forms]


def extract_forms_including_frames(page: Page) -> list[FormData]:
    """メインフレームおよびすべての子 iframe から FormData を収集する。

    iframe は同一オリジンのみ対象（クロスオリジン iframe はアクセス不可のためスキップ）。
    重複 action を除去して返す。
    """
    all_forms: list[FormData] = extract_forms(page)
    seen_actions: set[str] = {f.action for f in all_forms}

    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            frame_forms = _frame_to_forms(frame)
        except PlaywrightError as exc:
            logger.warning("iframe のフォーム抽出をスキップしました: %s", exc)
            continue
        for form in frame_forms:
            if form.action not in seen_actions:
                all_forms.append(form)
                seen_actions.add(form.action)

    return all_forms


def _to_form_data(raw_form: dict[str, Any]) -> FormData:
    raw_fields = cast(list[dict[str, Any]], raw_form.get("fields", []))
    fields = tuple(_to_field_data(raw_field) for raw_field in raw_fields)
    return FormData(
        action=str(raw_form.get("action") or EMPTY_TEXT),
        method=str(raw_form.get("method") or DEFAULT_FORM_METHOD).lower(),
        fields=fields,
    )


def _field_evidence(raw_field: dict[str, Any]) -> SourceEvidence:
    """抽出フィールドの DOM 上の出所（セレクタ・属性・位置）を根拠として構築する。"""
    element_id = str(raw_field.get("id") or EMPTY_TEXT)
    name = str(raw_field.get("name") or EMPTY_TEXT)
    if element_id:
        selector = f"#{element_id}"
        html_attribute = "id"
    elif name:
        selector = f"[name='{name}']"
        html_attribute = "name"
    else:
        selector = str(raw_field.get("field_type") or "input")
        html_attribute = None
    raw_bbox = raw_field.get("bbox")
    bbox: tuple[int, int, int, int] | None = None
    if isinstance(raw_bbox, list) and len(raw_bbox) == 4:
        try:
            bbox = (int(raw_bbox[0]), int(raw_bbox[1]), int(raw_bbox[2]), int(raw_bbox[3]))
        except (TypeError, ValueError):
            bbox = None
    return SourceEvidence(
        selector=selector,
        html_attribute=html_attribute,
        screenshot_path=None,
        bbox=bbox,
    )


def _to_field_data(raw_field: dict[str, Any]) -> FieldData:
    return FieldData(
        field_type=str(raw_field.get("field_type") or EMPTY_TEXT),
        name=str(raw_field.get("name") or EMPTY_TEXT),
        placeholder=str(raw_field.get("placeholder") or EMPTY_TEXT),
        required=bool(raw_field.get("required", False)),
        maxlength=_to_int(raw_field.get("maxlength")),
        minlength=_to_int(raw_field.get("minlength")),
        min_value=str(raw_field.get("min") or EMPTY_TEXT),
        max_value=str(raw_field.get("max") or EMPTY_TEXT),
        pattern=str(raw_field.get("pattern") or EMPTY_TEXT),
        default=str(raw_field.get("default") or EMPTY_TEXT),
        options=tuple(str(opt) for opt in (raw_field.get("options") or [])),
        element_id=str(raw_field.get("id") or EMPTY_TEXT),
        aria_label=str(raw_field.get("aria_label") or EMPTY_TEXT),
        aria_required=bool(raw_field.get("aria_required", False)),
        role=str(raw_field.get("role") or EMPTY_TEXT),
        has_visible_label=bool(raw_field.get("has_visible_label", False)),
        evidence=_field_evidence(raw_field),
        confidence=1.0,
    )


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


_FORM_SCRIPT = """
(forms) => forms.map((form) => ({
  action: form.getAttribute('action') || '',
  method: (form.getAttribute('method') || 'get').toLowerCase(),
  fields: Array.from(form.querySelectorAll('input, select, textarea')).map((field) => {
    const tag = field.tagName.toLowerCase();
    const type = tag === 'input'
      ? (field.getAttribute('type') || 'text').toLowerCase()
      : tag;
    const options = tag === 'select'
      ? Array.from(field.options).map((o) => (o.value || o.text || '').trim()).filter(Boolean)
      : [];
    return {
      field_type: type,
      name: field.getAttribute('name') || field.getAttribute('id') || '',
      id: field.getAttribute('id') || '',
      placeholder: field.getAttribute('placeholder') || '',
      required: Boolean(field.required),
      maxlength: field.getAttribute('maxlength'),
      minlength: field.getAttribute('minlength'),
      min: field.getAttribute('min') || '',
      max: field.getAttribute('max') || '',
      pattern: field.getAttribute('pattern') || '',
      default: field.getAttribute('value') || '',
      aria_label: field.getAttribute('aria-label') || '',
      aria_required: field.getAttribute('aria-required') === 'true' || field.required,
      role: field.getAttribute('role') || '',
      has_visible_label: (() => {
        const id = field.getAttribute('id');
        if (id && document.querySelector('label[for="' + id + '"]')) return true;
        if (field.getAttribute('aria-label')) return true;
        if (field.getAttribute('aria-labelledby')) return true;
        return false;
      })(),
      options: options,
      bbox: (() => {
        const r = field.getBoundingClientRect();
        return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)];
      })(),
    };
  }),
}))
"""

_BUTTON_SELECTOR = "button, input[type=button], input[type=submit], input[type=reset]"
_BUTTON_SCRIPT = """
(els) => els.map((el) => (
  el.innerText || el.getAttribute('value') || el.getAttribute('aria-label') || ''
).trim()).filter(Boolean)
"""


def extract_a11y_issues(page: Page) -> list[str]:
    """ページ内の明白なアクセシビリティ問題を検出する。"""
    issues: list[str] = []
    try:
        missing_alt: int = page.eval_on_selector_all(
            "img",
            "(imgs) => imgs.filter(img => !img.getAttribute('alt')).length",
        )
        if missing_alt:
            issues.append(f"img[alt欠落]: {missing_alt}件")

        unlabeled: int = page.eval_on_selector_all(
            "input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]), "
            "select, textarea",
            """(els) => els.filter(el => {
              const id = el.getAttribute('id');
              if (id && document.querySelector('label[for="' + id + '"]')) return false;
              if (el.getAttribute('aria-label')) return false;
              if (el.getAttribute('aria-labelledby')) return false;
              return true;
            }).length""",
        )
        if unlabeled:
            issues.append(f"ラベルなし入力: {unlabeled}件")

        has_landmark: bool = page.eval_on_selector_all(
            "main, [role='main'], nav, [role='navigation'], header, footer",
            "(els) => els.length > 0",
        )
        if not has_landmark:
            issues.append("landmark role なし（main/nav/header/footer が0件）")
    except Exception as exc:
        logger.warning("A11y チェックに失敗しました: %s", exc)
    return issues
