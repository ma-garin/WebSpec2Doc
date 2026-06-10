"""プロジェクト全体で共有する TypedDict 定義。"""

from __future__ import annotations

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict  # type: ignore[assignment]


class ScheduleConfig(TypedDict, total=False):
    """schedule.json のスキーマ定義。"""

    domain: str
    interval: str  # "daily" | "weekly" | "monthly" | "disabled"
    notify_type: str  # "slack" | "email" | "webhook" | "none"
    notify_endpoint: str
    severity_filter: str  # "breaking" | "warning" | "all"
    site_url: str
    last_run_at: str | None
    next_run_at: str | None
    created_at: str
