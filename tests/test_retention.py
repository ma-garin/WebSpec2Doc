from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from web.services.retention import (
    RetentionPolicy,
    RetentionPolicyError,
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


def test_generation_policy_never_follows_symlinked_snapshots_directory(tmp_path: Path) -> None:
    external = tmp_path / "outside"
    external.mkdir()
    protected = _snapshot(external, "20260715-000000.json")
    newest = _snapshot(external, "20260717-000000.json")
    target = external / "snapshots"
    site = tmp_path / "output" / "example.com"
    site.mkdir(parents=True)
    (site / "snapshots").symlink_to(target, target_is_directory=True)

    result = prune_snapshots(
        tmp_path / "output", RetentionPolicy(mode="generations", generations=1)
    )

    assert result.deleted_count == 0
    assert protected.is_file()
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


@pytest.mark.parametrize("value", [1.1, "1.1", b"1"])
def test_save_policy_rejects_non_integer_generation_values(tmp_path: Path, value: object) -> None:
    with pytest.raises(RetentionPolicyError):
        save_retention_policy(
            tmp_path / "retention.json",
            {"mode": "generations", "generations": value},
        )


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


# ---------- 世代別スクリーンショット（*-shots/）の巻き取り ----------


def _shots(snapshot_path: Path, *sizes: int) -> Path:
    """スナップショットに対応する世代別スクリーンショット置き場を作る。"""
    shots_dir = snapshot_path.with_name(f"{snapshot_path.stem}-shots")
    shots_dir.mkdir(parents=True, exist_ok=True)
    for index, size in enumerate(sizes):
        (shots_dir / f"P{index + 1:03d}.png").write_bytes(b"x" * size)
    return shots_dir


def test_pruning_a_snapshot_also_removes_its_screenshots(tmp_path: Path) -> None:
    """JSON だけ消すと画像が参照されないまま残り、容量が単調増加する。"""
    site = tmp_path / "output" / "example.com"
    oldest = _snapshot(site, "20260715-000000.json")
    oldest_shots = _shots(oldest, 10, 20)
    newest = _snapshot(site, "20260717-000000.json")
    newest_shots = _shots(newest, 30)

    prune_snapshots(tmp_path / "output", RetentionPolicy(mode="generations", generations=1))

    assert not oldest.exists()
    assert not oldest_shots.exists(), "対応する世代別スクリーンショットが残っている"
    assert newest.is_file()
    assert newest_shots.is_dir(), "残す世代の画像まで消してはいけない"


def test_deleted_bytes_include_the_screenshots(tmp_path: Path) -> None:
    """消した容量に画像分が含まれること（数字が実態と合わないと保持設定を調整できない）。"""
    site = tmp_path / "output" / "example.com"
    oldest = _snapshot(site, "20260715-000000.json")  # JSON は 2 バイト
    _shots(oldest, 10, 20)
    _snapshot(site, "20260717-000000.json")

    result = prune_snapshots(
        tmp_path / "output", RetentionPolicy(mode="generations", generations=1)
    )

    assert result.deleted_bytes == 2 + 30
    assert "example.com/snapshots/20260715-000000-shots" in result.deleted_paths


def test_snapshot_without_screenshots_is_unaffected(tmp_path: Path) -> None:
    site = tmp_path / "output" / "example.com"
    _snapshot(site, "20260715-000000.json")
    _snapshot(site, "20260717-000000.json")

    result = prune_snapshots(
        tmp_path / "output", RetentionPolicy(mode="generations", generations=1)
    )

    assert result.deleted_count == 1
    assert result.deleted_bytes == 2


def test_symlinked_shots_directory_is_not_followed(tmp_path: Path) -> None:
    """保持設定の適用範囲を超えて外のディレクトリを消さない。"""
    external = tmp_path / "outside"
    external.mkdir()
    (external / "keep.png").write_bytes(b"xxxx")

    site = tmp_path / "output" / "example.com"
    oldest = _snapshot(site, "20260715-000000.json")
    oldest.with_name(f"{oldest.stem}-shots").symlink_to(external, target_is_directory=True)
    _snapshot(site, "20260717-000000.json")

    prune_snapshots(tmp_path / "output", RetentionPolicy(mode="generations", generations=1))

    assert (external / "keep.png").is_file(), "シンボリックリンクの先を消してはいけない"


def test_storage_usage_counts_generation_screenshots(tmp_path: Path) -> None:
    """世代別スクリーンショットを snapshot_bytes に数えること。

    直下だけを見ると、画像が増えても表示上は増えず、保持設定を調整する判断ができない。
    """
    output = tmp_path / "output"
    instance = tmp_path / "instance"
    instance.mkdir()
    site = output / "example.com"
    snapshot = _snapshot(site, "20260717-000000.json")  # 2 バイト
    _shots(snapshot, 40)

    usage = collect_storage_usage(output, instance)

    assert usage.sites[0].snapshot_bytes == 2 + 40
    assert usage.sites[0].snapshot_count == 2
