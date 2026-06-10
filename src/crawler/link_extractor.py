from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, cast

from playwright.sync_api import Page

from crawler.page_crawler import FieldData, FormData, is_internal_link, normalize_url

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
    return hashlib.sha1(key.encode()).hexdigest()[:8]


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


def _to_form_data(raw_form: dict[str, Any]) -> FormData:
    raw_fields = cast(list[dict[str, Any]], raw_form.get("fields", []))
    fields = tuple(_to_field_data(raw_field) for raw_field in raw_fields)
    return FormData(
        action=str(raw_form.get("action") or EMPTY_TEXT),
        method=str(raw_form.get("method") or DEFAULT_FORM_METHOD).lower(),
        fields=fields,
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
      options: options,
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
