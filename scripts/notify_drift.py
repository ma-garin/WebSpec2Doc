#!/usr/bin/env python3
"""drift_summary.json の実数を使ってSlackへベストエフォート通知する。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.services.notifier import (  # noqa: E402
    NOTIFIER_SLACK,
    DriftNotification,
    NotifierConfig,
    send_drift_notification,
)


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="WebSpec2Doc drift summary Slack notifier")
    parser.add_argument("summary", type=Path, help="drift_summary.json path")
    args = parser.parse_args(argv)
    env = environ if environ is not None else os.environ
    try:
        summary = json.loads(args.summary.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("警告: ドリフトサマリを読み込めないため通知をスキップします。", file=sys.stderr)
        return 0
    if not isinstance(summary, dict):
        print("警告: ドリフトサマリの形式が不正なため通知をスキップします。", file=sys.stderr)
        return 0
    if bool(summary.get("first_run")) or not bool(summary.get("has_changes")):
        print("差分なし、または初回実行のため通知は不要です。")
        return 0
    webhook_url = str(env.get("SLACK_WEBHOOK_URL", "")).strip()
    if not webhook_url:
        print("警告: Slack Webhook未設定のため通知をスキップします。", file=sys.stderr)
        return 0
    counts = summary.get("counts")
    if not isinstance(counts, dict):
        counts = {}

    def count(name: str) -> int:
        value = counts.get(name, 0)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0

    notification = DriftNotification(
        site_url=str(summary.get("site_url", "")),
        added_pages=count("added_pages"),
        removed_pages=count("removed_pages"),
        field_changes=count("field_changes"),
        api_changes=count("api_changes"),
        report_url=str(env.get("WEBSPEC2DOC_NOTIFY_REPORT_URL") or summary.get("report_url", "")),
    )
    config = NotifierConfig(notifier_type=NOTIFIER_SLACK, endpoint=webhook_url)
    if not send_drift_notification(config, notification):
        print("警告: Slack通知の送信に失敗しました。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
