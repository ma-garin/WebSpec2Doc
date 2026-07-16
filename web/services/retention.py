"""スナップショット保持ポリシーと安全な世代GC。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path


@dataclass(frozen=True)
class RetentionPolicy:
    mode: str = "unlimited"
    generations: int | None = None
    days: int | None = None
    updated_at: str = ""
    updated_by: str = ""


@dataclass(frozen=True)
class PruneResult:
    deleted_count: int = 0
    deleted_bytes: int = 0
    deleted_paths: tuple[str, ...] = ()


class RetentionPolicyError(ValueError):
    """保持設定の入力エラー。"""


@dataclass(frozen=True)
class SiteStorageUsage:
    domain: str
    snapshot_count: int
    snapshot_bytes: int
    total_bytes: int
    updated_at: str


@dataclass(frozen=True)
class StorageUsage:
    output_bytes: int
    instance_bytes: int
    total_bytes: int
    sites: tuple[SiteStorageUsage, ...]


def load_retention_policy(path: Path) -> RetentionPolicy:
    """設定が無い・壊れている場合は安全側の無制限を返す。"""
    if not path.is_file():
        return RetentionPolicy()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return RetentionPolicy()
    if not isinstance(data, dict):
        return RetentionPolicy()
    mode = str(data.get("mode", "unlimited"))
    generations = _bounded_int(data.get("generations"), 1, 10_000)
    days = _bounded_int(data.get("days"), 1, 3_650)
    if mode not in {"unlimited", "generations", "days"}:
        return RetentionPolicy()
    if mode == "generations" and generations is None:
        return RetentionPolicy()
    if mode == "days" and days is None:
        return RetentionPolicy()
    return RetentionPolicy(
        mode=mode,
        generations=generations if mode == "generations" else None,
        days=days if mode == "days" else None,
        updated_at=str(data.get("updated_at", "")),
        updated_by=str(data.get("updated_by", "")),
    )


def save_retention_policy(
    path: Path,
    values: dict[str, object],
    *,
    updated_by: str = "",
    now: datetime | None = None,
) -> RetentionPolicy:
    mode = str(values.get("mode", "unlimited"))
    if mode not in {"unlimited", "generations", "days"}:
        raise RetentionPolicyError("invalid retention mode")
    generations = _bounded_int(values.get("generations"), 1, 10_000)
    days = _bounded_int(values.get("days"), 1, 3_650)
    if mode == "generations" and generations is None:
        raise RetentionPolicyError("generations is required")
    if mode == "days" and days is None:
        raise RetentionPolicyError("days is required")
    policy = RetentionPolicy(
        mode=mode,
        generations=generations if mode == "generations" else None,
        days=days if mode == "days" else None,
        updated_at=(now or datetime.now(UTC)).replace(microsecond=0).isoformat(),
        updated_by=updated_by,
    )
    payload = {"version": 1, **asdict(policy)}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
    return policy


def _bounded_int(value: object, minimum: int, maximum: int) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        parsed = int(value)
    else:
        return None
    return parsed if minimum <= parsed <= maximum else None


def collect_storage_usage(output_dir: Path, instance_dir: Path) -> StorageUsage:
    """スコープ済みoutput/instanceの実ファイル容量を集計する。"""
    sites: list[SiteStorageUsage] = []
    if output_dir.is_dir():
        for site_dir in sorted(output_dir.iterdir()):
            if (
                site_dir.is_symlink()
                or not site_dir.is_dir()
                or site_dir.name.startswith(".")
                or site_dir.name == "tenants"
            ):
                continue
            site_files = _regular_files(site_dir)
            snapshot_files = [path for path in site_files if path.parent == site_dir / "snapshots"]
            latest_mtime = max((path.stat().st_mtime for path in site_files), default=0.0)
            sites.append(
                SiteStorageUsage(
                    domain=site_dir.name,
                    snapshot_count=len(snapshot_files),
                    snapshot_bytes=sum(path.stat().st_size for path in snapshot_files),
                    total_bytes=sum(path.stat().st_size for path in site_files),
                    updated_at=(
                        datetime.fromtimestamp(latest_mtime, UTC).replace(microsecond=0).isoformat()
                        if latest_mtime
                        else ""
                    ),
                )
            )
    output_bytes = sum(site.total_bytes for site in sites)
    instance_bytes = sum(path.stat().st_size for path in _regular_files(instance_dir))
    return StorageUsage(output_bytes, instance_bytes, output_bytes + instance_bytes, tuple(sites))


def _regular_files(root: Path) -> list[Path]:
    if root.is_symlink() or not root.is_dir():
        return []
    return [path for path in root.rglob("*") if path.is_file() and not path.is_symlink()]


def prune_snapshots(
    output_dir: Path, policy: RetentionPolicy, *, now: datetime | None = None
) -> PruneResult:
    """保持設定をサイトごとのsnapshot JSONへ適用する。"""
    if policy.mode == "unlimited":
        return PruneResult()
    if policy.mode not in {"generations", "days"}:
        return PruneResult()

    deleted_count = 0
    deleted_bytes = 0
    deleted_paths: list[str] = []
    if not output_dir.is_dir():
        return PruneResult()
    for site_dir in sorted(output_dir.iterdir()):
        snapshots_dir = site_dir / "snapshots"
        if site_dir.is_symlink() or snapshots_dir.is_symlink() or not snapshots_dir.is_dir():
            continue
        try:
            snapshots_root = snapshots_dir.resolve(strict=True)
        except OSError:
            continue
        snapshots = sorted(
            (
                path
                for path in snapshots_dir.glob("*.json")
                if path.is_file() and not path.is_symlink() and _is_within(path, snapshots_root)
            ),
            key=lambda path: path.name,
            reverse=True,
        )
        if policy.mode == "generations" and policy.generations is not None:
            candidates = snapshots[max(1, policy.generations) :]
        elif policy.mode == "days" and policy.days is not None:
            current = now or datetime.now(UTC)
            cutoff = current - timedelta(days=max(1, policy.days))
            candidates = [
                path
                for path in snapshots[1:]
                if (_snapshot_time(path, current.tzinfo) or current) < cutoff
            ]
        else:
            candidates = []
        for path in candidates:
            try:
                size = path.stat().st_size
                path.unlink()
            except OSError:
                continue
            deleted_count += 1
            deleted_bytes += size
            deleted_paths.append(str(path.relative_to(output_dir)))
    return PruneResult(deleted_count, deleted_bytes, tuple(deleted_paths))


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(root)
    except (OSError, ValueError):
        return False
    return True


def _snapshot_time(path: Path, zone: tzinfo | None) -> datetime | None:
    try:
        parsed = datetime.strptime(path.name[:15], "%Y%m%d-%H%M%S")
    except ValueError:
        return None
    return parsed.replace(tzinfo=zone)
