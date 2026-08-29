"""スケジュール実行デーモン。

schedule.json の next_run_at に達したドメインの処理を
バックグラウンドスレッドで自動実行する（ADR-0009）。

実行する処理は schedule.json の `job_type` で決まる:

- `"crawl"`（既定・キー欠落時もこれ）: 従来どおり src/main.py でクロールする。
- `"test"`: ステップ編集（test_steps.json）から spec を生成し、
  test_run_job のキューへテスト実行ジョブを投入する。
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
from web.services.metrics import record_crawl, set_schedule_delay

SCHEDULER_POLL_INTERVAL = 60  # seconds
INSTANCE_DIR = Path("instance")

#: schedule.json の job_type。キーが無い既存ファイルは必ず "crawl" として扱う。
JOB_TYPE_CRAWL = "crawl"
JOB_TYPE_TEST = "test"
VALID_JOB_TYPES = frozenset({JOB_TYPE_CRAWL, JOB_TYPE_TEST})

#: スケジュールテストのジョブ終端を見張るスレッドが諦めるまでの時間（秒）。
#: 待ち切れなかった場合も「結果不明」として履歴に残し、無記録にはしない。
SCHEDULED_TEST_WAIT_TIMEOUT = 24 * 3600

#: 生成した spec の置き場（output/<domain>/qa_process/edited.spec.ts）。
#: ステップ編集画面の実行と同じ場所を使う。実行の成果物が 1 箇所に揃っていないと、
#: 「どの spec を流した結果か」が追えなくなる。
SCHEDULED_SPEC_RELATIVE = "qa_process/edited.spec.ts"

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

    job_type = _resolve_job_type(config)
    site_url = str(config.get("site_url", "")).strip()
    # site_url が必須なのはクロールだけ。テストジョブは環境設定（environment）と
    # ステップ定義から実行先を決めるため、ここで一律に弾いてはならない。
    if job_type == JOB_TYPE_CRAWL and not site_url:
        logger.warning("site_url が未設定のためスキップ: domain=%s", domain)
        return

    # 予定時刻からの遅延を公開する（滞留・詰まりの検知用）
    set_schedule_delay((now - next_run).total_seconds())

    # 先にタイムスタンプを更新して二重実行を防止する
    _persist_timestamps(schedule_path, config, now)

    # 二重実行防止の直後に job_type で分岐する。ここから先はクロールとテストで
    # 処理を共有しない（リトライの意味も、成功/失敗の意味も別物のため）。
    output_root = crawl_output or schedule_path.parent.parent
    if job_type == JOB_TYPE_TEST:
        start_scheduled_test(
            domain,
            schedule_path,
            config,
            output_root=output_root,
            trigger="scheduled",
            started_at=now,
        )
        return
    if job_type not in VALID_JOB_TYPES:
        # 未知の job_type でクロールへ倒すと、利用者の意図と違う処理が黙って走る。
        # 実行はせず、なぜ動かなかったのかを履歴に名指しで残す。
        logger.warning("未知の job_type のため実行しません: domain=%s value=%s", domain, job_type)
        _append_schedule_history(
            schedule_path,
            {
                "run_id": uuid.uuid4().hex,
                "domain": domain,
                "job_type": job_type,
                "started_at": now.isoformat(timespec="seconds"),
                "finished_at": now.isoformat(timespec="seconds"),
                "status": "failed",
                "trigger": "scheduled",
                "error": f"job_type が不正です（crawl / test のいずれか）: {job_type}",
            },
        )
        return

    logger.info("スケジュールクロール開始: domain=%s url=%s", domain, site_url)
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
        record_crawl(
            success=bool(last_result.success),
            duration_sec=max(0.0, float(last_result.duration_sec)),
        )
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


def _resolve_job_type(config: dict[str, Any]) -> str:
    """schedule.json から job_type を取り出す。

    **キー欠落・空文字・None は必ず "crawl"**（後方互換: job_type を知らない
    既存の schedule.json は 1 文字も変えずに従来どおり動く必要がある）。
    値が入っているが未知の場合は正規化した文字列をそのまま返し、
    呼び出し側で「不正」として扱えるようにする（黙ってクロールへ倒さない）。
    """
    raw = config.get("job_type", JOB_TYPE_CRAWL)
    if raw is None:
        return JOB_TYPE_CRAWL
    value = str(raw).strip().lower()
    return value or JOB_TYPE_CRAWL


@dataclass(frozen=True)
class ScheduledTestStart:
    """テスト実行ジョブの投入結果。ok が False のとき error に利用者向けの理由。"""

    ok: bool
    job_id: str = ""
    error: str = ""


def start_scheduled_test(
    domain: str,
    schedule_path: Path,
    config: dict[str, Any],
    *,
    output_root: Path,
    trigger: str = "scheduled",
    started_at: datetime | None = None,
) -> ScheduledTestStart:
    """スケジュール設定に従ってテスト実行ジョブをキューへ投入する。

    スケジューラー（trigger="scheduled"）と run-now（trigger="manual"）の
    両方から呼ぶ共通経路。投入までを行い、**完了は待たない**。

    起動できなかった場合は必ず `schedule_history.jsonl` へ status:"failed" と
    理由を残す。黙ってスキップすると、利用者から見えるのは「予定時刻を過ぎたのに
    何も起きない」だけで、原因を追う手掛かりが 1 つも残らない。

    リトライ（retry_max / retry_backoff_seconds）はテストには適用しない。
    テストの失敗はクロールの失敗と違って「システムの不調」ではなく「結果」であり、
    落ちたテストを自動で走らせ直すと不合格を握り潰すことになる。
    不安定さ（フレーキー）の検出は run_playwright の retries が担当する。
    """
    from web.services import environment_store, test_run_job, test_step_store

    root = Path(output_root)
    began = started_at or datetime.now().astimezone()

    def fail(reason: str) -> ScheduledTestStart:
        logger.warning("スケジュールテストを開始できません: domain=%s reason=%s", domain, reason)
        _append_schedule_history(
            schedule_path,
            _test_history_record(
                domain=domain,
                config=config,
                started_at=began,
                status="failed",
                trigger=trigger,
                error=reason,
            ),
        )
        return ScheduledTestStart(False, "", _sanitize_error(reason))

    # ① ステップ定義を読む
    try:
        document = test_step_store.load(root, domain)
    except Exception as exc:  # noqa: BLE001 - 読めない理由をそのまま利用者へ返す
        return fail(f"ステップ定義を読めません: {exc}")

    # ② 実行対象を絞る（schedule_test_ids が空なら enabled 全件）
    selected = {
        str(item).strip()
        for item in (config.get("schedule_test_ids") or [])
        if str(item).strip()
    }
    tests = [
        test
        for test in document.get("tests", [])
        if isinstance(test, dict) and test.get("enabled", True)
    ]
    if selected:
        tests = [test for test in tests if str(test.get("test_id", "")) in selected]
    if not tests:
        reason = "ステップが未作成のため実行できません"
        if selected:
            reason += "（指定された test_id に一致する有効なステップがありません）"
        return fail(reason)

    # ③ spec を書き出す（正本はステップ。spec は毎回作り直す）
    output_dir = root / domain / "qa_process"
    spec_path = root / domain / SCHEDULED_SPEC_RELATIVE
    try:
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(
            test_step_store.to_spec_ts({**document, "tests": tests}), encoding="utf-8"
        )
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return fail(f"spec を生成できません: {exc}")

    # ④ 環境を解決する。指定した環境が無いときは既定へ倒さず失敗させる
    #    （指定と違う環境へテストが流れる方が危険。environment_store.resolve と同じ方針）。
    env_id = str(config.get("environment", "") or "").strip()
    try:
        environment = environment_store.resolve(root, domain, env_id)
    except Exception as exc:  # noqa: BLE001
        return fail(f"環境設定を読めません: {exc}")
    if env_id and environment is None:
        return fail(f"指定された環境が見つかりません: {env_id}")
    base_url = str((environment or {}).get("base_url") or "").strip() or None
    try:
        storage_state = environment_store.storage_state_path(root, domain, environment)
    except Exception:  # noqa: BLE001 - ログイン状態が無くても実行自体は可能
        logger.warning("storage state を解決できませんでした: domain=%s", domain, exc_info=True)
        storage_state = None

    # ⑤ キューへ投入する
    try:
        from crawler.url_safety import _local_targets_allowed
        from web.services.egress_gateway import EgressPolicy

        policy = EgressPolicy(allow_local=_local_targets_allowed())
    except Exception:  # noqa: BLE001 - 方針を作れない場合は executor の既定に委ねる
        logger.warning("送信ポリシーを構成できませんでした: domain=%s", domain, exc_info=True)
        policy = None

    try:
        job = test_run_job.enqueue_test_run(
            domain=domain,
            kind="schedule",
            spec_path=spec_path,
            output_dir=output_dir,
            output_root=root,
            environment=str((environment or {}).get("env_id") or ""),
            per_test_timeout_sec=_bounded_int(
                config.get("per_test_timeout_sec"), default=30, minimum=5, maximum=600
            ),
            retries=_bounded_int(config.get("retries"), default=1, minimum=0, maximum=3),
            base_url=base_url,
            storage_state=storage_state,
            egress_policy=policy,
            schedule_context={"trigger": trigger, "schedule_path": str(schedule_path)},
        )
    except test_run_job.DomainBusyError as exc:
        return fail(str(exc))
    except Exception as exc:  # noqa: BLE001
        return fail(f"テスト実行を開始できません: {type(exc).__name__}: {exc}")

    logger.info(
        "スケジュールテストを投入: domain=%s job_id=%s trigger=%s tests=%d",
        domain,
        job.job_id,
        trigger,
        len(tests),
    )
    # **enqueue したら待たずに返す。** 7 時間かかる spec をここで待つと、
    # ポーリングループ（_scheduler_loop）がその間停止し、他ドメインの予定も
    # run-now の応答も全部止まる。結果は下の見張りスレッドが履歴へ書く。
    _watch_scheduled_test(
        job,
        schedule_path=schedule_path,
        domain=domain,
        config=config,
        started_at=began,
        trigger=trigger,
    )
    return ScheduledTestStart(True, job.job_id, "")


def _watch_scheduled_test(
    job: Any,
    *,
    schedule_path: Path,
    domain: str,
    config: dict[str, Any],
    started_at: datetime,
    trigger: str,
) -> None:
    """ジョブの終端を別スレッドで待ち、schedule_history.jsonl へ 1 行残す。

    デーモンスレッドにするのは、待っている最中のプロセス終了を妨げないため。
    その場合は履歴が残らないが、テスト実行自体の証跡は test_run_history.jsonl
    （test_run_job 側で永続化）に残るので、実行が丸ごと闇に消えることはない。
    """

    def _wait() -> None:
        try:
            finished = job.wait(SCHEDULED_TEST_WAIT_TIMEOUT)
            status = str(getattr(job, "status", "") or "failed")
            error = str(getattr(job, "error", "") or "")
            if not finished:
                status = "failed"
                error = error or "実行の完了を確認できませんでした（待機時間を超過）"
            result = getattr(job, "result", {}) or {}
            _append_schedule_history(
                schedule_path,
                _test_history_record(
                    domain=domain,
                    config=config,
                    started_at=started_at,
                    status=status,
                    trigger=trigger,
                    error=error,
                    job_id=str(getattr(job, "job_id", "")),
                    run_id_value=str(getattr(job, "run_id", "") or ""),
                    duration_sec=float(getattr(job, "elapsed_sec", lambda: 0)() or 0),
                    summary={
                        "total": int(result.get("total") or 0),
                        "passed": int(result.get("passed") or 0),
                        "failed": int(result.get("failed") or 0),
                        "flaky": int(result.get("flaky") or 0),
                    },
                ),
            )
        except Exception:
            logger.warning(
                "スケジュールテストの履歴を残せませんでした: domain=%s", domain, exc_info=True
            )

    threading.Thread(
        target=_wait,
        daemon=True,
        name=f"ScheduleTestWatch-{str(getattr(job, 'job_id', ''))[:8]}",
    ).start()


def _test_history_record(
    *,
    domain: str,
    config: dict[str, Any],
    started_at: datetime,
    status: str,
    trigger: str,
    error: str = "",
    job_id: str = "",
    run_id_value: str = "",
    duration_sec: float = 0.0,
    summary: dict[str, int] | None = None,
) -> dict[str, object]:
    """schedule_history.jsonl の 1 行を作る（テストジョブ用）。

    クロールの記録と同じキー（run_id / status / trigger / error）を維持し、
    画面（/schedule/history）が job_type を知らなくても表示できるようにする。
    """
    return {
        "run_id": run_id_value or uuid.uuid4().hex,
        "domain": domain,
        "job_type": JOB_TYPE_TEST,
        "job_id": job_id,
        "site_url": str(config.get("site_url", "") or ""),
        "environment": str(config.get("environment", "") or ""),
        "started_at": started_at.isoformat(timespec="seconds"),
        "finished_at": datetime.now(tz=started_at.tzinfo).isoformat(timespec="seconds"),
        "status": status,
        "attempts": 1,  # テストはリトライしない（start_scheduled_test の docstring 参照）
        "duration_sec": round(float(duration_sec), 3),
        "trigger": trigger,
        "summary": summary or {"total": 0, "passed": 0, "failed": 0, "flaky": 0},
        "error": "" if status == "complete" else _sanitize_error(error),
    }


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
