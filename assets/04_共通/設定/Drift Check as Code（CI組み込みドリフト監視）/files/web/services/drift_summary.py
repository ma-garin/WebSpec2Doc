"""通知側で共有する版付きdrift_summary.jsonの安全な読取。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_drift_summary(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("version") != 1:
        return None
    return value


def should_notify_drift(summary: dict[str, Any]) -> bool:
    return not bool(summary.get("first_run")) and bool(summary.get("has_changes"))


def drift_count(summary: dict[str, Any], name: str) -> int:
    counts = summary.get("counts")
    if not isinstance(counts, dict):
        return 0
    value = counts.get(name, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0
