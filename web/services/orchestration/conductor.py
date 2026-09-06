"""指揮者（O2）。目標の段を決定的に 1 本ずつ進める。

段の並びは goals.py の定数表にあり、ここは「走らせてよいか → 走らせる →
終わるまで見る → 次へ」だけを行う。次に何を呼ぶかを考えさせない。

進め方は 05（web/services/healing/orchestrator.py）に揃える。錠つきのグローバル
dict と daemon スレッドで進め、画面は永続化された JSON を読む（保存しない進捗は
存在しないのと同じ）。再起動でスレッドが消えた実行は reap_orphans で失敗として
書き戻す（waiting_human はスレッドが無いのが正常なので回収しない）。
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from web.services.orchestration import goals, registry, run_store
from web.services.orchestration.ports import STEP_STATES, Context, StepStatus
from web.services.orchestration.run_store import ConductorRun, StepRecord

logger = logging.getLogger(__name__)
#: 非同期の段（05）を見に行く間隔と、1 段に許す時間（超えたら失敗として畳む）。
POLL_INTERVAL_SEC = 10
STEP_TIMEOUT_SEC = 7200

#: 実行の状態。段と同じ語彙を使う（語彙の出どころは ports.STEP_STATES だけ）。
RUN_STATES: tuple[str, ...] = STEP_STATES
TERMINAL_STATUSES = frozenset({"succeeded", "failed", "skipped", "waiting_human", "cancelled"})

#: 「進めるスレッドが居るのが正常」な状態だけを回収の対象にする。
ORPHAN_CANDIDATE_STATUSES = frozenset({"queued", "running"})

ORPHAN_RUN_ERROR = "指揮の途中でプロセスが止まりました（サーバの再起動など）。もう一度実行してください"

_CANCEL_NOTE = "利用者の指示で中止しました"

_RUNS: dict[str, ConductorRun] = {}
_RUNS_LOCK = threading.RLock()

#: 「終わっていない実行を確認 → 無ければ始める」を割り込ませないための錠。
_START_LOCK = threading.Lock()

_CANCEL: dict[str, threading.Event] = {}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _add_log(run: ConductorRun, message: str) -> None:
    run.log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
    if len(run.log) > 500:
        del run.log[: len(run.log) - 500]


def _save(out_dir: Path, run: ConductorRun, *, note: str = "") -> None:
    """状態を 1 か所で保存する。ここを通した遷移は必ず永続化まで 1 セット。"""
    if note:
        _add_log(run, note)
    with _RUNS_LOCK:
        _RUNS[run.run_id] = run
    run_store.save_run(out_dir, run)


def _finish(out_dir: Path, run: ConductorRun, status: str, *, error: str = "",
            human_action: str = "", note: str = "") -> None:
    run.status = status
    run.error = error or run.error
    run.human_action = human_action
    run.finished_at = run.finished_at or _now_iso()
    _save(out_dir, run, note=note)


def _cancelled(run_id: str) -> bool:
    with _RUNS_LOCK:
        event = _CANCEL.get(run_id)
    return event is not None and event.is_set()  # 段の切れ目と 10 秒ごとに見る


def start(*, out_dir: Path, domain: str, goal: str, project_id: str = "",
          actor: str = "", params: Mapping[str, Any] | None = None) -> ConductorRun:
    """指揮を 1 本起こす。目標が未対応なら日本語の ValueError。"""
    site = str(domain or "").strip()
    if not site:
        raise ValueError("サイトを指定してください")
    agents = [registry.get_agent(name) for name in goals.steps_for(goal)]
    run = ConductorRun(
        run_id=f"cond-{uuid.uuid4().hex[:12]}", domain=site, goal=str(goal).strip(),
        project_id=str(project_id or "").strip(), status="queued",
        steps=[StepRecord(name=a.name, label=a.label) for a in agents],
        started_at=_now_iso(), actor=actor, params=dict(params or {}),
    )
    with _RUNS_LOCK:
        _CANCEL[run.run_id] = threading.Event()
    label = goals.GOAL_LABELS.get(run.goal, run.goal)
    _save(out_dir, run, note=f"受付しました（目標: {label} / 実行者: {actor or '不明'}）")
    threading.Thread(target=_loop, args=(Path(out_dir), run),
                     name=f"conductor-{run.run_id}", daemon=True).start()
    return run


def _loop(out_dir: Path, run: ConductorRun) -> None:
    """段を順に進める。どの経路で抜けても必ず保存する。"""
    try:
        run.status = "running"
        _save(out_dir, run, note="指揮を始めます")
        for index, record in enumerate(run.steps):
            run.step_index = index
            if _cancelled(run.run_id):
                _finish(out_dir, run, "cancelled", note=_CANCEL_NOTE)
                return
            if not _run_step(out_dir, run, record):
                return
        _finish(out_dir, run, "succeeded", note="すべての段が終わりました")
    except Exception as exc:  # noqa: BLE001 - 例外で実行を宙づりにしない
        logger.exception("指揮 %s が異常終了しました", run.run_id)
        _finish(out_dir, run, "failed", error=f"指揮の途中で問題が起きました: {exc}",
                note="指揮の途中で問題が起きました")
    finally:
        with _RUNS_LOCK:
            _CANCEL.pop(run.run_id, None)
        try:
            run_store.save_run(out_dir, run)
        except Exception:  # noqa: BLE001 - 保存の失敗でスレッドを落とさない
            logger.warning("指揮 %s の保存に失敗しました", run.run_id, exc_info=True)


def _run_step(out_dir: Path, run: ConductorRun, record: StepRecord) -> bool:
    """1 段を進める。次の段へ進んでよければ True。"""
    agent = registry.get_agent(record.name)
    ctx = Context(
        out_dir=out_dir, domain=run.domain, project_id=run.project_id, params=run.params,
        actor=run.actor,
        log=lambda message: _save(out_dir, run, note=f"{agent.label}: {message}"),
    )
    record.status = "running"
    record.started_at = _now_iso()
    _save(out_dir, run, note=f"{agent.label}を始めます")

    readiness = agent.ready(ctx)
    if not readiness.ok:
        # 人の承認・準備は代行しない。待ちとして表に出し、そこで止める。
        return _settle(out_dir, run, record, "waiting_human", label=agent.label,
                       summary=readiness.detail or "人の作業を待ちます",
                       human_action=readiness.human_action)

    result = agent.run(ctx)
    record.handle = result.handle
    record.artifacts = {str(k): str(v) for k, v in dict(result.artifacts).items()}
    record.evidence = [str(item) for item in result.evidence]
    if result.status != "running":
        return _settle(out_dir, run, record, result.status, label=agent.label,
                       summary=result.summary, error=result.error,
                       human_action=result.human_action)
    status = _await_step(out_dir, run, record, agent, ctx)
    record.artifacts.update({str(k): str(v) for k, v in dict(status.artifacts).items()})
    return _settle(out_dir, run, record, status.state, label=agent.label,
                   summary=status.summary or result.summary, error=status.error,
                   human_action=status.human_action)


def _await_step(out_dir: Path, run: ConductorRun, record: StepRecord,
                agent: Any, ctx: Context) -> StepStatus:
    """非同期の段を 10 秒間隔で見る。上限 2 時間。"""
    deadline = time.monotonic() + STEP_TIMEOUT_SEC
    last_state = ""
    while True:
        if _cancelled(run.run_id):
            note = _CANCEL_NOTE
            if record.name == "healing":
                # 05 の実行は 05 の持ち物。指揮者が代わりに止めない。
                note += "（オートヒーリング側の実行は動いています。"
                note += "止めるには 05 の画面で操作してください）"
            return StepStatus(state="cancelled", label="中止", summary=note)
        try:
            status = agent.status(ctx, record.handle)
        except Exception as exc:  # noqa: BLE001 - 例外は握らず結果として返す
            return StepStatus(state="failed", label="状態を取得できません",
                              error=f"{agent.label}の状態を取得できませんでした: {exc}")
        if status.state != last_state:
            _save(out_dir, run, note=f"{agent.label}: {status.label or status.state}")
            last_state = status.state
        if status.state != "running":
            return status
        if time.monotonic() >= deadline:
            message = f"{agent.label} が 2 時間で終わりませんでした"
            return StepStatus(state="failed", label="時間切れ", summary=message, error=message)
        time.sleep(POLL_INTERVAL_SEC)


def _settle(out_dir: Path, run: ConductorRun, record: StepRecord, status: str, *,
            label: str = "", summary: str = "", error: str = "",
            human_action: str = "") -> bool:
    """段の結果を書き、実行を続けてよいかを返す。"""
    record.status = status
    record.summary = summary
    record.error = error
    record.human_action = human_action
    record.finished_at = _now_iso()
    note = f"{label}: {summary or error or status}"
    if status in ("succeeded", "skipped"):
        _save(out_dir, run, note=note)
        return True
    if status == "waiting_human":
        _finish(out_dir, run, "waiting_human", human_action=human_action, note=note)
    elif status == "cancelled":
        _finish(out_dir, run, "cancelled", note=note)
    else:
        _finish(out_dir, run, "failed", error=error or summary or "段が失敗しました", note=note)
    return False


def get(out_dir: Path, run_id: str) -> ConductorRun | None:
    with _RUNS_LOCK:
        run = _RUNS.get(run_id)
    return run if run is not None else run_store.load_run(out_dir, run_id)


def list_summaries(out_dir: Path, domain: str = "", limit: int = 50) -> list[dict[str, Any]]:
    stored = run_store.list_runs(out_dir, domain=domain, limit=limit)
    with _RUNS_LOCK:
        merged: dict[str, ConductorRun] = {run.run_id: run for run in stored}
        for run_id, run in _RUNS.items():
            if domain and run.domain != domain:
                continue
            merged[run_id] = run  # メモリ側が最新なので永続化分を上書きする
    ordered = sorted(merged.values(), key=lambda r: r.started_at or "", reverse=True)[:limit]
    return [run_store.run_summary(run) for run in ordered]


def reap_orphans(out_dir: Path, *, domain: str = "") -> list[str]:
    """進める者がいなくなった実行を失敗として片付け、その run_id を返す。

    放置すると has_active_run が永久に True を返し、そのサイトの指揮は二度と
    起きない。waiting_human は対象にしない（人待ちは正常な姿）。
    """
    try:
        stored = run_store.list_runs(out_dir, domain=domain, limit=200)
    except Exception:  # noqa: BLE001 - 片付けの失敗で呼び出し元を止めない
        logger.warning("指揮の一覧を読めなかったため片付けを飛ばしました", exc_info=True)
        return []
    reaped: list[str] = []
    for run in stored:
        if run.status not in ORPHAN_CANDIDATE_STATUSES:
            continue
        with _RUNS_LOCK:
            if run.run_id in _RUNS:
                continue  # このプロセスのスレッドが進めている
        run.status = "failed"
        run.error = ORPHAN_RUN_ERROR
        run.finished_at = run.finished_at or _now_iso()
        _add_log(run, ORPHAN_RUN_ERROR)
        try:
            run_store.save_run(out_dir, run)  # 読み直した別インスタンスなので _RUNS に入れない
        except Exception:  # noqa: BLE001 - 1 件の失敗で他を諦めない
            logger.warning("止まった指揮 %s の保存に失敗しました", run.run_id, exc_info=True)
            continue
        reaped.append(run.run_id)
    return reaped


def has_active_run(out_dir: Path, domain: str) -> bool:
    """まだ終わっていない指揮があるか。判定の前に止まった実行を片付ける。"""
    try:
        reap_orphans(out_dir, domain=domain)
        summaries = list_summaries(out_dir, domain=domain, limit=200)
    except Exception:  # noqa: BLE001 - 判定できないときは走らせない側に倒す
        logger.warning("指揮の一覧を取得できませんでした", exc_info=True)
        return True
    return any(str(s.get("status") or "") not in TERMINAL_STATUSES for s in summaries)


def start_if_idle(*, out_dir: Path, domain: str, goal: str, project_id: str = "",
                  actor: str = "", params: Mapping[str, Any] | None = None) -> ConductorRun | None:
    """終わっていない指揮が無ければ 1 本起こす。あれば None。

    目標の検証は錠の外で先に行う（走行中でも未対応の目標は 400 で返す）。
    """
    goals.steps_for(goal)
    with _START_LOCK:
        if has_active_run(out_dir, domain):
            return None
        return start(out_dir=out_dir, domain=domain, goal=goal,
                     project_id=project_id, actor=actor, params=params)


def cancel(out_dir: Path, run_id: str) -> bool:
    """次の確認で止まるように合図する。走っている段そのものは止めない。"""
    with _RUNS_LOCK:
        event = _CANCEL.get(run_id)
        if event is None:
            return False
        event.set()
    return True
