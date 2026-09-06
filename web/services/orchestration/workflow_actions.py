"""指揮ワークフロー画面から押されたボタンを、既存のサービス関数へつなぐ層。

判断はしない。「押されたら何を呼ぶか」だけを持ち、状態の読み直しは
呼び出し側（routes/orchestration.py）が workflow_view.build に任せる。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from web.services.healing import project_store, report_doc
from web.services.healing import orchestrator as healing_orchestrator
from web.services.healing.types import HealingError
from web.services.orchestration import conductor, onboarding, workflow_view
from web.validation import _domain_of

logger = logging.getLogger(__name__)

_MIN_ROUNDS = 1
_MAX_ROUNDS = 5
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_BUSY = "このサイトの指揮はまだ終わっていません"

#: web.routes.auto_run.api_autorun_submit_input と同じ「ログインをスキップして
#: 続ける」入力。別タブで人がログイン済みという前提で、資格情報は代行しない。
_LOGIN_SKIP_INPUT = {"type": "login", "username": "", "password": "", "skip": True}


class ActionError(Exception):
    """利用者へそのまま見せてよい日本語の理由。呼び出し側が 400 にする。"""


def _clamp_rounds(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 1
    return max(_MIN_ROUNDS, min(_MAX_ROUNDS, n))


def _require_run(out_dir: Path, domain: str):
    run = workflow_view._latest_run(out_dir, domain)
    if run is None:
        raise ActionError("実行が見つかりません。")
    return run


def _current_record(run):
    idx = int(run.step_index or 0)
    return run.steps[idx] if 0 <= idx < len(run.steps) else None


# ─────────────────────────── start ───────────────────────────


def _start(out_dir: Path, domain: str, body: dict[str, Any], actor: str) -> str:
    url = str(body.get("url") or "").strip()
    if not url:
        raise ActionError("url を指定してください。")
    derived = _domain_of(url)
    if not derived:
        raise ActionError("url からサイトを取り出せませんでした。")
    if domain and domain != derived:
        raise ActionError("URL のサイトと domain が一致しません。")
    if conductor.has_active_run(out_dir, derived):
        raise ActionError(_BUSY)

    repo = str(body.get("repo") or "")
    verify_command = str(body.get("verify_command") or "")
    rounds = _clamp_rounds(body.get("rounds", 1))
    try:
        plan = onboarding.prepare(
            out_dir, url=url, repo=repo, verify_command=verify_command,
            rounds=rounds, actor=actor,
        )
    except ValueError as exc:
        raise ActionError(str(exc)) from exc

    params: dict[str, Any] = {"url": url, "rounds": rounds}
    for key in ("depth", "max_pages"):
        if key in body:
            try:
                params[key] = int(body[key])
            except (TypeError, ValueError):
                raise ActionError(f"{key} は整数で指定してください。") from None

    run = conductor.start_if_idle(
        out_dir=out_dir, domain=plan.domain, goal="onboard",
        project_id=plan.project_id, actor=actor, params=params,
    )
    if run is None:
        raise ActionError(_BUSY)


# ─────────────────────────── login_done ───────────────────────────
    return derived

def _login_done(out_dir: Path, domain: str, body: dict[str, Any], actor: str) -> None:
    run = _require_run(out_dir, domain)
    record = _current_record(run)
    if record is None or record.name != "docs" or run.status != "waiting_human":
        raise ActionError("いまはログイン待ちではありません。")

    from web.routes.auto_run import _JOBS as autorun_jobs
    from web.routes.auto_run import _JOBS_LOCK as autorun_lock

    with autorun_lock:
        job = autorun_jobs.get(str(record.handle or "").strip())
    if job is None:
        raise ActionError("観測の記録が見つかりません。")
    if str(getattr(job, "status", "") or "") != "awaiting_input":
        raise ActionError("いまはログイン入力待ちではありません。")

    job._input_data = dict(_LOGIN_SKIP_INPUT)
    job.input_request = None
    job.status = "crawling"
    job._input_event.set()


# ─────────────────────────── approve_viewpoints / return_viewpoints ───────────────────────────


def _approve_viewpoints(out_dir: Path, domain: str, body: dict[str, Any], actor: str) -> None:
    from autorun.stages import STATUS_APPROVED

    stage_id, _stage = workflow_view._pending_design_stage(out_dir, domain)
    if stage_id is None:
        raise ActionError("承認する観点がありません。")
    pipeline = workflow_view.load_pipeline(out_dir, domain)
    stage = pipeline.get(stage_id)
    if stage is None or not stage.can_approve:
        raise ActionError("この段階はまだ承認できません。全ての項目を承認してから、段階を承認してください。")

    pipeline = pipeline.replaced(stage.with_status(STATUS_APPROVED)).recorded(
        "approve", stage_id, f"{len(stage.items)}項目を承認", actor,
    )
    workflow_view.save_pipeline(out_dir, domain, pipeline)
    # 続き（テスト作成の残り→実行→分析）を観測をやり直さずに起こす。
    conductor.start_if_idle(out_dir=out_dir, domain=domain, goal="continue", actor=actor, params={})


def _return_viewpoints(out_dir: Path, domain: str, body: dict[str, Any], actor: str) -> None:
    from autorun.stages import STATUS_PENDING

    note = str(body.get("note") or "").strip()
    if not note:
        raise ActionError("差し戻すときは、どこを直してほしいかを書いてください。")
    stage_id, _stage = workflow_view._pending_design_stage(out_dir, domain)
    if stage_id is None:
        raise ActionError("差し戻す観点がありません。")
    pipeline = workflow_view.load_pipeline(out_dir, domain)
    stage = pipeline.get(stage_id)
    if stage is None:
        raise ActionError("差し戻す観点がありません。")
    # 段階を pending に戻して差し戻しの理由を記録する。02 には「note を読んで
    # 作り直す」処理が無いため、作り直しそのものは次にこの段階を生成する側
    # （02 の画面 / 再実行）に委ねる（詳細は impl_wf_backend.md の未解決）。
    pipeline = pipeline.replaced(stage.with_status(STATUS_PENDING)).recorded(
        "return", stage_id, note, actor,
    )
    workflow_view.save_pipeline(out_dir, domain, pipeline)


# ─────────────────────────── decide_report ───────────────────────────


def _decide_report(out_dir: Path, domain: str, body: dict[str, Any], actor: str) -> None:
    report_id = str(body.get("report_id") or "").strip()
    action = str(body.get("action") or "").strip()
    note = str(body.get("note") or "")
    if not report_id:
        raise ActionError("report_id を指定してください。")
    try:
        report = healing_orchestrator.decide_report(
            out_dir, report_id, action=action, note=note, actor=actor,
        )
    except HealingError as exc:
        raise ActionError(str(exc)) from exc

    run = workflow_view._latest_run(out_dir, domain)
    if run is None:
        return
    remaining = workflow_view._awaiting_reports(out_dir, report.project_id)
    if remaining:
        return
    total = _clamp_rounds(dict(run.params or {}).get("rounds", 1))
    last_healing = workflow_view._last_touched(run, "healing")
    try:
        current_no = int(workflow_view._round_no(last_healing))
    except ValueError:
        current_no = 1
    if current_no < total:
        conductor.start_if_idle(
            out_dir=out_dir, domain=domain, goal="daily", actor=actor, params={"rounds": 1},
        )


# ─────────────────────────── another_round / cancel / monitor ───────────────────────────


def _another_round(out_dir: Path, domain: str, body: dict[str, Any], actor: str) -> None:
    run = conductor.start_if_idle(
        out_dir=out_dir, domain=domain, goal="daily", actor=actor, params={"rounds": 1},
    )
    if run is None:
        raise ActionError(_BUSY)


def _cancel(out_dir: Path, domain: str, body: dict[str, Any], actor: str) -> None:
    run = _require_run(out_dir, domain)
    conductor.cancel(out_dir, run.run_id)


def _monitor(out_dir: Path, domain: str, body: dict[str, Any], actor: str) -> None:
    project = workflow_view._project_for(out_dir, domain)
    if project is None:
        raise ActionError("このサイトの接続先が見つかりません。")
    monitor_time = str(body.get("monitor_time") or "").strip()
    if monitor_time and not _TIME_RE.match(monitor_time):
        raise ActionError("monitor_time は HH:MM で指定してください。")
    updates = {"monitor_enabled": bool(body.get("monitor_enabled"))}
    if monitor_time:
        updates["monitor_time"] = monitor_time
    try:
        project_store.update_project(out_dir, project.project_id, updates)
    except HealingError as exc:
        raise ActionError(str(exc)) from exc


_HANDLERS = {
    "start": _start,
    "login_done": _login_done,
    "approve_viewpoints": _approve_viewpoints,
    "return_viewpoints": _return_viewpoints,
    "decide_report": _decide_report,
    "another_round": _another_round,
    "cancel": _cancel,
    "monitor": _monitor,
}


def perform(out_dir: Path, domain: str, kind: str, body: dict[str, Any], actor: str) -> dict[str, Any]:
    """操作を 1 つ実行し、画面の最新状態（workflow_view.build と同じ形）を返す。"""
    handler = _HANDLERS.get(str(kind or "").strip())
    if handler is None:
        raise ActionError(f"「{kind}」という操作はありません。")
    result = handler(out_dir, domain, body, actor)
    # start は新しいサイトを作るので、送られてきた（空の）site ではなく
    # 作ったサイトの状態を返す。空のまま組むと「最初のサイト」の ① に戻って見える
    if isinstance(result, str) and result:
        domain = result
    return workflow_view.build(out_dir, domain)
