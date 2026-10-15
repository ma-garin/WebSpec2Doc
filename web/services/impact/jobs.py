"""分析ジョブ（DD-005）。スレッドで run.analyze を回し、進捗を jobs 表に書く。

保存先（テナント別 impact.db）は呼び出し側がスレッド開始前に解決して db_file で渡す（request 文脈に依存しない）。
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from web.services.impact.engine import run

try:
    from web.services.impact.repo.errors import ImpactError
except ImportError:  # repo が未配置の環境（単体テスト）
    class ImpactError(Exception):  # type: ignore[no-redef]
        def __init__(self, message: str, status: int = 400):
            super().__init__(message)
            self.message, self.status = message, status

log = logging.getLogger(__name__)
_threads: dict[str, threading.Thread] = {}
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(db_file: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_file), timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _row(conn, job_id: str) -> dict:
    r = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if r is None:
        raise ImpactError("分析ジョブが見つかりません。変更要求の画面を開き直してください。", 404)
    d = dict(r)
    d["engine"] = json.loads(d["engine"]) if d.get("engine") else None
    return d


def _update(conn, job_id: str, **fields) -> None:
    with conn:
        conn.execute(f"UPDATE jobs SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?", [*fields.values(), job_id])


def _set_cr(conn, cr_id: str, status: str) -> None:
    with conn:
        conn.execute("UPDATE change_requests SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), cr_id))


def _work(db_file: Path, job_id: str, sid: str, cr_code: str, cr_id: str, actor: str, confirm_send: bool) -> None:
    conn = _connect(db_file)
    try:
        _update(conn, job_id, status="running", stage="changes", progress=0, started_at=_now())

        def progress_cb(stage: str, pct: int) -> None:
            _update(conn, job_id, stage=stage, progress=int(pct))

        def cancelled_cb() -> bool:
            r = conn.execute("SELECT cancel FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return bool(r and r[0])

        result = run.analyze(conn, sid, cr_code, actor, progress_cb, cancelled_cb, allow_send=confirm_send)
        if result == "cancelled":
            _update(conn, job_id, status="cancelled", message="分析を中止しました。結果は保存していません。",
                    finished_at=_now())
            _set_cr(conn, cr_id, "draft")
            return
        _update(conn, job_id, status="done", stage="done", progress=100, finished_at=_now(),
                message=f"影響 {result['counts']['impacts']} 件を見つけました。",
                engine=json.dumps(result["engine"], ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 - スレッド内の失敗はすべて jobs 表へ記録する
        log.exception("影響度分析のジョブが失敗しました: job=%s", job_id)
        msg = str(exc) if isinstance(exc, run.AnalyzeError) else "分析に失敗しました。時間をおいて再度分析してください。"
        try:
            _update(conn, job_id, status="failed", message=msg, finished_at=_now())
            _set_cr(conn, cr_id, "draft")
        except sqlite3.Error:
            log.exception("ジョブの失敗を記録できませんでした: job=%s", job_id)
    finally:
        conn.close()
        with _lock:
            _threads.pop(job_id, None)


def start(sid: str, cr_code: str, actor: str, db_file: Path, confirm_send: bool = False) -> dict:
    """ジョブを作りスレッドで分析する。同じ変更要求で実行中があれば 409。"""
    db_file = Path(db_file)
    conn = _connect(db_file)
    try:
        cr = conn.execute("SELECT id FROM change_requests WHERE system_id = ? AND code = ?", (sid, cr_code)).fetchone()
        if cr is None:
            raise ImpactError("変更要求が見つかりません。一覧から選び直してください。", 404)
        busy = conn.execute("SELECT 1 FROM jobs WHERE cr_id = ? AND status IN ('queued','running')", (cr["id"],)).fetchone()
        if busy:
            raise ImpactError("この変更要求は分析中です。終わるまで待つか、中止してから再度分析してください。", 409)
        job_id = uuid.uuid4().hex[:12]
        with conn:
            conn.execute("INSERT INTO jobs(id, cr_id, status, stage, progress, message, cancel)"
                         " VALUES(?,?,?,?,?,?,0)", (job_id, cr["id"], "queued", "queued", 0, ""))
        _set_cr(conn, cr["id"], "analyzing")
        job = _row(conn, job_id)
    finally:
        conn.close()
    t = threading.Thread(target=_work, args=(db_file, job_id, sid, cr_code, job["cr_id"], actor, bool(confirm_send)),
                         name=f"impact-job-{job_id}", daemon=True)
    with _lock:
        _threads[job_id] = t
    t.start()
    return {k: job[k] for k in ("id", "status", "stage", "progress")}


def status(db_file: Path, job_id: str) -> dict:
    conn = _connect(Path(db_file))
    try:
        return _row(conn, job_id)
    finally:
        conn.close()


def cancel(db_file: Path, job_id: str) -> dict:
    """中止を要求する（cancel=1）。スレッドが次の段の境目で止まる。"""
    conn = _connect(Path(db_file))
    try:
        job = _row(conn, job_id)
        if job["status"] in ("queued", "running"):
            _update(conn, job_id, cancel=1)
        return _row(conn, job_id)
    finally:
        conn.close()


def wait(job_id: str, timeout: float = 30.0) -> None:
    """スレッドの終了を待つ（テスト・評価用）。"""
    with _lock:
        t = _threads.get(job_id)
    if t is not None:
        t.join(timeout)


def recover(conn) -> int:
    """起動時に実行中・待機中のジョブを中断扱いにし、変更要求を起票に戻す。戻した件数を返す。"""
    rows = conn.execute("SELECT id, cr_id FROM jobs WHERE status IN ('running','queued')").fetchall()
    with conn:
        for r in rows:
            conn.execute("UPDATE jobs SET status = 'interrupted', message = ?, finished_at = ? WHERE id = ?",
                         ("アプリの再起動で中断しました。再度分析してください。", _now(), r["id"]))
            conn.execute("UPDATE change_requests SET status = 'draft', updated_at = ? WHERE id = ? AND status = 'analyzing'",
                         (_now(), r["cr_id"]))
    return len(rows)
