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
) -> Path:
    """playwright_candidates.json から Playwright .spec.ts を生成する。

    filter_mode:
      "all"        全候補（manual-review は test.skip）
      "smoke"      画面表示スモークのみ
      "transition" スモーク + 遷移テスト
      "form"       スモーク + フォーム入力 + 必須入力
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
        title = _safe_str(item.get("title", "untitled"))
        test_id = _safe_str(item.get("id", ""))
        trace_id = _safe_str(item.get("trace_id", ""))
        steps: list[str] = item.get("steps") or []
        expected = _safe_str(item.get("expected", ""))
        automation_status = _safe_str(item.get("automation_status", ""))

        if automation_status == "manual-review":
            lines.append(
                f"test.skip('{_esc(test_id)} {_esc(title)} [{_esc(trace_id)}]', async () => {{"
            )
            lines.append("  // manual-review: skip in CI")
            lines.append("});")
        else:
            lines.append(
                f"test('{_esc(test_id)} {_esc(title)} [{_esc(trace_id)}]', async ({{ page }}) => {{"
            )
            url = _extract_url(steps)
            if url:
                lines.append(f"  await page.goto('{_esc(url)}');")
                lines.append("  await page.waitForLoadState('domcontentloaded');")
            for step in steps:
                if not step.startswith("page.goto("):
                    lines.append(f"  // {_esc(step)}")
            if expected:
                lines.append(f"  // expected: {_esc(expected)}")
            lines.append("  await expect(page.locator('body')).toBeVisible();")
            lines.append("});")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


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
