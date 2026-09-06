"""指揮ワークフロー画面（新 UI）の状態 API が読む「今の姿」。

画面は 6 工程（サイトとコードを指定 → 観測 → テストを作る → 実行 →
分析して直す → 判断する）の**いま居る 1 工程だけ**を見るステッパーにした。
ここは conductor.py が持つ生の実行記録（ConductorRun / StepRecord。複数の
システムの都合が混ざったもの）を、その 1 画面のための要約に変換する。

判定はここでしか行わない。画面にもう一つ同じ判定を持たせると、
「どちらの判定を信じるか」という問題が生まれる。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from web.services.healing import project_store, report_doc
from web.services.orchestration import conductor
from web.services.orchestration.run_store import ConductorRun, StepRecord

#: 画面に出す 6 工程。キーは conductor の段名（docs/tests/run/healing）とは別語彙。
_STEP_DEFS: tuple[tuple[str, str], ...] = (
    ("setup", "サイトとコードを指定"),
    ("observe", "サイトを観測"),
    ("tests", "テストを作る"),
    ("run", "テストを実行"),
    ("analyze", "失敗を分析して直す"),
    ("decide", "判断する"),
)
_STEP_INDEX: dict[str, int] = {key: i for i, (key, _label) in enumerate(_STEP_DEFS)}
_FINISHED_INDEX = len(_STEP_DEFS)

#: conductor の段名 → 通常時の工程キー（healing だけ waiting_human で "decide" に化ける）。
_AGENT_OF_STEP: dict[str, str] = {"docs": "observe", "tests": "tests", "run": "run", "healing": "analyze"}
_STEP_OF_AGENT: dict[str, str] = {v: k for k, v in _AGENT_OF_STEP.items()}

_ROUND_RE = re.compile(r"（(\d+)\s*周目）")

_DEFAULT_MONITOR_TIME = "09:00"

#: docs_agent._LOGIN_ACTION と同じ文言（画面の判定に使う。docs_agent 側を
#: import すると 01 のアダプタに O2 画面の都合を持ち込むことになるため、
#: 文字列で照合する）。
_LOGIN_HUMAN_ACTION = "サイトにログインしてください"

_SETUP_TEXT = "まだサイトが登録されていません。見張りたいサイトと、そのコードの場所を教えてください。"


@dataclass(frozen=True)
class _Current:
    key: str
    state: str
    headline: str
    text: str
    elapsed_sec: int = 0
    error: str = ""
    action: dict[str, Any] | None = None


def _now() -> datetime:
    return datetime.now()


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None


def _elapsed_sec(started_at: str) -> int:
    started = _parse_ts(started_at)
    if started is None:
        return 0
    return max(0, int((_now() - started).total_seconds()))


def _round_no(record: StepRecord | None) -> str:
    if record is None:
        return "1"
    m = _ROUND_RE.search(record.label or "")
    return m.group(1) if m else "1"


def _records_by_name(run: ConductorRun, name: str) -> list[StepRecord]:
    return [s for s in run.steps if s.name == name]


def _last_touched(run: ConductorRun, name: str) -> StepRecord | None:
    """段 name の記録のうち、最後に走った（queued でない）もの。無ければ None。"""
    touched = [r for r in _records_by_name(run, name) if r.status != "queued"]
    return touched[-1] if touched else None


# ─────────────────────────── サイト一覧・接続先候補 ───────────────────────────


def _site_label(site: dict[str, Any]) -> str:
    """切替コンボに出す表示名。domain は必ず含める（衝突しても区別できるように）。

    観測で得た題名（report.json の title）が domain と違えば「題名（domain）」、
    無ければ domain だけ。永続データ（接続先の name 等）は書き換えない——
    ここは site 一覧を都度組み立てる読み取り専用の変換。
    """
    domain = str(site.get("domain") or "")
    title = str(site.get("title") or "").strip()
    if title and title != domain:
        return f"{title}（{domain}）"
    return domain


def _list_sites(out_dir: Path) -> list[dict[str, str]]:
    """接続・観測・指揮のいずれかが存在するサイトの一覧（選ばせるための一覧）。"""
    from web.routes.healing import (
        _SITE_EXCLUDE_DIRS,
        _conductor_domains,
        _connected_domains,
        _site_dict,
        _unobserved_site,
    )

    sites: dict[str, dict[str, Any]] = {}
    if out_dir.is_dir():
        for entry in sorted(out_dir.iterdir(), key=lambda p: p.name):
            if not entry.is_dir() or entry.name.startswith(".") or entry.name in _SITE_EXCLUDE_DIRS:
                continue
            if not (entry / "report.json").is_file():
                continue
            site = _site_dict(entry)
            if site is not None:
                sites[site["domain"]] = site
    try:
        for domain in _connected_domains(out_dir) | _conductor_domains(out_dir):
            sites.setdefault(domain, _unobserved_site(domain))
    except Exception:  # noqa: BLE001 - サイト一覧の一部が読めなくても画面は出す
        pass
    ordered = sorted(sites.values(), key=lambda s: str(s.get("domain") or ""))
    return [{"domain": s["domain"], "label": _site_label(s)} for s in ordered]


def _list_repos(out_dir: Path) -> list[dict[str, str]]:
    repos = project_store.discover_repos(out_dir, limit=200)
    return [
        {"path": r.path, "label": r.display_path, "verify_command": r.suggested_command}
        for r in repos
    ]


def _resolve_domain(out_dir: Path, domain: str, sites: list[dict[str, str]]) -> str:
    given = str(domain or "").strip()
    if given:
        return given
    return sites[0]["domain"] if sites else ""


def _project_for(out_dir: Path, domain: str) -> Any | None:
    for project in project_store.list_projects(out_dir):
        if project.domain == domain:
            return project
    return None


def _latest_run(out_dir: Path, domain: str) -> ConductorRun | None:
    if not domain:
        return None
    summaries = conductor.list_summaries(out_dir, domain=domain, limit=1)
    if not summaries:
        return None
    run_id = str(summaries[0].get("run_id") or "")
    return conductor.get(out_dir, run_id) if run_id else None


# ─────────────────────────── 承認待ちの中身 ───────────────────────────


def stages_path(out_dir: Path, domain: str) -> Path:
    """02 の段階承認ファイル（web/routes/autorun_stages.py と同じ置き場所）。

    autorun_stages._load_pipeline/_save_pipeline を直接呼ばないのは、
    それが自前で scoped_output_dir(OUTPUT_DIR) を解決し直すため——ここで
    受け取った out_dir（呼び出し側がテナントを確定させたもの）と食い違う
    経路をもう一つ作らないよう、ファイルの置き場所だけを共有する。
    """
    return Path(out_dir) / domain / "qa_process" / "stages.json"


def load_pipeline(out_dir: Path, domain: str):
    from autorun.stages import Pipeline

    path = stages_path(out_dir, domain)
    if path.is_file():
        try:
            return Pipeline.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return Pipeline.initial()


def save_pipeline(out_dir: Path, domain: str, pipeline: Any) -> None:
    path = stages_path(out_dir, domain)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pipeline.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def _pending_design_stage(out_dir: Path, domain: str) -> tuple[str, Any] | tuple[None, None]:
    """まだ承認・スキップされていない設計段階（1〜7）を 1 つ探す。無ければ (None, None)。"""
    from autorun.stages import DESIGN_STAGE_IDS, STATUS_APPROVED, STATUS_SKIPPED

    pipeline = load_pipeline(out_dir, domain)
    for stage_id in DESIGN_STAGE_IDS:
        stage = pipeline.get(stage_id)
        if stage is not None and stage.status not in (STATUS_APPROVED, STATUS_SKIPPED):
            return stage_id, stage
    return None, None


def _viewpoint_items(out_dir: Path, domain: str) -> tuple[list[dict[str, str]], int]:
    _stage_id, stage = _pending_design_stage(out_dir, domain)
    if stage is None:
        return [], 0
    items = [{"id": item.item_id, "text": item.title} for item in stage.items]
    return items[:3], len(items)


def _awaiting_reports(out_dir: Path, project_id: str) -> list[report_doc.MaintenanceReport]:
    if not project_id:
        return []
    return [
        r for r in report_doc.list_reports(out_dir, project_id=project_id, limit=200)
        if r.status == "awaiting"
    ]


def _report_item(report: report_doc.MaintenanceReport) -> dict[str, Any]:
    primary = "承認して PR を作る" if report.fix_target != "script" else "承認"
    return {
        "report_id": report.report_id,
        "title": report.title,
        "incident_text": report.incident_text,
        "cause_text": report.cause_text,
        "action_text": report.action_text,
        "verify_before": report.verify_before,
        "verify_after": report.verify_after,
        "verify_after_ok": report.verify_after_ok,
        "fix_target": report.fix_target,
        "primary": primary,
    }


def _monitor_item(project: Any | None) -> dict[str, Any]:
    return {
        "monitor_enabled": bool(getattr(project, "monitor_enabled", False)),
        "monitor_time": str(getattr(project, "monitor_time", "") or _DEFAULT_MONITOR_TIME),
    }


# ─────────────────────────── current の組み立て ───────────────────────────


def _action(kind: str, primary: str = "", secondary: str = "",
            items: list[Any] | None = None, **extra: Any) -> dict[str, Any]:
    return {"kind": kind, "primary": primary, "secondary": secondary,
            "items": list(items or []), **extra}


def _current_for_setup() -> _Current:
    return _Current(key="setup", state="human", headline="サイトとコードを指定", text=_SETUP_TEXT,
                     action=_action("start", primary="始める"))


def _current_for_waiting(out_dir: Path, run: ConductorRun, record: StepRecord) -> _Current:
    step_key = _AGENT_OF_STEP.get(record.name, "observe")
    headline = dict(_STEP_DEFS).get(step_key, step_key)

    if record.name == "docs" and record.human_action == _LOGIN_HUMAN_ACTION:
        login_url = _login_url_of(record.handle) or f"http://{run.domain}/"
        return _Current(
            key="observe", state="human", headline=headline,
            text="この先はログインが必要な画面です。サイトにログインしてください。",
            action=_action("login", primary="ログインした", secondary="ログインの要る画面は飛ばす",
                           items=[{"login_url": login_url}]),
        )
    if record.name == "tests":
        items, count = _viewpoint_items(out_dir, run.domain)
        text = (f"テストの観点 {count} 件を作りました。内容を確認して承認してください。"
                if count else (record.human_action or "テスト観点の承認待ちです。"))
        return _Current(
            key="tests", state="human", headline=headline, text=text,
            action=_action("approve_viewpoints", primary="承認して続ける", secondary="差し戻す",
                           items=items, count=count),
        )
    if record.name == "healing":
        reports = _awaiting_reports(out_dir, run.project_id)
        if reports:
            return _Current(
                key="decide", state="human", headline="判断する",
                text=f"報告書が {len(reports)} 通あります。内容を確認して判断してください。",
                action=_action("decide_report", primary=_report_item(reports[0])["primary"],
                               secondary="差し戻す・却下",
                               items=[_report_item(r) for r in reports]),
            )
        return _Current(key="analyze", state="human", headline="失敗を分析して直す",
                         text=record.human_action or record.summary or "",
                         action=_action("none"))
    # run / その他: 契約に個別の action は無いので待ちの説明だけ出す。
    return _Current(key=step_key, state="human", headline=headline,
                     text=record.human_action or record.summary or "", action=_action("none"))


def _login_url_of(job_id: str) -> str:
    """docs 段の handle（AutoRunJob.job_id）からログイン先 URL を引く。

    03 AutoRun の画面と同じ実体（web.routes.auto_run._JOBS）を読むだけで、
    ログインの入口はそちらの経路（api_autorun_submit_input）と共有する。
    """
    try:
        from web.routes.auto_run import _JOBS as autorun_jobs
        from web.routes.auto_run import _JOBS_LOCK as autorun_lock

        with autorun_lock:
            job = autorun_jobs.get(str(job_id or "").strip())
        if job is None:
            return ""
        request = getattr(job, "input_request", None) or {}
        return str(request.get("login_url") or "")
    except Exception:  # noqa: BLE001 - 引けなくても画面は出す（既定 URL で代替する）
        return ""


def _current_for_running(run: ConductorRun, record: StepRecord) -> _Current:
    step_key = _AGENT_OF_STEP.get(record.name, "observe")
    headline = dict(_STEP_DEFS).get(step_key, step_key)
    return _Current(key=step_key, state="running", headline=headline,
                     text=record.summary or f"{headline}を進めています",
                     elapsed_sec=_elapsed_sec(record.started_at))


def _current_for_terminal(run: ConductorRun, record: StepRecord, out_dir: Path) -> _Current:
    step_key = _AGENT_OF_STEP.get(record.name, "observe")
    headline = dict(_STEP_DEFS).get(step_key, step_key)
    if run.status == "cancelled":
        return _Current(key=step_key, state="cancelled", headline=headline,
                         text="ここまでの結果は残っています。もう一度始めると、"
                              "指定したところからやり直します。",
                         action=_action("start", primary="もう一度始める"))
    # failed / skipped（前の修正が終わっていない、等）
    return _Current(key=step_key, state="failed", headline=headline,
                     text=record.summary or run.error or "",
                     error=run.error or record.error or "")


def _current_for_finished(out_dir: Path, run: ConductorRun) -> _Current:
    last_healing = _last_touched(run, "healing")
    round_no = _round_no(last_healing)
    project = _project_for(out_dir, run.domain)
    monitor_time = str(getattr(project, "monitor_time", "") or _DEFAULT_MONITOR_TIME)
    text = f"{round_no} 周目で失敗が無くなりました。明日から毎朝 {monitor_time} に見張ります。"
    return _Current(key="finished", state="done", headline="完了", text=text,
                     action=_action("monitor", primary="見張りの時刻を変える", secondary="最初から",
                                    items=[_monitor_item(project)]))


def _current_of(out_dir: Path, run: ConductorRun | None) -> _Current:
    if run is None:
        return _current_for_setup()
    if run.status == "succeeded":
        return _current_for_finished(out_dir, run)
    index = int(run.step_index or 0)
    record = run.steps[index] if 0 <= index < len(run.steps) else None
    if record is None:
        return _current_for_setup()
    if run.status == "waiting_human":
        return _current_for_waiting(out_dir, run, record)
    if run.status in ("running", "queued"):
        return _current_for_running(run, record)
    return _current_for_terminal(run, record, out_dir)


def _current_index(current: _Current) -> int:
    if current.key == "finished":
        return _FINISHED_INDEX
    return _STEP_INDEX.get(current.key, 0)


def _step_summary(run: ConductorRun | None, key: str, is_done: bool) -> str:
    if run is None:
        return ""
    agent_name = _STEP_OF_AGENT.get(key)
    if agent_name is None:  # "decide" には対応する段名が無い（healing と共用）
        return ""
    record = _last_touched(run, agent_name)
    if record is not None:
        return record.summary or record.error or ""
    return "前回までに完了しています。" if is_done else ""


def _steps_list(run: ConductorRun | None, current: _Current) -> list[dict[str, Any]]:
    idx = _current_index(current)
    result: list[dict[str, Any]] = []
    for i, (key, label) in enumerate(_STEP_DEFS):
        if i < idx:
            state = "done"
        elif i == idx:
            state = current.state if current.state in ("human", "running") else "done"
        else:
            state = "todo"
        result.append({
            "no": i + 1, "key": key, "label": label, "state": state,
            "summary": _step_summary(run, key, state == "done"),
        })
    return result


def _rounds(run: ConductorRun | None, current: _Current) -> dict[str, int]:
    total = 1
    if run is not None:
        try:
            total = max(1, min(5, int(dict(run.params or {}).get("rounds", 1))))
        except (TypeError, ValueError):
            total = 1
    current_no = 1
    if run is not None:
        agent_name = _STEP_OF_AGENT.get(current.key)
        record = _last_touched(run, agent_name) if agent_name else None
        if record is None and 0 <= int(run.step_index or 0) < len(run.steps):
            record = run.steps[int(run.step_index or 0)]
        try:
            current_no = int(_round_no(record))
        except ValueError:
            current_no = 1
    return {"current": min(current_no, total), "total": total}


def build(out_dir: Path, domain: str) -> dict[str, Any]:
    """ワークフロー画面 1 画面分の状態を組み立てる。"""
    sites = _list_sites(out_dir)
    resolved_domain = _resolve_domain(out_dir, domain, sites)
    repos = _list_repos(out_dir)
    run = _latest_run(out_dir, resolved_domain) if resolved_domain else None

    current = _current_of(out_dir, run)
    steps = _steps_list(run, current)
    rounds = _rounds(run, current)

    # 2 周目以降は見出しに周回を付ける（経過タイマーが無言で巻き戻って
    # 見える問題への対策。finished は text 側で既に周回を伝えているため除く）。
    headline = current.headline
    if current.key != "finished" and rounds.get("current", 1) >= 2:
        headline = f"{headline}（{rounds['current']} 周目 / {rounds['total']}）"

    return {
        "domain": resolved_domain,
        "sites": sites,
        "repos": repos,
        "rounds": rounds,
        "steps": steps,
        "current": {
            "key": current.key, "state": current.state, "headline": headline,
            "text": current.text, "elapsed_sec": current.elapsed_sec, "error": current.error,
            "action": current.action or _action("none"),
        },
        "run_id": run.run_id if run is not None else "",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
