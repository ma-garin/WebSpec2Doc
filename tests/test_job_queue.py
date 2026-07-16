from __future__ import annotations

import json
from pathlib import Path

from web.services.job_queue import CrawlJob, _try_slack_notify


def test_web_job_notification_uses_drift_summary_counts(tmp_path: Path, monkeypatch) -> None:
    domain_dir = tmp_path / "example.com"
    domain_dir.mkdir()
    (domain_dir / "drift_summary.json").write_text(
        json.dumps(
            {
                "version": 1,
                "site_url": "https://example.com",
                "first_run": False,
                "has_changes": True,
                "counts": {
                    "added_pages": 2,
                    "removed_pages": 1,
                    "field_changes": 3,
                    "api_changes": 4,
                },
                "report_url": "output/example.com/diff_report.html",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.invalid/private-token")
    monkeypatch.setattr("dotenv.dotenv_values", lambda *_args: {})
    captured = []
    monkeypatch.setattr(
        "web.services.notifier.send_drift_notification",
        lambda _config, notification: captured.append(notification) or True,
    )
    job = CrawlJob(
        job_id="job-1",
        domain="example.com",
        site_url="https://example.com",
        status="completed",
        started_at="2026-07-17T00:00:00",
    )

    _try_slack_notify(job, tmp_path)

    assert len(captured) == 1
    assert captured[0].added_pages == 2
    assert captured[0].removed_pages == 1
    assert captured[0].field_changes == 3
    assert captured[0].api_changes == 4


def test_web_job_notification_skips_unchanged_summary(tmp_path: Path, monkeypatch) -> None:
    domain_dir = tmp_path / "example.com"
    domain_dir.mkdir()
    (domain_dir / "drift_summary.json").write_text(
        json.dumps(
            {
                "version": 1,
                "site_url": "https://example.com",
                "first_run": False,
                "has_changes": False,
                "counts": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.invalid/private-token")
    monkeypatch.setattr("dotenv.dotenv_values", lambda *_args: {})
    calls = []
    monkeypatch.setattr(
        "web.services.notifier.send_drift_notification",
        lambda *_args: calls.append(True) or True,
    )
    job = CrawlJob(
        job_id="job-1",
        domain="example.com",
        site_url="https://example.com",
        status="completed",
        started_at="2026-07-17T00:00:00",
    )

    _try_slack_notify(job, tmp_path)

    assert calls == []
