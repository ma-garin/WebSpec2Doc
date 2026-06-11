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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from web.config import OUTPUT_DIR

SCHEDULER_POLL_INTERVAL = 60  # seconds

_stop_event = threading.Event()
_started_lock = threading.Lock()
_scheduler_started = False

logger = logging.getLogger(__name__)


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
    """output_dir 配下の全 schedule.json を検査し、期限到来分を実行する。"""
    if not output_dir.is_dir():
        return
    now = datetime.now()
    for domain_dir in output_dir.iterdir():
        if not domain_dir.is_dir():
            continue
        schedule_path = domain_dir / "schedule.json"
        if not schedule_path.is_file():
            continue
        try:
            _maybe_run(domain_dir.name, schedule_path, now)
        except Exception:
            logger.exception("スケジュール実行エラー: domain=%s", domain_dir.name)


def _maybe_run(domain: str, schedule_path: Path, now: datetime) -> None:
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

    if now < next_run:
        return

    site_url = str(config.get("site_url", "")).strip()
    if not site_url:
        logger.warning("site_url が未設定のためスキップ: domain=%s", domain)
        return

    logger.info("スケジュールクロール開始: domain=%s url=%s", domain, site_url)

    # 先にタイムスタンプを更新して二重実行を防止する
    _persist_timestamps(schedule_path, config, now)
    _run_crawl(site_url)

    logger.info("スケジュールクロール完了: domain=%s", domain)


def _persist_timestamps(schedule_path: Path, config: dict[str, Any], ran_at: datetime) -> None:
    """last_run_at を更新し next_run_at を再計算して保存する。"""
    updated = {
        **config,
        "last_run_at": ran_at.isoformat(timespec="seconds"),
        "next_run_at": _calc_next_run_at(str(config.get("interval", "disabled")), ran_at),
    }
    try:
        tmp = schedule_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(schedule_path)
    except OSError as exc:
        logger.warning("schedule.json 更新エラー: %s, %s", schedule_path, exc)


def _calc_next_run_at(interval: str, base: datetime) -> str | None:
    """interval 文字列から次回実行時刻を計算する。"""
    delta_map: dict[str, timedelta] = {
        "daily": timedelta(hours=24),
        "weekly": timedelta(days=7),
        "monthly": timedelta(days=30),
    }
    delta = delta_map.get(interval)
    if delta is None:
        return None
    return (base + delta).isoformat(timespec="seconds")


def _run_crawl(site_url: str) -> None:
    """src/main.py を子プロセスとして実行する。失敗してもログに記録するのみ。"""
    cmd = [
        sys.executable,
        "src/main.py",
        "--url",
        site_url,
        "--format",
        "md,html,json",
        "--compare",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)  # nosec B603
        if result.returncode != 0:
            logger.warning(
                "スケジュールクロール終了コード %d: %s", result.returncode, result.stderr[-500:]
            )
    except subprocess.TimeoutExpired:
        logger.error("スケジュールクロールがタイムアウト: url=%s", site_url)
    except OSError as exc:
        logger.error("スケジュールクロール起動失敗: %s", exc)
