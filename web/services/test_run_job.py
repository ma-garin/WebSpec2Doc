"""テスト実行（ステップ実行 / テストケース実行 / スケジュール実行）のジョブ基盤。

ステップ実行・テストケース実行・スケジュール実行はいずれも最終的に
`playwright_executor.run_playwright()` を呼ぶ同じ処理であり、成果物の置き場
（`output/<domain>/qa_process/`）も共有する。それぞれが独立にスレッドを起こすと
同じディレクトリへ同時に書き込み、レポートが混ざって「どの実行の結果か分からない」
状態になる。そのため実行要求はすべてこのモジュールのキューへ集約し、
ドメイン単位で 1 本ずつ直列に流す。

既知の制約（`web/services/job_queue.py` と同じ）:
    ジョブの状態はプロセス内のメモリ（`_JOBS`）に持つ。gunicorn などで
    複数ワーカープロセスを立てた場合、**プロセスごとに別のキューができる**ため、
    ジョブの参照・キャンセル・ドメイン排他はワーカーをまたいで効かない。
    永続化が必要な証跡は `output/<domain>/qa_process/test_run_history.jsonl`
    （全プロセスから追記される）と `run_store` のスナップショットに寄せてある。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Any

from web.config import OUTPUT_DIR

logger = logging.getLogger(__name__)

#: これ以上状態が進まない終端。ここへ入ったジョブはドメイン排他の対象外になる。
TERMINAL_STATUSES = frozenset({"complete", "failed", "cancelled"})

#: メモリ上に保持するジョブ数の上限（ドメインあたり）。job_queue.py と同じ方針。
#: 永続的な履歴は test_run_history.jsonl 側に残るため、ここは画面表示用の直近分だけ持つ。
MAX_JOBS_PER_DOMAIN = 20

#: エラー文字列の保持上限（レポート・jsonl が肥大化しないように切り詰める）。
MAX_ERROR_CHARS = 2000

#: 履歴 jsonl のファイル名（output/<domain>/qa_process/ 配下）。
HISTORY_FILENAME = "test_run_history.jsonl"

#: kind -> run_store のイベント名。run_store 側の語彙に合わせる。
_EVENT_BY_KIND = {
    "steps": "step_run",
    "testcase": "testcase_run",
    "schedule": "scheduled_test",
}

#: ジョブの status -> run_notifier の status 語彙。両者の語彙を無理に揃えない
#: （auto_run_job.py の `_RUN_NOTIFY_STATUS` と同じ考え方）。
_NOTIFY_STATUS = {
    "complete": "completed",
    "failed": "failed",
    "cancelled": "cancelled",
}

# --- モジュール状態（すべて _LOCK / _COND の保護下で触る） ---------------------
_LOCK = threading.RLock()
#: キュー待ち・実行中・終了済みを含む全ジョブ。job_id -> TestRunJob
_JOBS: dict[str, TestRunJob] = {}
#: 実行待ちの FIFO。ワーカーはここから取り出す。
_QUEUE: deque[str] = deque()
#: 新しいジョブの投入をワーカーへ知らせる。ロックは _LOCK を共有する。
_COND = threading.Condition(_LOCK)
#: 起動済みのワーカースレッド。start_workers() を冪等にするための記録。
_WORKERS: list[threading.Thread] = []
#: domain -> その domain のジョブが使った output_root。
#: list_jobs() は output_root を引数に取らない契約なので、履歴 jsonl の在り処を
#: ここから引く（テナントスコープされた出力先に追随するため）。
_DOMAIN_ROOTS: dict[str, Path] = {}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clip(text: str) -> str:
    text = str(text or "")
    return text if len(text) <= MAX_ERROR_CHARS else text[:MAX_ERROR_CHARS]


class DomainBusyError(RuntimeError):
    """同一ドメインで既に実行中/待機中のジョブがある。既存 job_id を name 属性に持つ。

    呼び出し元（ルート）は `exc.name` をそのまま画面へ出し、「どの実行が
    ぶつかっているか」を利用者に名指しで伝えられるようにする。
    「今は実行できません」だけでは、利用者は待てばよいのか壊れたのか判断できない。
    """

    def __init__(self, message: str, job_id: str):
        super().__init__(message)
        #: 衝突相手の job_id。属性名 `name` は呼び出し側の契約。
        self.name = job_id
        #: 可読性のための別名（`name` と同じ値）。
        self.job_id = job_id


@dataclass
class TestRunJob:
    """1 回のテスト実行要求。

    終端処理（スナップショット・通知・履歴追記）は必ずワーカーの finally
    1 箇所だけで行う。AutoRunJob は終端遷移が複数モジュールへ分散しているため
    `__setattr__` フックで通知を拾っているが、TestRunJob は終端が
    `_run_job()` の finally しかないので**そのフックは踏襲しない**。
    フックは「どこで状態が変わっても拾える」代わりに、発火条件が状態の組み合わせに
    依存して読みにくくなる。発火点が 1 箇所なら素直に書いた方が壊れにくい。
    """

    job_id: str
    domain: str
    kind: str  # "steps" | "testcase" | "schedule"
    status: str  # queued | running | complete | failed | cancelled
    spec_path: str
    output_dir: str  # 通常 output/<domain>/qa_process
    environment: str = ""
    requested_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    #: run_playwright の戻り値のサマリ（passed/failed/total/flaky/duration_ms/ok/error）
    result: dict[str, Any] = field(default_factory=dict)
    #: run_store.snapshot_run() の戻り値。空なら退避できる成果物が無かった。
    run_id: str = ""
    error: str = ""
    #: scheduler 起点なら {"trigger": "scheduled"|"manual", ...}
    schedule_context: dict[str, Any] = field(default_factory=dict)

    # --- 内部状態（to_dict() には出さない） ---
    #: 実行中の子プロセス（Popen）。cancel から見えないと止められない。
    _proc: Any = field(default=None, init=False, repr=False, compare=False)
    _cancelled: bool = field(default=False, init=False, repr=False, compare=False)
    #: 終端処理まで完了したら set される。テスト・同期待ちの呼び出し元が使う。
    _done_event: Any = field(default_factory=threading.Event, init=False, repr=False, compare=False)
    #: run_playwright へ渡す実引数（enqueue 時に確定させ、ワーカーはそのまま展開する）。
    _run_kwargs: dict[str, Any] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def to_dict(self) -> dict[str, Any]:
        """API/画面向けの辞書。`_` 始まりの内部フィールドは含めない。"""
        return {
            f.name: getattr(self, f.name) for f in fields(self) if not f.name.startswith("_")
        }

    def elapsed_sec(self) -> int:
        """開始から終了（未終了なら現在）までの経過秒。"""
        if not self.started_at:
            return 0
        try:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.finished_at) if self.finished_at else datetime.now()
            return max(0, int((end - start).total_seconds()))
        except Exception:
            return 0

    def register_proc(self, proc: Any) -> None:
        """実行中の子プロセスを登録する。

        登録が無い子プロセスは cancel_job() から見えず、中止しても走り続ける。
        また cancel_job() との競合（登録の直前に中止された場合）に備え、
        登録時点で中止済みなら即座に終了させる（auto_run_job.py と同じ形）。
        """
        self._proc = proc
        if self._cancelled:
            try:
                proc.terminate()
            except Exception:
                pass

    def wait(self, timeout: float | None = None) -> bool:
        """終端処理の完了を待つ。完了したら True。"""
        return self._done_event.wait(timeout)


# --- ワーカー数 ---------------------------------------------------------------


def worker_count() -> int:
    """起動するワーカースレッド数。環境変数 `WEBSPEC2DOC_TEST_WORKERS`（既定 1）。

    既定を 1 にしているのは playwright_executor.run_playwright() の `workers`
    引数と同じ理由による:

        「並列実行数。既定は1（対象サイトへ同時多数アクセスしないための配慮）。」

    テスト実行は他人が運用している実サイトを叩く。ジョブを並列に流すと
    1 実行あたりの workers=1 を守っていても、サイトから見た同時接続数は
    ジョブ数の分だけ増える。増やしてよいのは、対象が自社の検証環境で
    負荷をかけてよいと確認できている場合だけ。
    暴走を防ぐため 1〜4 にクランプする。
    """
    raw = (os.environ.get("WEBSPEC2DOC_TEST_WORKERS") or "").strip()
    try:
        value = int(raw) if raw else 1
    except ValueError:
        logger.warning("WEBSPEC2DOC_TEST_WORKERS が数値ではありません: %r（1 を使います）", raw)
        value = 1
    return max(1, min(4, value))


def start_workers() -> None:
    """ワーカースレッドを起動する。冪等（二重起動しない）。

    create_app() から呼ばれる。テストや再入で複数回呼ばれても、
    既に生きているワーカーがある限り新しいスレッドは作らない。
    """
    with _LOCK:
        alive = [t for t in _WORKERS if t.is_alive()]
        _WORKERS[:] = alive
        need = worker_count() - len(alive)
        for index in range(need):
            thread = threading.Thread(
                target=_worker_loop,
                daemon=True,
                name=f"TestRunWorker-{len(_WORKERS) + index}",
            )
            _WORKERS.append(thread)
            thread.start()


# --- 公開 API -----------------------------------------------------------------


def enqueue_test_run(
    *,
    domain: str,
    kind: str,
    spec_path: Path,
    output_dir: Path,
    output_root: Path,
    environment: str = "",
    per_test_timeout_sec: int = 30,
    retries: int = 1,
    update_snapshots: bool = False,
    headed: bool = False,
    base_url: str | None = None,
    storage_state: Path | None = None,
    snapshot_dir: Path | None = None,
    egress_policy: Any = None,
    schedule_context: dict | None = None,
) -> TestRunJob:
    """テスト実行をキューへ投入し、ジョブを返す。

    同一 domain で running または queued のジョブがあれば `DomainBusyError` を送出する。
    理由: ステップ実行・テストケース実行・スケジュール実行・AutoRun はいずれも
    `output/<domain>/qa_process/` 配下の成果物（playwright_report.json、
    スクリーンショット、trace）を共有しており、同時に走らせると後から書いた方が
    前の結果を上書きする。「実行したのに結果が別の実行のもの」は検知が難しく、
    利用者は誤った結果を正しいものとして受け取ってしまう。

    Raises:
        DomainBusyError: 同一ドメインで実行中/待機中のジョブがある。
    """
    if kind not in _EVENT_BY_KIND:
        raise ValueError(f"kind は {sorted(_EVENT_BY_KIND)} のいずれか: {kind!r}")

    job = TestRunJob(
        job_id=uuid.uuid4().hex[:12],
        domain=domain,
        kind=kind,
        status="queued",
        spec_path=str(spec_path),
        output_dir=str(output_dir),
        environment=environment,
        requested_at=_now(),
        schedule_context=dict(schedule_context or {}),
    )
    # run_playwright の実引数名に合わせる（playwright_executor.run_playwright 参照）。
    job._run_kwargs = {
        "spec_path": Path(spec_path),
        "output_dir": Path(output_dir),
        "per_test_timeout_sec": per_test_timeout_sec,
        "retries": retries,
        "update_snapshots": update_snapshots,
        "headed": headed,
        "base_url": base_url,
        "storage_state": storage_state,
        "snapshot_dir": snapshot_dir,
        "egress_policy": egress_policy,
    }

    with _COND:
        busy = _busy_job_id(domain)
        if busy:
            raise DomainBusyError(
                f"ドメイン {domain} では実行中/待機中のテストがあります（job_id={busy}）。"
                "完了を待つか、そのジョブを中止してください。",
                busy,
            )
        _DOMAIN_ROOTS[domain] = Path(output_root)
        _JOBS[job.job_id] = job
        _evict_old_jobs(domain)
        _QUEUE.append(job.job_id)
        _COND.notify()

    # 呼び出し元が start_workers() を忘れていても実行が始まらない事態を避ける
    # （create_app() で起動済みなら冪等に何もしない）。
    start_workers()
    return job


def get_job(job_id: str) -> TestRunJob | None:
    """job_id からジョブを引く。メモリ上に無ければ None。"""
    with _LOCK:
        return _JOBS.get(job_id)


def list_jobs(domain: str, limit: int = 20) -> list[dict]:
    """domain のジョブをメモリと履歴 jsonl からマージし、新しい順に返す。

    メモリ側（実行中・直近）が優先。同じ job_id が jsonl にもある場合は
    メモリ側を採用する（実行中の最新状態を古い記録で上書きしないため）。
    """
    with _LOCK:
        memory = [job.to_dict() for job in _JOBS.values() if job.domain == domain]
    merged: dict[str, dict] = {}
    for row in _read_history(domain):
        job_id = str(row.get("job_id") or "")
        if job_id:
            merged[job_id] = row
    for row in memory:
        merged[str(row.get("job_id") or "")] = row
    rows = sorted(merged.values(), key=_sort_key, reverse=True)
    return rows[: max(0, int(limit))]


def cancel_job(job_id: str) -> str:
    """ジョブを中止する。戻り値は "cancelled" | "already_finished" | "not_found"。

    queued のジョブは即座に cancelled にし、ワーカーは取り出し時に捨てる
    （deque からの抜き取りは O(n) で、取り出し時の判定と二重管理になるため行わない）。
    running のジョブは登録済みの子プロセスを terminate し、5 秒待って kill する。
    """
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return "not_found"
        if job.status in TERMINAL_STATUSES:
            return "already_finished"
        job._cancelled = True
        was_queued = job.status == "queued"
        proc = job._proc

    if was_queued:
        # 実行前に確定させる。ワーカーが拾うまで queued に見え続けると、
        # 画面上は「中止したのにまだ待っている」ことになる。
        with _LOCK:
            job.status = "cancelled"
        # 終端処理（履歴追記など）はワーカーの finally 1 箇所に集約するため、
        # ここでは行わない。ワーカーが取り出した時点で記録される。
        with _COND:
            _COND.notify()
        return "cancelled"

    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                logger.warning("子プロセスの強制終了に失敗: job_id=%s", job_id, exc_info=True)
    return "cancelled"


def queued_position(job_id: str) -> int:
    """待ち順を返す。0 = 実行中、またはキューの先頭。未知/終了済みは -1。"""
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None or job.status in TERMINAL_STATUSES:
            return -1
        if job.status == "running":
            return 0
        try:
            return list(_QUEUE).index(job_id)
        except ValueError:
            return -1


# --- 内部処理 -----------------------------------------------------------------


def _busy_job_id(domain: str) -> str:
    """_LOCK 保持中に呼ぶ。domain で実行中/待機中のジョブ ID（無ければ空文字）。"""
    for job in _JOBS.values():
        if job.domain == domain and job.status in ("queued", "running"):
            return job.job_id
    return ""


def _evict_old_jobs(domain: str) -> None:
    """_LOCK 保持中に呼ぶ。domain の終端済みジョブを古い順に上限まで削除する。

    job_queue.py:101 の `_evict_old_jobs` と同じ方針だが、実行中/待機中のジョブは
    消さない（消すと cancel も参照もできない幽霊ジョブになるため）。
    """
    finished = sorted(
        [jid for jid, j in _JOBS.items() if j.domain == domain and j.status in TERMINAL_STATUSES],
        key=lambda jid: _JOBS[jid].requested_at,
    )
    total = sum(1 for j in _JOBS.values() if j.domain == domain)
    while total >= MAX_JOBS_PER_DOMAIN and finished:
        del _JOBS[finished.pop(0)]
        total -= 1


def _worker_loop() -> None:
    """キューからジョブを 1 件ずつ取り出して実行する（daemon スレッド）。"""
    while True:
        with _COND:
            while not _QUEUE:
                _COND.wait()
            job_id = _QUEUE.popleft()
            job = _JOBS.get(job_id)
        if job is None:
            # evict 済み。記録も残らないが、参照先が無いので何もできない。
            continue
        try:
            _run_job(job)
        except Exception:
            # ここまで例外が来るのは _run_job の finally 自体が壊れた場合のみ。
            # ワーカースレッドを落とすと以降の全ジョブが永久に queued になる。
            logger.exception("テスト実行ワーカーで想定外の例外: job_id=%s", job.job_id)


def _run_job(job: TestRunJob) -> None:
    """1 ジョブを実行し、finally で終端処理をまとめて行う。"""
    started = False
    status = "failed"
    try:
        with _LOCK:
            if job._cancelled:
                # 待機中に中止された。実行はしないが、証跡は finally で残す。
                status = "cancelled"
                job.status = "cancelled"
                return
            job.status = "running"
            job.started_at = _now()
        started = True

        from web.services.playwright_executor import run_playwright

        result = run_playwright(on_proc=job.register_proc, **job._run_kwargs)
        job.result = dict(result or {})
        if job._cancelled:
            status = "cancelled"
        elif job.result.get("ok"):
            status = "complete"
        else:
            status = "failed"
            job.error = _clip(job.result.get("error") or "")
    except Exception as exc:
        status = "cancelled" if job._cancelled else "failed"
        job.error = _clip(f"{type(exc).__name__}: {exc}")
        logger.exception("テスト実行に失敗: job_id=%s", job.job_id)
    finally:
        _finalize(job, status=status, started=started)


def _finalize(job: TestRunJob, *, status: str, started: bool) -> None:
    """終端処理。①スナップショット ②通知 ③履歴追記 ④完了通知の順に行う。

    **各ステップは個別に try/except で囲む。**1 つ落ちても後続を止めない
    （例えば snapshot_run が失敗しただけで履歴 jsonl まで書かれないと、
    「実行した記録そのものが無い」状態になり、原因調査ができなくなる）。
    """
    with _LOCK:
        job.status = status
        job.finished_at = _now()
    summary = _summary(job)
    output_root = _DOMAIN_ROOTS.get(job.domain, OUTPUT_DIR)

    # ① 成果物のスナップショット（実行していないジョブは対象外。
    #    走っていないのに前回の成果物を退避すると、実行回が水増しされる）。
    if started:
        try:
            from web.services.run_store import snapshot_run

            run_id = snapshot_run(
                output_root,
                job.domain,
                event=_EVENT_BY_KIND.get(job.kind, "testcase_run"),
                status=status,
                summary=summary,
            )
            job.run_id = run_id or ""
        except Exception:
            logger.warning("実行回の退避に失敗: job_id=%s", job.job_id, exc_info=True)

    # ② Slack 通知。通知の失敗で実行が失敗扱いになってはならないため、
    #    呼び出し全体を try/except で包む（TypeError も含めてここで受ける。
    #    キーワード追加の過渡期に握りつぶし専用の except を書くと、
    #    引数の不一致が恒久的に隠れてしまうので書かない）。
    if started:
        try:
            from web.services.run_notifier import notify_run_finished

            notify_run_finished(
                site_url=job.domain,
                run_kind=_EVENT_BY_KIND.get(job.kind, "testcase_run"),
                status=_NOTIFY_STATUS.get(status, "failed"),
                total=summary["total"],
                passed=summary["passed"],
                failed=summary["failed"],
                skipped=int(job.result.get("skipped") or 0),
                elapsed_sec=job.elapsed_sec(),
                error=job.error,
                domain=job.domain,
                output_root=output_root,
            )
        except Exception:
            logger.warning("実行完了通知に失敗: job_id=%s", job.job_id, exc_info=True)

    # ③ 履歴 jsonl へ 1 行追記（永続する唯一の記録）。
    try:
        _append_history(job, summary=summary, output_root=output_root)
    except Exception:
        logger.warning("実行履歴の追記に失敗: job_id=%s", job.job_id, exc_info=True)

    # ④ 待っている呼び出し元を解放する。ここまで来たら必ず set する。
    try:
        job._done_event.set()
    except Exception:
        logger.warning("完了イベントの通知に失敗: job_id=%s", job.job_id, exc_info=True)


def _summary(job: TestRunJob) -> dict[str, int]:
    """run_playwright の結果から、記録・通知で共通に使うサマリを作る。"""
    result = job.result if isinstance(job.result, dict) else {}
    return {
        "total": int(result.get("total") or 0),
        "passed": int(result.get("passed") or 0),
        "failed": int(result.get("failed") or 0),
        "flaky": int(result.get("flaky") or 0),
    }


def _history_path(domain: str, output_root: Path | None = None) -> Path:
    root = Path(output_root) if output_root is not None else _DOMAIN_ROOTS.get(domain, OUTPUT_DIR)
    return root / domain / "qa_process" / HISTORY_FILENAME


def _append_history(job: TestRunJob, *, summary: dict[str, int], output_root: Path) -> None:
    """test_run_history.jsonl へ 1 行追記する。"""
    path = _history_path(job.domain, output_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "job_id": job.job_id,
        "kind": job.kind,
        "status": job.status,
        "run_id": job.run_id,
        "environment": job.environment,
        "requested_at": job.requested_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "summary": summary,
        "error": job.error,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_history(domain: str) -> list[dict]:
    """履歴 jsonl を読む。壊れた行は捨てる（1 行の破損で履歴全体を失わない）。"""
    path = _history_path(domain)
    if not path.is_file():
        return []
    rows: list[dict] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except OSError:
        logger.warning("実行履歴の読み込みに失敗: %s", path, exc_info=True)
    return rows


def _sort_key(row: dict) -> str:
    """新しい順に並べるためのキー。要求時刻を基準にする。"""
    return str(row.get("requested_at") or row.get("started_at") or row.get("finished_at") or "")
