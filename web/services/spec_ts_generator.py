from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

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
            locator_expr = _build_resilient_locator(locators)
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
