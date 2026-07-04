from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, cast

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from crawler.page_crawler import (
    EmbeddedFrame,
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


def extract_forms_including_frames(page: Page, base_url: str | None = None) -> list[FormData]:
    """メインフレームおよび同一オリジン iframe から FormData を収集する。

    base_url を指定すると同一オリジン iframe のみを対象にする。クロスオリジン
    iframe は Playwright の CDP 経由では例外を出さずに読めてしまうことが
    実測で確認できているが、対象サイト自身が配信する内容のみを仕様として
    扱う方針のため、オリジン比較で明示的に除外する（§8 参照）。
    base_url 省略時は後方互換のため全 frame を試行する（既存呼び出し元向け）。
    重複 action を除去して返す。
    """
    all_forms: list[FormData] = extract_forms(page)
    seen_actions: set[str] = {f.action for f in all_forms}

    frames = _same_origin_child_frames(page, base_url) if base_url else _iter_child_frames(page)
    for frame in frames:
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


def _iter_child_frames(page: Page) -> list[Any]:
    """メインフレーム以外の子 iframe（page.frames）を返す。"""
    return [frame for frame in page.frames if frame != page.main_frame]


def _is_same_origin_frame(frame_url: str, base_url: str) -> bool:
    """iframe が対象サイトと同一オリジンか判定する。

    about:blank / about:srcdoc は親ページと同一のセキュリティコンテキストを
    継承するため同一オリジン扱いとする。
    """
    if not frame_url or frame_url.startswith("about:"):
        return True
    return is_internal_link(base_url, frame_url)


def _same_origin_child_frames(page: Page, base_url: str) -> list[Any]:
    """メインフレーム以外の同一オリジン iframe のみを返す（クロスオリジンは除外）。

    Playwright は CDP 経由でクロスオリジン iframe の内容も技術的には読める
    （frame.evaluate / eval_on_selector_all は例外を出さない）。本関数は
    「対象サイト自身が配信する内容のみを仕様として扱う」というポリシー上の
    境界であり、技術的な読み取り可否の制約ではない。
    """
    return [
        frame
        for frame in _iter_child_frames(page)
        if _is_same_origin_frame(frame.url or "", base_url)
    ]


def extract_links_all_scopes(page: Page, base_url: str) -> list[str]:
    """メインフレームおよび同一オリジン iframe からリンクを収集する（重複除去）。

    リンクのセレクタマッチング自体は open shadow root を貫通するため
    （Playwright のセレクタエンジンによる。§8 参照）、shadow 内のリンクは
    メインフレーム分ですでに収集済みである。ここでは iframe 境界のみを跨ぐ。
    """
    all_links: list[str] = list(extract_internal_links(page, base_url))
    seen: set[str] = set(all_links)
    for frame in _same_origin_child_frames(page, base_url):
        try:
            hrefs = cast(
                list[str],
                frame.eval_on_selector_all("a[href]", "(els) => els.map((a) => a.href)"),
            )
        except Exception as exc:
            logger.warning("iframe のリンク抽出をスキップしました: %s", exc)
            continue
        for href in hrefs:
            if not href or not is_internal_link(base_url, href):
                continue
            normalized = normalize_url(href)
            if normalized not in seen:
                seen.add(normalized)
                all_links.append(normalized)
    return all_links


def extract_headings_all_scopes(page: Page, base_url: str) -> list[str]:
    """メインフレームおよび同一オリジン iframe から見出しを収集する。"""
    all_headings: list[str] = list(extract_headings(page))
    for frame in _same_origin_child_frames(page, base_url):
        try:
            values = cast(
                list[str],
                frame.eval_on_selector_all(
                    "h1, h2, h3",
                    "(els) => els.map((el) => (el.innerText || '').trim()).filter(Boolean)",
                ),
            )
        except Exception as exc:
            logger.warning("iframe の見出し抽出をスキップしました: %s", exc)
            continue
        all_headings.extend(values)
    return all_headings


def extract_buttons_all_scopes(page: Page, base_url: str) -> list[str]:
    """メインフレームおよび同一オリジン iframe からボタン文言を収集する（重複除去）。"""
    all_buttons: list[str] = list(extract_buttons(page))
    seen: set[str] = set(all_buttons)
    for frame in _same_origin_child_frames(page, base_url):
        try:
            values = cast(list[str], frame.eval_on_selector_all(_BUTTON_SELECTOR, _BUTTON_SCRIPT))
        except Exception as exc:
            logger.warning("iframe のボタン抽出をスキップしました: %s", exc)
            continue
        for value in values:
            if value and value not in seen:
                seen.add(value)
                all_buttons.append(value)
    return all_buttons


_CLOSED_SHADOW_SCAN_JS = """
() => {
  const hosts = new Set();
  const scan = (root) => {
    root.querySelectorAll('*').forEach((el) => {
      if (el.shadowRoot) {
        scan(el.shadowRoot);
      } else if (
        el.tagName &&
        el.tagName.includes('-') &&
        el.childElementCount === 0 &&
        !(el.textContent || '').trim()
      ) {
        hosts.add(el.tagName.toLowerCase());
      }
    });
  };
  scan(document);
  return Array.from(hosts);
}
"""


def _detect_closed_shadow_hosts(page: Page) -> list[str]:
    """closed shadow root を持つ可能性のあるカスタム要素のタグ名を検出する。

    closed shadow root は外部から中身を一切参照できないため、正確な判定は
    不可能。ここでは「カスタム要素タグ・光 DOM 上の子要素なし・テキストなし」
    というヒューリスティックで近似する（過検出よりも取りこぼしを許容し、
    呼び出し側では常に「の可能性」として記録し断定しない）。
    """
    try:
        raw = page.evaluate(_CLOSED_SHADOW_SCAN_JS)
    except Exception as exc:
        logger.debug("closed shadow root の検出に失敗しました: %s", exc)
        return []
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def collect_embedded_frames(page: Page, base_url: str) -> list[EmbeddedFrame]:
    """ページ内の iframe・closed shadow root の可能性がある要素を記録する。

    iframe は同一オリジンなら readable=True、クロスオリジンなら readable=False
    （クロスオリジンのため未読）とする。オリジン判定は URL 比較で行う
    （frame.evaluate はクロスオリジンでも例外を出さず成功するため使えない。
    §8 参照）。closed shadow root は常に readable=False とする。
    """
    embedded: list[EmbeddedFrame] = []
    for frame in _iter_child_frames(page):
        src = frame.url or ""
        if _is_same_origin_frame(src, base_url):
            embedded.append(EmbeddedFrame(src=src, readable=True))
        else:
            embedded.append(EmbeddedFrame(src=src, readable=False, note="クロスオリジンのため未読"))
    for tag_name in _detect_closed_shadow_hosts(page):
        embedded.append(
            EmbeddedFrame(
                src=f"shadow:{tag_name}",
                readable=False,
                note="closed shadow root の可能性（検出したが読めない）",
            )
        )
    return embedded


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
(forms) => {
  // フォーム内に Web Components（open shadow root）でラップされた入力欄が
  // あっても、native querySelectorAll はシャドウ境界を貫通できない。
  // collectFields は open shadow root を再帰的に辿って入力欄を集める
  // （Playwright 自体のセレクタエンジンは trailing のトップレベル一致で
  // shadow を貫通するが、評価済み要素上での native 呼び出しは貫通しない）。
  const collectFields = (root) => {
    let fields = Array.from(root.querySelectorAll('input, select, textarea'));
    root.querySelectorAll('*').forEach((el) => {
      if (el.shadowRoot) {
        fields = fields.concat(collectFields(el.shadowRoot));
      }
    });
    return fields;
  };
  return forms.map((form) => ({
  action: form.getAttribute('action') || '',
  method: (form.getAttribute('method') || 'get').toLowerCase(),
  fields: collectFields(form).map((field) => {
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
  }));
}
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
