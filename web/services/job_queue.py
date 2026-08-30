"""非同期クロールジョブの管理。

REST API (/api/v1/sites/<domain>/crawl) から呼び出され、
バックグラウンドスレッドでクロールを実行してジョブ状態を保持する。
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from web.services.drift_summary import drift_count, load_drift_summary, should_notify_drift

_JOBS: dict[str, CrawlJob] = {}
_FINISHED_STATUSES = frozenset({"completed", "failed"})
_JOBS_LOCK = threading.Lock()

MAX_LOG_BYTES = 4096
MAX_JOBS_PER_DOMAIN = 20

JobStatus = Literal["queued", "running", "completed", "failed"]

logger = logging.getLogger(__name__)


@dataclass
class CrawlJob:
    job_id: str
    domain: str
    site_url: str
    status: JobStatus
    started_at: str
    finished_at: str | None = None
    exit_code: int | None = None
    log_tail: str = field(default="", repr=False)


def start_crawl_job(
    domain: str,
    site_url: str,
    depth: int = 2,
    max_pages: int = 30,
    formats: list[str] | None = None,
    compare: bool = True,
    auth_path: str = "",
    output_dir: Path | None = None,
    on_done: Callable[[CrawlJob], None] | None = None,
    domain_name: str = "",
) -> str:
    """バックグラウンドスレッドでクロールを開始し、job_id を返す。

    output_dir: テナントスコープ済み出力先。スレッド内ではリクエスト
    コンテキストを参照できないため、呼び出し元（ルート）が解決して渡す。
    domain_name: 出力先ディレクトリ名。既定は domain（サイトのディレクトリ
    ラベル）で、再クロールが必ず同じディレクトリへ書き戻るようにする。
    on_done: ジョブが終了（completed / failed）した直後にジョブを渡して呼ぶ。
    スレッド内で実行されるため、リクエストコンテキストは参照できない。
    例外は握りつぶしてログに残す（クロール自体の結果に影響させない）。
    """
    import uuid

    job_id = uuid.uuid4().hex
    now = datetime.now().isoformat(timespec="seconds")
    job = CrawlJob(job_id=job_id, domain=domain, site_url=site_url, status="queued", started_at=now)

    with _JOBS_LOCK:
        _JOBS[job_id] = job
        _publish_queue_depth()
        _evict_old_jobs(domain)

    thread = threading.Thread(
        target=_run_job,
        args=(
            job,
            depth,
            max_pages,
            formats or ["md", "html", "json"],
            compare,
            auth_path,
            output_dir,
            on_done,
            (domain_name or domain),
        ),
        daemon=True,
        name=f"CrawlJob-{job_id[:8]}",
    )
    thread.start()
    return job_id


def get_job(job_id: str) -> CrawlJob | None:
    with _JOBS_LOCK:
        return _JOBS.get(job_id)


def list_jobs_for_domain(domain: str) -> list[CrawlJob]:
    """domain に属するジョブを新しい順に返す（最大 MAX_JOBS_PER_DOMAIN 件）。"""
    with _JOBS_LOCK:
        jobs = [j for j in _JOBS.values() if j.domain == domain]
    return sorted(jobs, key=lambda j: j.started_at, reverse=True)[:MAX_JOBS_PER_DOMAIN]


def _evict_old_jobs(domain: str) -> None:
    """_JOBS_LOCK 保持中に呼ぶ。domain の古いジョブを上限まで削除する。"""
    domain_jobs = sorted(
        [jid for jid, j in _JOBS.items() if j.domain == domain],
        key=lambda jid: _JOBS[jid].started_at,
    )
    while len(domain_jobs) >= MAX_JOBS_PER_DOMAIN:
        del _JOBS[domain_jobs.pop(0)]


def _run_job(
    job: CrawlJob,
    depth: int,
    max_pages: int,
    formats: list[str],
    compare: bool,
    auth_path: str,
    output_dir: Path | None = None,
    on_done: Callable[[CrawlJob], None] | None = None,
    domain_name: str = "",
) -> None:
    cmd = [
        sys.executable,
        "src/main.py",
        "--url",
        job.site_url,
        "--depth",
        str(depth),
        "--max-pages",
        str(max_pages),
        "--format",
        ",".join(formats),
    ]
    if output_dir is not None:
        cmd += ["--output", str(output_dir)]
    if domain_name:
        cmd += ["--domain-name", domain_name]
    if compare:
        cmd.append("--compare")
    if auth_path:
        cmd += ["--auth", auth_path]

    _update(job, status="running")
    log_buf: list[str] = []

    try:
        proc = subprocess.Popen(  # nosec B603
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            log_buf.append(line)
        proc.wait()
        log_text = "".join(log_buf)[-MAX_LOG_BYTES:]
        status: JobStatus = "completed" if proc.returncode == 0 else "failed"
        _update(job, status=status, exit_code=proc.returncode, log_tail=log_text)
        _notify_done(job, on_done)
        if status == "completed" and compare:
            _try_slack_notify(job, output_dir)
    except OSError as exc:
        logger.error("クロールジョブ起動失敗: job_id=%s, %s", job.job_id, exc)
        _update(job, status="failed", exit_code=-1, log_tail=str(exc))
        _notify_done(job, on_done)


def _notify_done(job: CrawlJob, on_done: Callable[[CrawlJob], None] | None) -> None:
    """終了コールバックを呼ぶ。失敗してもジョブ結果には影響させない。"""
    if on_done is None:
        return
    try:
        on_done(job)
    except Exception:  # noqa: BLE001 - コールバックの失敗でクロール結果を捨てない
        logger.warning("on_done failed: job_id=%s", job.job_id, exc_info=True)


def _try_slack_notify(job: CrawlJob, output_dir: Path | None = None) -> None:
    """ドリフトがあればSlack通知を試みる（失敗しても例外を伝播させない）。"""
    try:
        from dotenv import dotenv_values

        env = dotenv_values(".env")
        webhook_url = env.get("SLACK_WEBHOOK_URL", "") or os.environ.get("SLACK_WEBHOOK_URL", "")
        if not webhook_url:
            return
        base_dir = output_dir if output_dir is not None else Path("output")
        summary_path = base_dir / job.domain / "drift_summary.json"
        summary = load_drift_summary(summary_path)
        if summary is None:
            return
        if not should_notify_drift(summary):
            return

        from web.services.notifier import (
            NOTIFIER_SLACK,
            DriftNotification,
            NotifierConfig,
            send_drift_notification,
        )

        notification = DriftNotification(
            site_url=str(summary.get("site_url") or job.site_url),
            added_pages=drift_count(summary, "added_pages"),
            removed_pages=drift_count(summary, "removed_pages"),
            field_changes=drift_count(summary, "field_changes"),
            api_changes=drift_count(summary, "api_changes"),
            report_url=str(summary.get("report_url") or f"output/{job.domain}/diff_report.html"),
        )
        config = NotifierConfig(notifier_type=NOTIFIER_SLACK, endpoint=webhook_url)
        send_drift_notification(config, notification)
    except Exception:
        logger.warning("Slack通知に失敗しました", exc_info=True)


def _update(
    job: CrawlJob,
    *,
    status: JobStatus,
    exit_code: int | None = None,
    log_tail: str = "",
) -> None:
    with _JOBS_LOCK:
        job.status = status
        if exit_code is not None:
            job.exit_code = exit_code
        if log_tail:
            job.log_tail = log_tail
        if status in ("completed", "failed"):
            job.finished_at = datetime.now().isoformat(timespec="seconds")
        _publish_queue_depth()


def _publish_queue_depth() -> None:
    """未終了ジョブ数をメトリクスへ反映する（_JOBS_LOCK 保持中に呼ぶこと）。"""
    from web.services.metrics import set_job_queue_depth

    unfinished = sum(1 for job in _JOBS.values() if job.status not in _FINISHED_STATUSES)
    set_job_queue_depth(unfinished)
