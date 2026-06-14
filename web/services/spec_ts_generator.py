from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# タイトルベースのフィルター用定数（auto_run.py からも参照）
SMOKE_TITLES: frozenset[str] = frozenset(["画面表示スモーク"])
TRANSITION_TITLES: frozenset[str] = frozenset(["画面表示スモーク", "画面遷移"])
FORM_TITLES: frozenset[str] = frozenset(["画面表示スモーク", "フォーム入力", "必須入力"])


def generate_spec_ts(
    domain: str,
    candidates_path: Path,
    output_path: Path,
    filter_mode: str = "all",
    enable_strong_assertions: bool = False,
    enable_self_healing: bool = False,
    generate_page_object: bool = False,
) -> Path:
    """playwright_candidates.json から Playwright .spec.ts を生成する。

    filter_mode:
      "all"        全候補（manual-review は test.skip）
      "smoke"      画面表示スモークのみ
      "transition" スモーク + 遷移テスト
      "form"       スモーク + フォーム入力 + 必須入力

    enable_strong_assertions: True の場合、expected フィールドに基づく強化アサーションを追加。
    enable_self_healing: True の場合、locators フィールドから resilient ロケータを生成。
    """
    data: dict[str, Any] = {}
    try:
        data = json.loads(candidates_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    candidates: list[dict[str, Any]] = data.get("candidates", [])
    filtered = _apply_filter(candidates, filter_mode)

    lines = [
        "import { test, expect } from '@playwright/test';",
        "",
        f"// AutoRun generated spec — {domain}",
        f"// filter: {filter_mode}  candidates: {len(filtered)}/{len(candidates)}",
        "",
    ]

    for item in filtered:
        _append_test_block(lines, item, enable_strong_assertions, enable_self_healing)

    output_path.write_text("\n".join(lines), encoding="utf-8")
    if generate_page_object:
        base_name = output_path.name.removesuffix(".spec.ts")
        page_object_path = output_path.with_name(f"{base_name}.page.ts")
        _generate_page_object(domain, filtered, page_object_path)
    return output_path


def _append_test_block(
    lines: list[str],
    item: dict[str, Any],
    enable_strong_assertions: bool,
    enable_self_healing: bool,
) -> None:
    """単一候補の test ブロックを lines に追記する。"""
    title = _safe_str(item.get("title", "untitled"))
    test_id = _safe_str(item.get("id", ""))
    trace_id = _safe_str(item.get("trace_id", ""))
    steps: list[Any] = item.get("steps") or []
    locators: list[str] = item.get("locators") or []
    expected = _safe_str(item.get("expected", ""))
    automation_status = _safe_str(item.get("automation_status", ""))

    label = f"'{_esc(test_id)} {_esc(title)} [{_esc(trace_id)}]'"

    if automation_status == "manual-review":
        lines.append(f"test.skip({label}, async () => {{")
        lines.append("  // manual-review: skip in CI")
        lines.append("});")
    else:
        lines.append(f"test({label}, async ({{ page }}) => {{")
        url = _extract_url(steps)
        if url:
            lines.append(f"  await page.goto('{_esc(url)}');")
            lines.append("  await page.waitForLoadState('domcontentloaded');")
        for step in steps:
            if not str(step).startswith("page.goto("):
                lines.append(f"  // {_esc(str(step))}")
        if expected:
            lines.append(f"  // expected: {_esc(expected)}")
        if enable_self_healing and locators:
            locator_expr = _build_role_based_locator(
                locators,
                field_name=_safe_str(item.get("field_name", "")),
                aria_label=_safe_str(item.get("aria_label", "")),
                field_type=_safe_str(item.get("field_type", "text")),
            )
            lines.append(f"  const targetLocator = {locator_expr};")
            lines.append("  await expect(targetLocator).toBeVisible();")
        else:
            lines.append("  await expect(page.locator('body')).toBeVisible();")
        if enable_strong_assertions and expected:
            for assertion in _generate_strong_assertions(expected):
                lines.append(f"  {assertion}")
        lines.append("});")
    lines.append("")


def _generate_strong_assertions(expected: str) -> list[str]:
    """expected フィールドから強化アサーション文字列のリストを返す。"""
    assertions: list[str] = []
    if "エラー" in expected:
        assertions.append(_generate_validation_message_assertion(expected))
    url_like = re.search(r"(https?://[^\s]+|/[^\s]*)", expected)
    if url_like:
        assertions.append(_generate_url_assertion(url_like.group(1)))
    return assertions


def _build_resilient_locator(locators: list[str]) -> str:
    """複数ロケータ候補を Playwright の first() チェーンで表現。
    最も具体的な候補（data-testid, aria-label, type= など）を先頭に並べる。"""
    sorted_locs = _sort_locators_by_reliability(locators)
    combined = ", ".join(sorted_locs)
    return f"page.locator('{_esc(combined)}').first()"


def _build_role_based_locator(
    locators: list[str],
    field_name: str = "",
    aria_label: str = "",
    field_type: str = "text",
) -> str:
    """ラベルと入力種別を使い、保守しやすいロケータを優先生成する。"""
    label = aria_label or field_name
    if aria_label:
        return f"page.getByLabel('{_esc(aria_label)}')"

    role_by_type = {
        "select": "combobox",
        "textarea": "textbox",
        "checkbox": "checkbox",
        "radio": "radio",
        "submit": "button",
        "button": "button",
        "reset": "button",
    }
    role = role_by_type.get(field_type)
    if role:
        name_part = f", {{ name: '{_esc(label)}' }}" if label else ""
        return f"page.getByRole('{role}'{name_part})"
    if label:
        return f"page.getByLabel('{_esc(label)}')"
    return _build_resilient_locator(locators)


def _sort_locators_by_reliability(locators: list[str]) -> list[str]:
    """ロケータ候補を信頼度順にソートする。

    優先度:
      1. data-testid を含む
      2. aria-label を含む
      3. type= を含む
      4. # で始まる（ID セレクタ）
      5. その他
    """

    def _priority(loc: str) -> int:
        if "data-testid" in loc:
            return 0
        if "aria-label" in loc:
            return 1
        if "type=" in loc:
            return 2
        if loc.strip().startswith("#"):
            return 3
        return 4

    return sorted(locators, key=_priority)


def _generate_url_assertion(expected_url: str) -> str:
    """URL アサーション文字列を返す。"""
    return f"await expect(page).toHaveURL('{_esc(expected_url)}');"


def _generate_validation_message_assertion(error_text: str) -> str:
    """バリデーションメッセージ表示アサーション文字列を返す。"""
    _ = error_text  # 将来の拡張のため受け取る（現在は固定セレクタ）
    return (
        "await expect("
        'page.locator(\'[role="alert"], .error-message, [aria-live="polite"]\').first()'
        ").toBeVisible();"
    )


def _generate_form_submit_assertion(expected_url_fragment: str) -> str:
    """フォーム送信後の URL パターンアサーション文字列を返す。"""
    return f"await expect(page).toHaveURL(/{_esc(expected_url_fragment)}/);"


def compute_filter_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    """各フィルターモードでの件数を返す。"""
    return {
        "all": len(candidates),
        "smoke": sum(1 for c in candidates if c.get("title") in SMOKE_TITLES),
        "transition": sum(1 for c in candidates if c.get("title") in TRANSITION_TITLES),
        "form": sum(1 for c in candidates if c.get("title") in FORM_TITLES),
    }


def _apply_filter(candidates: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    if mode == "smoke":
        return [c for c in candidates if c.get("title") in SMOKE_TITLES]
    if mode == "transition":
        return [c for c in candidates if c.get("title") in TRANSITION_TITLES]
    if mode == "form":
        return [c for c in candidates if c.get("title") in FORM_TITLES]
    return candidates  # "all"


def _extract_url(steps: list[Any]) -> str:
    for step in steps:
        m = re.search(r"page\.goto\(['\"]([^'\"]+)['\"]\)", str(step))
        if m:
            return m.group(1)
    return ""


def _safe_str(value: object) -> str:
    return str(value) if value is not None else ""


def _esc(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _generate_page_object(
    domain: str,
    candidates: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """候補をURL単位でまとめたPlaywright Page Objectを生成する。"""
    url_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        steps: list[Any] = candidate.get("steps") or []
        url_groups[_extract_url(steps) or "unknown"].append(candidate)

    lines = [
        "import { Page } from '@playwright/test';",
        "",
        f"// Page Object generated by WebSpec2Doc - {domain}",
        "",
    ]
    for url, items in url_groups.items():
        lines.append(f"export class {_url_to_class_name(url)} {{")
        lines.append("  readonly page: Page;")
        lines.append("  constructor(page: Page) { this.page = page; }")
        lines.append("")
        if url != "unknown":
            lines.append(f"  async goto() {{ await this.page.goto('{_esc(url)}'); }}")
            lines.append("")

        seen_getters: set[str] = set()
        for candidate in items:
            for raw_locator in candidate.get("locators") or []:
                getter_name = _locator_to_getter_name(str(raw_locator))
                if getter_name and getter_name not in seen_getters:
                    seen_getters.add(getter_name)
                    locator = _raw_locator_to_playwright(str(raw_locator))
                    lines.append(f"  get {getter_name}() {{ return {locator}; }}")
        lines.append("}")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")


def _url_to_class_name(url: str) -> str:
    """URLパス末尾をPage Objectのクラス名に変換する。"""
    if url == "unknown":
        return "UnknownPage"
    path = urlparse(url).path.rstrip("/")
    segment = path.rsplit("/", 1)[-1] if path else "Index"
    words = re.split(r"[-_.]", segment)
    name = "".join(word.capitalize() for word in words if word) or "Index"
    return f"{name}Page"


def _locator_to_getter_name(raw_locator: str) -> str:
    """CSSセレクタからPage Object getter名を生成する。"""
    stripped = raw_locator.strip()
    id_match = re.match(r"^#(.+)$", stripped)
    if id_match:
        return f"{_camel(id_match.group(1))}Input"
    name_match = re.search(r'\[name=["\']([^"\']+)["\']', stripped)
    if name_match:
        return f"{_camel(name_match.group(1))}Input"
    test_id_match = re.search(r'data-testid=["\']([^"\']+)["\']', stripped)
    if test_id_match:
        return f"{_camel(test_id_match.group(1))}Button"
    return ""


def _camel(value: str) -> str:
    """snake-case / kebab-caseをcamelCaseへ変換する。"""
    parts = [part for part in re.split(r"[-_\s]+", value) if part]
    if not parts:
        return ""
    return parts[0].lower() + "".join(part.capitalize() for part in parts[1:])


def _raw_locator_to_playwright(raw_locator: str) -> str:
    """CSSセレクタをPage Object内のPlaywrightロケータ式へ変換する。"""
    aria_match = re.search(r'aria-label=["\']([^"\']+)["\']', raw_locator)
    if aria_match:
        return f"this.page.getByLabel('{_esc(aria_match.group(1))}')"
    test_id_match = re.search(r'data-testid=["\']([^"\']+)["\']', raw_locator)
    if test_id_match:
        return f"this.page.getByTestId('{_esc(test_id_match.group(1))}')"
    return f"this.page.locator('{_esc(raw_locator)}')"
