from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from web.services.retention import (
    RetentionPolicy,
    collect_storage_usage,
    load_retention_policy,
    prune_snapshots,
    save_retention_policy,
)


def _snapshot(site_dir: Path, name: str) -> Path:
    path = site_dir / "snapshots" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]", encoding="utf-8")
    return path


def test_missing_policy_is_unlimited_and_deletes_nothing(tmp_path: Path) -> None:
    policy = load_retention_policy(tmp_path / "instance" / "retention.json")
    snapshot = _snapshot(tmp_path / "output" / "example.com", "20260717-000000.json")

    result = prune_snapshots(tmp_path / "output", policy)

    assert policy.mode == "unlimited"
    assert policy.generations is None
    assert policy.days is None
    assert result.deleted_count == 0
    assert snapshot.is_file()


def test_malformed_policy_falls_back_to_safe_unlimited_mode(tmp_path: Path) -> None:
    path = tmp_path / "instance" / "retention.json"
    path.parent.mkdir()
    path.write_text(
        '{"mode":"generations","generations":"not-a-number"}',
        encoding="utf-8",
    )

    policy = load_retention_policy(path)

    assert policy == RetentionPolicy()


def test_generation_policy_keeps_newest_snapshots_per_site(tmp_path: Path) -> None:
    site = tmp_path / "output" / "example.com"
    oldest = _snapshot(site, "20260715-000000.json")
    middle = _snapshot(site, "20260716-000000.json")
    newest = _snapshot(site, "20260717-000000.json")

    result = prune_snapshots(
        tmp_path / "output", RetentionPolicy(mode="generations", generations=2)
    )

    assert result.deleted_count == 1
    assert result.deleted_bytes == 2
    assert result.deleted_paths == ("example.com/snapshots/20260715-000000.json",)
    assert not oldest.exists()
    assert middle.is_file()
    assert newest.is_file()


def test_days_policy_deletes_only_snapshots_older_than_cutoff(tmp_path: Path) -> None:
    site = tmp_path / "output" / "example.com"
    expired = _snapshot(site, "20260701-000000.json")
    retained = _snapshot(site, "20260712-000000.json")
    latest = _snapshot(site, "20260717-000000.json")

    result = prune_snapshots(
        tmp_path / "output",
        RetentionPolicy(mode="days", days=7),
        now=datetime(2026, 7, 17, tzinfo=UTC),
    )

    assert result.deleted_paths == ("example.com/snapshots/20260701-000000.json",)
    assert not expired.exists()
    assert retained.is_file()
    assert latest.is_file()


def test_save_policy_validates_and_roundtrips_generation_limit(tmp_path: Path) -> None:
    path = tmp_path / "instance" / "retention.json"

    saved = save_retention_policy(
        path,
        {"mode": "generations", "generations": 30},
        updated_by="admin-1",
        now=datetime(2026, 7, 17, tzinfo=UTC),
    )

    assert saved == RetentionPolicy(
        mode="generations",
        generations=30,
        days=None,
        updated_at="2026-07-17T00:00:00+00:00",
        updated_by="admin-1",
    )
    assert load_retention_policy(path) == saved


def test_storage_usage_reports_output_instance_and_site_snapshots(tmp_path: Path) -> None:
    output = tmp_path / "output"
    instance = tmp_path / "instance"
    site = output / "example.com"
    _snapshot(site, "20260717-000000.json")
    (site / "report.html").write_text("abc", encoding="utf-8")
    instance.mkdir()
    (instance / "auth.db").write_text("1234", encoding="utf-8")

    usage = collect_storage_usage(output, instance)

    assert usage.output_bytes == 5
    assert usage.instance_bytes == 4
    assert usage.total_bytes == 9
    assert len(usage.sites) == 1
    assert usage.sites[0].domain == "example.com"
    assert usage.sites[0].snapshot_count == 1
    assert usage.sites[0].snapshot_bytes == 2
    assert usage.sites[0].total_bytes == 5
