"""プロジェクト全体で共有する TypedDict 定義。"""

from __future__ import annotations

from typing import TypedDict


class ScheduleConfig(TypedDict, total=False):
    """schedule.json のスキーマ定義。"""

    domain: str
    interval: str  # "daily" | "weekly" | "monthly" | "disabled"
    timezone: str
    weekdays: list[int]
    window_start: str
    window_end: str
    retry_max: int
    retry_backoff_seconds: int
    notify_type: str  # "slack" | "teams" | "email" | "webhook" | "none"
    notify_endpoint: str
    notify_template: str
    diff_summary_limit: int
    severity_filter: str  # "breaking" | "warning" | "all"
    site_url: str
    last_run_at: str | None
    next_run_at: str | None
    created_at: str
