"""web/services/scheduler.py のユニットテスト。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from web.services.scheduler import (
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
    with patch("web.services.scheduler._run_crawl", side_effect=lambda url, crawl_output=None: fired.append(url)):
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
