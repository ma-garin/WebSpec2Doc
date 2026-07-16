"""web/services/scheduler.py のユニットテスト。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from web.services.admin_audit import read_admin_audit
from web.services.retention import save_retention_policy
from web.services.scheduler import (
    CrawlRunResult,
    _calc_next_run_at,
    _check_and_run_due,
    _maybe_run,
    _persist_timestamps,
)


def _write_schedule(domain_dir: Path, config: dict) -> Path:
    domain_dir.mkdir(parents=True, exist_ok=True)
    p = domain_dir / "schedule.json"
    p.write_text(json.dumps(config), encoding="utf-8")
    return p


# ─────────────── _calc_next_run_at ───────────────


def test_calc_next_run_at_daily() -> None:
    base = datetime(2026, 6, 10, 12, 0, 0)
    result = _calc_next_run_at("daily", base)
    assert result == "2026-06-11T12:00:00"


def test_calc_next_run_at_weekly() -> None:
    base = datetime(2026, 6, 10, 0, 0, 0)
    result = _calc_next_run_at("weekly", base)
    assert result == "2026-06-17T00:00:00"


def test_calc_next_run_at_monthly() -> None:
    base = datetime(2026, 6, 10, 0, 0, 0)
    result = _calc_next_run_at("monthly", base)
    assert result == "2026-07-10T00:00:00"


def test_calc_next_run_at_disabled_returns_none() -> None:
    base = datetime(2026, 6, 10, 0, 0, 0)
    assert _calc_next_run_at("disabled", base) is None


def test_calc_next_run_at_applies_timezone_weekdays_and_window() -> None:
    base = datetime(2026, 7, 17, 3, 0, tzinfo=ZoneInfo("Asia/Tokyo"))  # Friday
    result = _calc_next_run_at(
        "daily",
        base,
        timezone_name="Asia/Tokyo",
        weekdays=(0, 1, 2, 3, 4),
        window_start="02:00",
        window_end="05:00",
    )
    assert result == "2026-07-20T02:00:00+09:00"


def test_calc_next_run_at_moves_before_window_to_window_start() -> None:
    base = datetime(2026, 7, 13, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    result = _calc_next_run_at(
        "daily",
        base,
        timezone_name="Asia/Tokyo",
        window_start="02:00",
        window_end="05:00",
    )
    assert result == "2026-07-14T02:00:00+09:00"


def test_calc_next_run_at_supports_overnight_window() -> None:
    base = datetime(2026, 7, 13, 0, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    result = _calc_next_run_at(
        "daily",
        base,
        timezone_name="Asia/Tokyo",
        weekdays=(0,),
        window_start="22:00",
        window_end="02:00",
    )
    # Tuesday 00:00 belongs to the window that started on Monday 22:00.
    assert result == "2026-07-14T00:00:00+09:00"


# ─────────────── _persist_timestamps ───────────────


def test_persist_timestamps_updates_file(tmp_path: Path) -> None:
    schedule_path = tmp_path / "schedule.json"
    config = {
        "domain": "example.com",
        "interval": "daily",
        "last_run_at": None,
        "next_run_at": None,
    }
    schedule_path.write_text(json.dumps(config), encoding="utf-8")

    ran_at = datetime(2026, 6, 10, 9, 0, 0)
    _persist_timestamps(schedule_path, config, ran_at)

    saved = json.loads(schedule_path.read_text(encoding="utf-8"))
    assert saved["last_run_at"] == "2026-06-10T09:00:00"
    assert saved["next_run_at"] == "2026-06-11T09:00:00"


def test_persist_timestamps_atomic_write(tmp_path: Path) -> None:
    """tmp ファイル経由の原子的書き込みで .tmp ファイルが残らない。"""
    schedule_path = tmp_path / "schedule.json"
    config = {
        "domain": "example.com",
        "interval": "weekly",
        "last_run_at": None,
        "next_run_at": None,
    }
    schedule_path.write_text(json.dumps(config), encoding="utf-8")
    _persist_timestamps(schedule_path, config, datetime.now())
    assert not (tmp_path / "schedule.tmp").exists()


# ─────────────── _maybe_run ───────────────


def test_maybe_run_skips_disabled(tmp_path: Path) -> None:
    p = _write_schedule(
        tmp_path / "example.com",
        {
            "domain": "example.com",
            "interval": "disabled",
            "next_run_at": "2020-01-01T00:00:00",
            "site_url": "https://example.com",
        },
    )
    with patch("web.services.scheduler._run_crawl") as mock_crawl:
        _maybe_run("example.com", p, datetime.now())
    mock_crawl.assert_not_called()


def test_maybe_run_skips_future_next_run(tmp_path: Path) -> None:
    future = (datetime.now() + timedelta(days=1)).isoformat(timespec="seconds")
    p = _write_schedule(
        tmp_path / "example.com",
        {
            "domain": "example.com",
            "interval": "daily",
            "next_run_at": future,
            "site_url": "https://example.com",
        },
    )
    with patch("web.services.scheduler._run_crawl") as mock_crawl:
        _maybe_run("example.com", p, datetime.now())
    mock_crawl.assert_not_called()


def test_maybe_run_fires_when_due(tmp_path: Path) -> None:
    past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
    p = _write_schedule(
        tmp_path / "example.com",
        {
            "domain": "example.com",
            "interval": "daily",
            "next_run_at": past,
            "site_url": "https://example.com",
            "last_run_at": None,
        },
    )
    with patch("web.services.scheduler._run_crawl") as mock_crawl:
        _maybe_run("example.com", p, datetime.now())
    mock_crawl.assert_called_once_with("https://example.com", None)


def test_maybe_run_updates_timestamps_when_due(tmp_path: Path) -> None:
    past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
    p = _write_schedule(
        tmp_path / "example.com",
        {
            "domain": "example.com",
            "interval": "daily",
            "next_run_at": past,
            "site_url": "https://example.com",
            "last_run_at": None,
        },
    )
    with patch("web.services.scheduler._run_crawl"):
        _maybe_run("example.com", p, datetime.now())

    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["last_run_at"] is not None
    assert saved["next_run_at"] is not None
    assert saved["next_run_at"] > saved["last_run_at"]


def test_maybe_run_skips_missing_site_url(tmp_path: Path) -> None:
    past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
    p = _write_schedule(
        tmp_path / "example.com",
        {"domain": "example.com", "interval": "daily", "next_run_at": past, "site_url": ""},
    )
    with patch("web.services.scheduler._run_crawl") as mock_crawl:
        _maybe_run("example.com", p, datetime.now())
    mock_crawl.assert_not_called()


def test_maybe_run_handles_invalid_json(tmp_path: Path) -> None:
    p = tmp_path / "example.com" / "schedule.json"
    p.parent.mkdir(parents=True)
    p.write_text("not json", encoding="utf-8")
    # 例外なく終了すること
    _maybe_run("example.com", p, datetime.now())


def test_maybe_run_accepts_legacy_naive_next_run_with_aware_now(tmp_path: Path) -> None:
    p = _write_schedule(
        tmp_path / "example.com",
        {
            "domain": "example.com",
            "interval": "daily",
            "timezone": "Asia/Tokyo",
            "next_run_at": "2026-07-16T02:00:00",
            "site_url": "https://example.com",
            "retry_max": 0,
        },
    )
    with patch(
        "web.services.scheduler._run_crawl", return_value=CrawlRunResult(True)
    ) as mock_crawl:
        _maybe_run(
            "example.com",
            p,
            datetime(2026, 7, 16, 3, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        )
    mock_crawl.assert_called_once()


def test_maybe_run_reschedules_without_running_outside_window(tmp_path: Path) -> None:
    p = _write_schedule(
        tmp_path / "example.com",
        {
            "domain": "example.com",
            "interval": "daily",
            "timezone": "Asia/Tokyo",
            "weekdays": [],
            "window_start": "02:00",
            "window_end": "05:00",
            "next_run_at": "2026-07-16T02:00:00+09:00",
            "site_url": "https://example.com",
            "last_run_at": None,
        },
    )
    with patch("web.services.scheduler._run_crawl") as mock_crawl:
        _maybe_run(
            "example.com",
            p,
            datetime(2026, 7, 16, 6, 0, tzinfo=ZoneInfo("Asia/Tokyo")),
        )
    mock_crawl.assert_not_called()
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["last_run_at"] is None
    assert saved["next_run_at"] == "2026-07-17T02:00:00+09:00"


def test_maybe_run_retries_with_backoff_and_records_success(tmp_path: Path) -> None:
    p = _write_schedule(
        tmp_path / "example.com",
        {
            "domain": "example.com",
            "interval": "daily",
            "next_run_at": "2026-07-15T00:00:00",
            "site_url": "https://example.com",
            "retry_max": 2,
            "retry_backoff_seconds": 10,
        },
    )
    results = (
        CrawlRunResult(False, "temporary-1", 1.0),
        CrawlRunResult(False, "temporary-2", 2.0),
        CrawlRunResult(True, "", 3.0),
    )
    sleeps: list[float] = []
    with patch("web.services.scheduler._run_crawl", side_effect=results) as mock_crawl:
        _maybe_run(
            "example.com",
            p,
            datetime(2026, 7, 16, 0, 0),
            sleeper=sleeps.append,
        )

    assert mock_crawl.call_count == 3
    assert sleeps == [10, 20]
    records = [
        json.loads(line)
        for line in (p.parent / "schedule_history.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    assert records[0]["status"] == "complete"
    assert records[0]["attempts"] == 3
    assert records[0]["duration_sec"] == 6.0
    assert records[0]["error"] == ""


def test_maybe_run_records_final_failure_without_secret_output(tmp_path: Path) -> None:
    p = _write_schedule(
        tmp_path / "example.com",
        {
            "domain": "example.com",
            "interval": "daily",
            "next_run_at": "2026-07-15T00:00:00",
            "site_url": "https://example.com",
            "retry_max": 1,
            "retry_backoff_seconds": 1,
        },
    )
    with patch(
        "web.services.scheduler._run_crawl",
        side_effect=(
            CrawlRunResult(False, "first failure", 1.5),
            CrawlRunResult(False, "final\nfailure", 2.5),
        ),
    ):
        _maybe_run(
            "example.com",
            p,
            datetime(2026, 7, 16, 0, 0),
            sleeper=lambda _seconds: None,
        )

    record = json.loads(
        (p.parent / "schedule_history.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    assert record["status"] == "failed"
    assert record["attempts"] == 2
    assert record["duration_sec"] == 4.0
    assert record["error"] == "final failure"


def test_maybe_run_sends_notification_after_final_failure(tmp_path: Path) -> None:
    p = _write_schedule(
        tmp_path / "example.com",
        {
            "domain": "example.com",
            "interval": "daily",
            "next_run_at": "2026-07-15T00:00:00",
            "site_url": "https://example.com",
            "retry_max": 0,
            "notify_type": "teams",
            "notify_endpoint": "https://prod.example.logic.azure.com/workflows/example",
            "notify_template": "",
        },
    )
    with (
        patch(
            "web.services.scheduler._run_crawl",
            return_value=CrawlRunResult(False, "timeout", 2.0),
        ),
        patch("web.services.notifier.send_crawl_failure_notification") as mock_notify,
    ):
        _maybe_run("example.com", p, datetime(2026, 7, 16, 0, 0))

    mock_notify.assert_called_once()
    notifier_config, notification = mock_notify.call_args.args
    assert notifier_config.notifier_type == "teams"
    assert notification.site_url == "https://example.com"
    assert notification.attempts == 1
    assert notification.error == "timeout"


def test_maybe_run_sends_drift_summary_after_success(tmp_path: Path) -> None:
    domain_dir = tmp_path / "example.com"
    p = _write_schedule(
        domain_dir,
        {
            "domain": "example.com",
            "interval": "daily",
            "next_run_at": "2026-07-15T00:00:00",
            "site_url": "https://example.com",
            "retry_max": 0,
            "notify_type": "teams",
            "notify_endpoint": "https://prod.example.logic.azure.com/workflows/example",
            "diff_summary_limit": 2,
        },
    )
    (domain_dir / "diff_summary.json").write_text(
        json.dumps(
            {
                "added_pages": [
                    {"title": "A", "url": "/a"},
                    {"title": "B", "url": "/b"},
                    {"title": "C", "url": "/c"},
                ],
                "removed_pages": [{"title": "Old", "url": "/old"}],
                "field_changes": 3,
                "api_changes": 1,
            }
        ),
        encoding="utf-8",
    )
    with (
        patch("web.services.scheduler._run_crawl", return_value=CrawlRunResult(True, "", 1.0)),
        patch("web.services.notifier.send_drift_notification") as mock_notify,
    ):
        _maybe_run("example.com", p, datetime(2026, 7, 16, 0, 0))

    mock_notify.assert_called_once()
    _config, notification = mock_notify.call_args.args
    assert notification.added_pages == 3
    assert notification.added_page_names == ("A", "B")
    assert notification.removed_page_names == ("Old",)
    assert notification.field_changes == 3
    assert notification.api_changes == 1


def test_maybe_run_prunes_expired_snapshots_only_after_success(tmp_path: Path) -> None:
    domain_dir = tmp_path / "output" / "example.com"
    p = _write_schedule(
        domain_dir,
        {
            "domain": "example.com",
            "interval": "daily",
            "next_run_at": "2026-07-15T00:00:00",
            "site_url": "https://example.com",
            "retry_max": 0,
        },
    )
    snapshots = domain_dir / "snapshots"
    snapshots.mkdir()
    for name in (
        "20260715-000000.json",
        "20260716-000000.json",
        "20260717-000000.json",
    ):
        (snapshots / name).write_text("[]", encoding="utf-8")
    retention_path = tmp_path / "instance" / "retention.json"
    save_retention_policy(
        retention_path,
        {"mode": "generations", "generations": 2},
    )

    with patch(
        "web.services.scheduler._run_crawl",
        return_value=CrawlRunResult(True, "", 1.0),
    ):
        _maybe_run(
            "example.com",
            p,
            datetime(2026, 7, 16, 0, 0),
            retention_path=retention_path,
        )

    assert sorted(path.name for path in snapshots.glob("*.json")) == [
        "20260716-000000.json",
        "20260717-000000.json",
    ]
    audit = read_admin_audit(tmp_path / "instance" / "admin_audit.jsonl")
    assert len(audit) == 1
    assert audit[0].action == "retention.snapshots_pruned"
    assert audit[0].detail["deleted_count"] == 1
    assert audit[0].detail["deleted_paths"] == ["example.com/snapshots/20260715-000000.json"]


# ─────────────── _check_and_run_due ───────────────


def test_check_and_run_due_skips_nonexistent_dir(tmp_path: Path) -> None:
    nonexistent = tmp_path / "does_not_exist"
    # 例外なく終了すること
    _check_and_run_due(nonexistent)


def test_check_and_run_due_runs_multiple_domains(tmp_path: Path) -> None:
    past = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
    for domain in ("site-a.com", "site-b.com"):
        _write_schedule(
            tmp_path / domain,
            {
                "domain": domain,
                "interval": "daily",
                "next_run_at": past,
                "site_url": f"https://{domain}",
                "last_run_at": None,
            },
        )

    fired: list[str] = []
    with patch(
        "web.services.scheduler._run_crawl",
        side_effect=lambda url, crawl_output=None: fired.append(url),
    ):
        _check_and_run_due(tmp_path)

    assert len(fired) == 2
    assert "https://site-a.com" in fired
    assert "https://site-b.com" in fired


# ─────────────── start_scheduler / stop_scheduler ───────────────


def test_start_scheduler_does_not_crash() -> None:
    from web.services import scheduler as sched_mod

    sched_mod.stop_scheduler()

    with patch.object(sched_mod, "_check_and_run_due"):
        sched_mod.start_scheduler()
        import time

        time.sleep(0.05)
        sched_mod.stop_scheduler()


def test_start_scheduler_idempotent() -> None:
    """二重起動しても例外が発生しない。"""
    from web.services import scheduler as sched_mod

    sched_mod.stop_scheduler()
    with patch.object(sched_mod, "_check_and_run_due"):
        sched_mod.start_scheduler()
        sched_mod.start_scheduler()  # 二回目は無視される
        sched_mod.stop_scheduler()
