from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def generate_spec_ts(domain: str, candidates_path: Path, output_path: Path) -> Path:
    """playwright_candidates.json から Playwright .spec.ts を生成する。"""
    data: dict[str, Any] = {}
    try:
        data = json.loads(candidates_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    candidates: list[dict[str, Any]] = data.get("candidates", [])
    lines = [
        "import { test, expect } from '@playwright/test';",
        "",
        f"// AutoRun generated spec — {domain}",
        f"// candidates: {len(candidates)}",
        "",
    ]

    for item in candidates:
        title = _safe_str(item.get("title", "untitled"))
        test_id = _safe_str(item.get("id", ""))
        trace_id = _safe_str(item.get("trace_id", ""))
        steps: list[str] = item.get("steps") or []
        expected = _safe_str(item.get("expected", ""))
        automation_status = _safe_str(item.get("automation_status", ""))

        if automation_status == "manual-review":
            lines.append(f"test.skip('{_esc(test_id)} {_esc(title)} [{_esc(trace_id)}]', async () => {{")
            lines.append("  // manual-review: skip in CI")
            lines.append("});")
        else:
            lines.append(f"test('{_esc(test_id)} {_esc(title)} [{_esc(trace_id)}]', async ({{ page }}) => {{")
            url = _extract_url(steps)
            if url:
                lines.append(f"  await page.goto('{_esc(url)}');")
            for step in steps:
                lines.append(f"  // {_esc(step)}")
            if expected:
                lines.append(f"  // expected: {_esc(expected)}")
            lines.append("  await expect(page.locator('body')).toBeVisible();")
            lines.append("});")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _extract_url(steps: list[Any]) -> str:
    for step in steps:
        m = re.search(r"page\.goto\(['\"]([^'\"]+)['\"]\)", str(step))
        if m:
            return m.group(1)
    return ""


def _safe_str(value: object) -> str:
    return str(value) if value is not None else ""


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")
