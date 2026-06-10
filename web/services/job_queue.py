"""非同期クロールジョブの管理。

REST API (/api/v1/sites/<domain>/crawl) から呼び出され、
バックグラウンドスレッドでクロールを実行してジョブ状態を保持する。
"""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

_JOBS: dict[str, CrawlJob] = {}
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
) -> str:
    """バックグラウンドスレッドでクロールを開始し、job_id を返す。"""
    import uuid

    job_id = uuid.uuid4().hex
    now = datetime.now().isoformat(timespec="seconds")
    job = CrawlJob(job_id=job_id, domain=domain, site_url=site_url, status="queued", started_at=now)

    with _JOBS_LOCK:
        _JOBS[job_id] = job
        _evict_old_jobs(domain)

    thread = threading.Thread(
        target=_run_job,
        args=(job, depth, max_pages, formats or ["md", "html", "json"], compare, auth_path),
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
    except OSError as exc:
        logger.error("クロールジョブ起動失敗: job_id=%s, %s", job.job_id, exc)
        _update(job, status="failed", exit_code=-1, log_tail=str(exc))


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
