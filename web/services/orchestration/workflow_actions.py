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
    """url 1 本だけで始める（案1・T2）。

    repo / verify_command / rounds は渡ってきても使わない——コードの場所は
    「分析して直す」で必要だと分かった時点で connect 操作から聞く
    （onboarding.connect）。rounds は常に 1 とし、繰り返しは「もう 1 周」
    （another_round）に任せる。接続先がまだ無くても解析は始められる。
    """
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

    params: dict[str, Any] = {"url": url, "rounds": 1}
    for key in ("depth", "max_pages"):
        if key in body:
            try:
                params[key] = int(body[key])
            except (TypeError, ValueError):
                raise ActionError(f"{key} は整数で指定してください。") from None

    # 既に接続先があるサイト（domain 一致）なら使い回す。無ければ project_id
    # は空のまま始め、「分析して直す」で必要になった時点で connect が作る。
    project_id = next(
        (p.project_id for p in project_store.list_projects(out_dir) if p.domain == derived), ""
    )
    run = conductor.start_if_idle(
        out_dir=out_dir, domain=derived, goal="onboard",
        project_id=project_id, actor=actor, params=params,
    )
    if run is None:
        raise ActionError(_BUSY)
    return derived


# ─────────────────────────── login_done ───────────────────────────

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
        raise ActionError("解析の記録が見つかりません。")
    if str(getattr(job, "status", "") or "") != "awaiting_input":
        raise ActionError("いまはログイン入力待ちではありません。")

    job._input_data = dict(_LOGIN_SKIP_INPUT)
    job.input_request = None
    job.status = "crawling"
    job._input_event.set()


# ─────────────────────────── approve_stage / return_stage ───────────────────────────


def _approve_stage(out_dir: Path, domain: str, body: dict[str, Any], actor: str) -> None:
    """01 の段階を 1 つ承認する（案2・案5）。stage_id は画面の 8 段階一覧から選ぶ。

    item_ids があれば、画面に「要確認」として出ている項目のうち指定した分
    だけを確認する（残りは要確認のまま、段階はまだ承認しない）。無ければ
    段階に残る項目を全部確認してから、段階そのものを承認する。

    段階が承認できたら、後続の段階も要確認が 0 件である限り連続で進める
    （advance_design_stages・案2）。全段階が揃えば continue を起こす。
    """
    from autorun.stages import STATUS_APPROVED

    stage_id = str(body.get("stage_id") or "").strip()
    if not stage_id:
        raise ActionError("stage_id を指定してください。")
    pipeline = workflow_view.load_pipeline(out_dir, domain)
    stage = pipeline.get(stage_id)
    if stage is None:
        raise ActionError(f"未知の段階です: {stage_id}")

    raw_item_ids = body.get("item_ids") or []
    item_ids = [str(i) for i in raw_item_ids if str(i or "").strip()] if isinstance(raw_item_ids, list) else []
    targets = set(item_ids) if item_ids else {item.item_id for item in stage.items if not item.approved}
    approved_now = [item for item in stage.items if item.item_id in targets and not item.approved]
    if approved_now:
        updated = stage
        for item in approved_now:
            updated = updated.with_item(item.with_approval(True))
        pipeline = pipeline.replaced(updated).recorded(
            "item_approve", stage_id, f"{len(approved_now)}項目を確認", actor,
        )
        stage = pipeline.get(stage_id)

    if item_ids:
        # 個別の項目だけを確認した呼び出し。段階の承認は残りが揃うまで待つ。
        workflow_view.save_pipeline(out_dir, domain, pipeline)
        return

    if not stage.can_approve:
        raise ActionError("この段階はまだ承認できません。全ての項目を承認してから、段階を承認してください。")

    pipeline = pipeline.replaced(stage.with_status(STATUS_APPROVED)).recorded(
        "approve", stage_id, f"{len(stage.items)}項目を承認", actor,
    )
    workflow_view.save_pipeline(out_dir, domain, pipeline)

    # 次の段階も要確認 0 なら、連続で進める（案2）。8 段階すべてが揃うまでは
    # continue を起こさない——途中で起こすと、まだ承認していない段階を
    # 追い越して実行してしまう。
    subject, _review_pending = workflow_view.advance_design_stages(out_dir, domain, actor=actor)
    if not subject:
        conductor.start_if_idle(out_dir=out_dir, domain=domain, goal="continue", actor=actor, params={})


def _return_stage(out_dir: Path, domain: str, body: dict[str, Any], actor: str) -> None:
    """01 の段階を 1 つ差し戻す。差し戻す理由（note）を必ず記録する。"""
    from autorun.stages import STATUS_PENDING

    stage_id = str(body.get("stage_id") or "").strip()
    note = str(body.get("note") or "").strip()
    if not stage_id:
        raise ActionError("stage_id を指定してください。")
    if not note:
        raise ActionError("差し戻すときは、どこを直してほしいかを書いてください。")
    pipeline = workflow_view.load_pipeline(out_dir, domain)
    stage = pipeline.get(stage_id)
    if stage is None:
        raise ActionError(f"未知の段階です: {stage_id}")
    # 段階を pending に戻して差し戻しの理由を記録する。02 には「note を読んで
    # 作り直す」処理が無いため、作り直しそのものは次にこの段階を生成する側
    # （02 の画面 / 再実行）に委ねる（詳細は impl_wf_backend.md の未解決）。
    pipeline = pipeline.replaced(stage.with_status(STATUS_PENDING)).recorded(
        "return", stage_id, note, actor,
    )
    workflow_view.save_pipeline(out_dir, domain, pipeline)


def _removed_kind(out_dir: Path, domain: str, body: dict[str, Any], actor: str) -> None:
    """旧 kind（approve_viewpoints / return_viewpoints）への互換応答。"""
    raise ActionError("この操作は無くなりました")


# ─────────────────────────── connect ───────────────────────────


def _connect(out_dir: Path, domain: str, body: dict[str, Any], actor: str) -> None:
    """「分析して直す」でコードの場所が要ると分かった時点で接続先を作る（T2）。"""
    if not domain:
        raise ActionError("サイトが決まっていません。")
    repo = str(body.get("repo") or "")
    verify_command = str(body.get("verify_command") or "")
    try:
        plan = onboarding.connect(
            out_dir, domain=domain, repo=repo, verify_command=verify_command, actor=actor,
        )
    except ValueError as exc:
        raise ActionError(str(exc)) from exc
    conductor.start_if_idle(
        out_dir=out_dir, domain=domain, goal="heal",
        project_id=plan.project_id, actor=actor, params={},
    )


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
    "approve_stage": _approve_stage,
    "return_stage": _return_stage,
    "connect": _connect,
    "decide_report": _decide_report,
    "another_round": _another_round,
    "cancel": _cancel,
    "monitor": _monitor,
    # 旧 kind。UI の切り替え漏れ・古いタブに 400 で理由を返す。
    "approve_viewpoints": _removed_kind,
    "return_viewpoints": _removed_kind,
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
