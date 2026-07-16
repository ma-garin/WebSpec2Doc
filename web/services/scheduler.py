"""スケジュール実行デーモン。

schedule.json の next_run_at に達したドメインのクロールを
バックグラウンドスレッドで自動実行する（ADR-0009）。
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import time as time_module
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from web.config import OUTPUT_DIR

SCHEDULER_POLL_INTERVAL = 60  # seconds
INSTANCE_DIR = Path("instance")

_stop_event = threading.Event()
_started_lock = threading.Lock()
_scheduler_started = False

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CrawlRunResult:
    success: bool
    error: str = ""
    duration_sec: float = 0.0


def start_scheduler() -> None:
    """アプリ起動時に一度だけデーモンスレッドを起動する。"""
    global _scheduler_started
    with _started_lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    _stop_event.clear()
    thread = threading.Thread(target=_scheduler_loop, daemon=True, name="WebSpec2Doc-Scheduler")
    thread.start()
    logger.info(
        "スケジューラーデーモンを起動しました (poll_interval=%ds)",
        SCHEDULER_POLL_INTERVAL,
    )


def stop_scheduler() -> None:
    """テスト・シャットダウン用。スケジューラーを停止する。"""
    global _scheduler_started
    _stop_event.set()
    with _started_lock:
        _scheduler_started = False


def _scheduler_loop() -> None:
    """STOP_EVENT がセットされるまでポーリングし続けるメインループ。"""
    while not _stop_event.is_set():
        try:
            _check_and_run_due(OUTPUT_DIR)
        except Exception:
            logger.exception("スケジューラーループで予期しないエラーが発生しました")
        # 1 秒ずつ分割スリープして終了シグナルに素早く応答する
        for _ in range(SCHEDULER_POLL_INTERVAL):
            if _stop_event.wait(1.0):
                return


def _check_and_run_due(output_dir: Path) -> None:
    """output_dir 配下の全 schedule.json を検査し、期限到来分を実行する。

    テナント分離後は output/tenants/{slug}/{domain}/ にもスケジュールが
    存在するため、共有領域とテナント領域の両方を走査する。
    """
    if not output_dir.is_dir():
        return
    now = datetime.now().astimezone()
    _scan_schedule_base(
        output_dir,
        now,
        crawl_output=None,
        retention_path=INSTANCE_DIR / "retention.json",
    )
    from web.tenancy import TENANTS_DIR_NAME

    tenants_root = output_dir / TENANTS_DIR_NAME
    if tenants_root.is_dir():
        for tenant_dir in tenants_root.iterdir():
            if tenant_dir.is_dir():
                _scan_schedule_base(
                    tenant_dir,
                    now,
                    crawl_output=tenant_dir,
                    retention_path=(
                        INSTANCE_DIR / TENANTS_DIR_NAME / tenant_dir.name / "retention.json"
                    ),
                )


def _scan_schedule_base(
    base_dir: Path,
    now: datetime,
    crawl_output: Path | None,
    retention_path: Path,
) -> None:
    from web.tenancy import TENANTS_DIR_NAME

    for domain_dir in base_dir.iterdir():
        if not domain_dir.is_dir() or domain_dir.name == TENANTS_DIR_NAME:
            continue
        schedule_path = domain_dir / "schedule.json"
        if not schedule_path.is_file():
            continue
        try:
            _maybe_run(
                domain_dir.name,
                schedule_path,
                now,
                crawl_output=crawl_output,
                retention_path=retention_path,
            )
        except Exception:
            logger.exception("スケジュール実行エラー: domain=%s", domain_dir.name)


def _maybe_run(
    domain: str,
    schedule_path: Path,
    now: datetime,
    crawl_output: Path | None = None,
    *,
    sleeper: Callable[[float], None] | None = None,
    retention_path: Path | None = None,
) -> None:
    """schedule.json を読み、期限到来時にクロールを起動して timestamps を更新する。"""
    try:
        config: dict[str, Any] = json.loads(schedule_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("schedule.json 読み込みエラー: domain=%s, %s", domain, exc)
        return

    if config.get("interval", "disabled") == "disabled":
        return

    next_run_str = config.get("next_run_at")
    if not next_run_str:
        return

    try:
        next_run = datetime.fromisoformat(str(next_run_str))
    except ValueError:
        logger.warning("next_run_at のパース失敗: domain=%s, value=%s", domain, next_run_str)
        return

    now, next_run = _normalize_schedule_datetimes(now, next_run, config)
    if now < next_run:
        return

    if not _is_allowed_execution_time(now, config):
        _reschedule_missed_window(schedule_path, config, next_run, now)
        return

    site_url = str(config.get("site_url", "")).strip()
    if not site_url:
        logger.warning("site_url が未設定のためスキップ: domain=%s", domain)
        return

    logger.info("スケジュールクロール開始: domain=%s url=%s", domain, site_url)

    # 先にタイムスタンプを更新して二重実行を防止する
    _persist_timestamps(schedule_path, config, now)
    retry_max = _bounded_int(config.get("retry_max"), default=2, minimum=0, maximum=5)
    backoff = _bounded_int(config.get("retry_backoff_seconds"), default=60, minimum=1, maximum=3600)
    active_sleeper = sleeper or time_module.sleep
    attempts = 0
    total_duration = 0.0
    last_result = CrawlRunResult(False, "クロールを開始できませんでした", 0.0)
    for attempt_index in range(retry_max + 1):
        if attempt_index:
            active_sleeper(float(backoff * (2 ** (attempt_index - 1))))
        attempts += 1
        try:
            raw_result = _run_crawl(site_url, crawl_output)
            last_result = (
                raw_result if isinstance(raw_result, CrawlRunResult) else CrawlRunResult(True)
            )
        except Exception as exc:  # noqa: BLE001 - 実行履歴へ失敗として確定する
            logger.exception("スケジュールクロールで予期しない例外: domain=%s", domain)
            last_result = CrawlRunResult(False, str(exc), 0.0)
        total_duration += max(0.0, float(last_result.duration_sec))
        if last_result.success:
            break

    _append_schedule_history(
        schedule_path,
        {
            "run_id": uuid.uuid4().hex,
            "domain": domain,
            "site_url": site_url,
            "started_at": now.isoformat(timespec="seconds"),
            "finished_at": datetime.now(tz=now.tzinfo).isoformat(timespec="seconds"),
            "status": "complete" if last_result.success else "failed",
            "attempts": attempts,
            "duration_sec": round(total_duration, 3),
            "trigger": "scheduled",
            "error": "" if last_result.success else _sanitize_error(last_result.error),
        },
    )

    if last_result.success:
        logger.info("スケジュールクロール完了: domain=%s attempts=%d", domain, attempts)
        if retention_path is not None:
            try:
                from web.services.retention import load_retention_policy, prune_snapshots

                output_scope = crawl_output or schedule_path.parent.parent
                policy = load_retention_policy(retention_path)
                pruned = prune_snapshots(output_scope, policy)
                if pruned.deleted_count:
                    logger.info(
                        "保持ポリシーによりスナップショットを削除: count=%d bytes=%d",
                        pruned.deleted_count,
                        pruned.deleted_bytes,
                    )
                    from web.services.admin_audit import append_admin_audit

                    append_admin_audit(
                        retention_path.parent / "admin_audit.jsonl",
                        action="retention.snapshots_pruned",
                        actor_id="scheduler",
                        actor_email="system",
                        target_type="workspace",
                        target_id="current",
                        detail={
                            "deleted_count": pruned.deleted_count,
                            "deleted_bytes": pruned.deleted_bytes,
                            "deleted_paths": list(pruned.deleted_paths),
                        },
                    )
            except Exception as exc:
                logger.warning("保持GCを完了できませんでした（クロール成功は維持）: %s", exc)
        _notify_drift_summary(config, schedule_path, site_url)
    else:
        logger.error("スケジュールクロール失敗: domain=%s attempts=%d", domain, attempts)
        _notify_final_failure(config, site_url, attempts, last_result.error, now)


def _notify_final_failure(
    config: dict[str, Any],
    site_url: str,
    attempts: int,
    error: str,
    started_at: datetime,
) -> None:
    from web.services.notifier import (
        CrawlFailureNotification,
        notifier_config_from_mapping,
        send_crawl_failure_notification,
    )

    notifier_config = notifier_config_from_mapping(config)
    if notifier_config is None:
        return
    notification = CrawlFailureNotification(
        site_url=site_url,
        attempts=attempts,
        error=_sanitize_error(error),
        started_at=started_at.isoformat(timespec="seconds"),
    )
    if not send_crawl_failure_notification(notifier_config, notification):
        logger.warning("クロール失敗通知を送信できませんでした: site=%s", site_url)


def _notify_drift_summary(config: dict[str, Any], schedule_path: Path, site_url: str) -> None:
    from web.services.notifier import (
        DriftNotification,
        notifier_config_from_mapping,
        send_drift_notification,
    )

    notifier_config = notifier_config_from_mapping(config)
    if notifier_config is None:
        return
    summary_path = schedule_path.parent / "diff_summary.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(summary, dict):
        return
    added = summary.get("added_pages") or []
    removed = summary.get("removed_pages") or []
    field_changes = _bounded_int(
        summary.get("field_changes"), default=0, minimum=0, maximum=1_000_000
    )
    api_changes = _bounded_int(summary.get("api_changes"), default=0, minimum=0, maximum=1_000_000)
    if not (added or removed or field_changes or api_changes):
        return
    limit = _bounded_int(config.get("diff_summary_limit"), default=5, minimum=1, maximum=20)

    def labels(items: object) -> tuple[str, ...]:
        result: list[str] = []
        if not isinstance(items, list):
            return ()
        for item in items:
            if not isinstance(item, dict):
                continue
            label = str(item.get("title") or item.get("url") or "").strip()
            if label:
                result.append(label)
            if len(result) >= limit:
                break
        return tuple(result)

    notification = DriftNotification(
        site_url=site_url,
        added_pages=len(added) if isinstance(added, list) else 0,
        removed_pages=len(removed) if isinstance(removed, list) else 0,
        field_changes=field_changes,
        api_changes=api_changes,
        report_url=str(schedule_path.parent / "diff_report.html"),
        added_page_names=labels(added),
        removed_page_names=labels(removed),
    )
    if not send_drift_notification(notifier_config, notification):
        logger.warning("ドリフト通知を送信できませんでした: site=%s", site_url)


def _normalize_schedule_datetimes(
    now: datetime, next_run: datetime, config: dict[str, Any]
) -> tuple[datetime, datetime]:
    timezone_name = str(config.get("timezone", "")).strip()
    zone = None
    if timezone_name:
        try:
            zone = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            logger.warning("不正な timezone を無視します: %s", timezone_name)
    if zone is not None:
        normalized_now = now.replace(tzinfo=zone) if now.tzinfo is None else now.astimezone(zone)
        normalized_next = (
            next_run.replace(tzinfo=zone) if next_run.tzinfo is None else next_run.astimezone(zone)
        )
        return normalized_now, normalized_next
    if now.tzinfo is not None and next_run.tzinfo is None:
        next_run = next_run.replace(tzinfo=now.tzinfo)
    elif now.tzinfo is None and next_run.tzinfo is not None:
        now = now.replace(tzinfo=next_run.tzinfo)
    return now, next_run


def _is_allowed_execution_time(now: datetime, config: dict[str, Any]) -> bool:
    weekdays = tuple(config.get("weekdays") or ())
    window_start = str(config.get("window_start", ""))
    window_end = str(config.get("window_end", ""))
    try:
        allowed = _next_allowed_datetime(
            now,
            weekdays=weekdays,
            window_start=window_start,
            window_end=window_end,
            zone=now.tzinfo,
        )
    except ValueError:
        logger.warning("不正な実行ウィンドウを検出したため実行を見送ります")
        return False
    return allowed == now


def _reschedule_missed_window(
    schedule_path: Path,
    config: dict[str, Any],
    previous_run: datetime,
    now: datetime,
) -> None:
    """ウィンドウ外で期限到来した実行を、次の将来ウィンドウへ送る。"""
    candidate = previous_run
    next_iso: str | None = None
    for _ in range(370):
        next_iso = _calc_next_run_at(
            str(config.get("interval", "disabled")),
            candidate,
            timezone_name=str(config.get("timezone", "")),
            weekdays=tuple(config.get("weekdays") or ()),
            window_start=str(config.get("window_start", "")),
            window_end=str(config.get("window_end", "")),
        )
        if not next_iso:
            break
        parsed = datetime.fromisoformat(next_iso)
        _, parsed = _normalize_schedule_datetimes(now, parsed, config)
        if parsed > now:
            break
        candidate = parsed
    updated = {**config, "next_run_at": next_iso}
    _write_schedule_config(schedule_path, updated)
    logger.info("実行ウィンドウ外のため次回へ延期: next_run_at=%s", next_iso)


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, str | int | float | bytes | bytearray):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, parsed))


def _sanitize_error(error: str) -> str:
    return " ".join(str(error).split())[:500]


def _append_schedule_history(schedule_path: Path, record: dict[str, object]) -> None:
    history_path = schedule_path.parent / "schedule_history.jsonl"
    try:
        with history_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("スケジュール実行履歴の保存に失敗: %s, %s", history_path, exc)


def _persist_timestamps(schedule_path: Path, config: dict[str, Any], ran_at: datetime) -> None:
    """last_run_at を更新し next_run_at を再計算して保存する。"""
    updated = {
        **config,
        "last_run_at": ran_at.isoformat(timespec="seconds"),
        "next_run_at": _calc_next_run_at(
            str(config.get("interval", "disabled")),
            ran_at,
            timezone_name=str(config.get("timezone", "")),
            weekdays=tuple(config.get("weekdays") or ()),
            window_start=str(config.get("window_start", "")),
            window_end=str(config.get("window_end", "")),
        ),
    }
    _write_schedule_config(schedule_path, updated)


def _write_schedule_config(schedule_path: Path, config: dict[str, Any]) -> None:
    try:
        tmp = schedule_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(schedule_path)
    except OSError as exc:
        logger.warning("schedule.json 更新エラー: %s, %s", schedule_path, exc)


def _calc_next_run_at(
    interval: str,
    base: datetime,
    *,
    timezone_name: str = "",
    weekdays: tuple[int, ...] = (),
    window_start: str = "",
    window_end: str = "",
) -> str | None:
    """周期と運用ウィンドウから次回実行時刻を計算する。

    timezone_name が空の場合は従来の naive datetime を維持する。設定済みの場合は
    IANA timezone の offset 付き ISO 8601 を返す。
    """
    delta_map: dict[str, timedelta] = {
        "daily": timedelta(hours=24),
        "weekly": timedelta(days=7),
        "monthly": timedelta(days=30),
    }
    delta = delta_map.get(interval)
    if delta is None:
        return None
    zone: tzinfo | None
    if timezone_name:
        try:
            zone = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            return None
        local_base = base.replace(tzinfo=zone) if base.tzinfo is None else base.astimezone(zone)
    else:
        zone = base.tzinfo
        local_base = base
    candidate = local_base + delta
    candidate = _next_allowed_datetime(
        candidate,
        weekdays=weekdays,
        window_start=window_start,
        window_end=window_end,
        zone=zone,
    )
    return candidate.isoformat(timespec="seconds")


def _next_allowed_datetime(
    candidate: datetime,
    *,
    weekdays: tuple[int, ...],
    window_start: str,
    window_end: str,
    zone: Any,
) -> datetime:
    """candidate 以降で最初の許可日時を返す。日跨ぎウィンドウにも対応する。"""
    allowed_days = frozenset(weekdays)
    if not window_start or not window_end:
        if not allowed_days or candidate.weekday() in allowed_days:
            return candidate
        for offset in range(1, 8):
            day = candidate.date() + timedelta(days=offset)
            if day.weekday() in allowed_days:
                return _combine(day, candidate.timetz().replace(tzinfo=None), zone)
        return candidate

    start_time = time.fromisoformat(window_start)
    end_time = time.fromisoformat(window_end)
    choices: list[datetime] = []
    # 前日開始の日跨ぎウィンドウに candidate が含まれる可能性がある。
    first_start_day = candidate.date() - timedelta(days=1)
    for offset in range(15):
        start_day = first_start_day + timedelta(days=offset)
        if allowed_days and start_day.weekday() not in allowed_days:
            continue
        interval_start = _combine(start_day, start_time, zone)
        interval_end = _combine(start_day, end_time, zone)
        if interval_end <= interval_start:
            interval_end += timedelta(days=1)
        if candidate >= interval_end:
            continue
        allowed = max(candidate, interval_start)
        if allowed < interval_end:
            choices.append(allowed)
    return min(choices) if choices else candidate


def _combine(day: date, at: time, zone: Any) -> datetime:
    combined = datetime.combine(day, at)
    return combined.replace(tzinfo=zone) if zone is not None else combined


def _run_crawl(site_url: str, crawl_output: Path | None = None) -> CrawlRunResult:
    """src/main.py を子プロセスとして実行し、成否と所要時間を返す。"""
    cmd = [
        sys.executable,
        "src/main.py",
        "--url",
        site_url,
        "--format",
        "md,html,json",
        "--compare",
    ]
    if crawl_output is not None:
        cmd += ["--output", str(crawl_output)]
    started = time_module.perf_counter()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)  # nosec B603
        if result.returncode != 0:
            error = _sanitize_error(result.stderr[-500:])
            logger.warning(
                "スケジュールクロール終了コード %d: %s", result.returncode, result.stderr[-500:]
            )
            return CrawlRunResult(
                False,
                error or f"終了コード {result.returncode}",
                time_module.perf_counter() - started,
            )
        return CrawlRunResult(True, "", time_module.perf_counter() - started)
    except subprocess.TimeoutExpired:
        logger.error("スケジュールクロールがタイムアウト: url=%s", site_url)
        return CrawlRunResult(
            False, "クロールがタイムアウトしました", time_module.perf_counter() - started
        )
    except OSError as exc:
        logger.error("スケジュールクロール起動失敗: %s", exc)
        return CrawlRunResult(False, str(exc), time_module.perf_counter() - started)
