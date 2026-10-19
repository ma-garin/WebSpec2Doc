"""指揮ワークフロー画面（新 UI）の状態 API が読む「今の姿」。

画面は 01（ドキュメント作成）の語彙に揃えた 5 工程（解析 → テスト設計 →
実行 → 分析して直す → 判断）の**いま居る 1 工程だけ**を見るステッパーにした。
サイトがまだ登録されていない間は工程に入らず、setup という別のカードを出す
（工程は増やさない）。ここは conductor.py が持つ生の実行記録
（ConductorRun / StepRecord。複数のシステムの都合が混ざったもの）を、
その 1 画面のための要約に変換する。

判定はここでしか行わない。画面にもう一つ同じ判定を持たせると、
「どちらの判定を信じるか」という問題が生まれる。

出所（text_source）: current.text が「実測（measured）」「案内文（user）」
「AI 提案（llm）」「未検証（unverified）」のどれに基づくかを添える。setup や
ログイン案内のような定型の連絡文は user、それ以外（進捗・件数・結果の要約）
は measured を既定にする。
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

#: 画面に出す 5 工程（01 の語彙）。キーは conductor の段名
#: （docs/tests/run/healing）とは別語彙。setup は工程ではなく、
#: サイト未登録時のカード（_current_for_setup）が使うキーで、
#: このステッパーには含めない。
_STEP_DEFS: tuple[tuple[str, str], ...] = (
    ("analyze", "解析"),
    ("design", "テスト設計"),
    ("run", "実行"),
    ("fix", "分析して直す"),
    ("decide", "判断"),
)
_STEP_INDEX: dict[str, int] = {key: i for i, (key, _label) in enumerate(_STEP_DEFS)}
_FINISHED_INDEX = len(_STEP_DEFS)

#: conductor の段名 → 通常時の工程キー（healing だけ waiting_human で "decide" に化ける）。
_AGENT_OF_STEP: dict[str, str] = {"docs": "analyze", "tests": "design", "run": "run", "healing": "fix"}
_STEP_OF_AGENT: dict[str, str] = {v: k for k, v in _AGENT_OF_STEP.items()}

_ROUND_RE = re.compile(r"（(\d+)\s*周目）")

_DEFAULT_MONITOR_TIME = "09:00"

#: docs_agent._LOGIN_ACTION と同じ文言（画面の判定に使う。docs_agent 側を
#: import すると 01 のアダプタに O2 画面の都合を持ち込むことになるため、
#: 文字列で照合する）。
_LOGIN_HUMAN_ACTION = "サイトにログインしてください"

_SETUP_TEXT = "まだサイトが登録されていません。見張りたいサイトの URL を教えてください。"


@dataclass(frozen=True)
class _Current:
    key: str
    state: str
    headline: str
    text: str
    #: text の出所。"measured"（実測）/ "user"（案内文）/ "llm"（AI 提案）/
    #: "unverified"（未検証）のいずれか。既定は measured——ほとんどの text は
    #: 実行記録・件数など実測から組み立てているため。setup やログイン案内の
    #: ような定型の連絡文だけ user にする。
    text_source: str = "measured"
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

    解析で得た題名（report.json の title）が domain と違えば「題名（domain）」、
    無ければ domain だけ。永続データ（接続先の name 等）は書き換えない——
    ここは site 一覧を都度組み立てる読み取り専用の変換。
    """
    domain = str(site.get("domain") or "")
    title = str(site.get("title") or "").strip()
    if title and title != domain:
        return f"{title}（{domain}）"
    return domain


def _list_sites(out_dir: Path) -> list[dict[str, str]]:
    """接続・解析・指揮のいずれかが存在するサイトの一覧（選ばせるための一覧）。"""
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


def _page_report(out_dir: Path, domain: str) -> dict[str, Any] | None:
    """01 の解析結果（report.json）。review_queue のリスク判定が画面 URL を
    見るために読む。無ければ None（page_urls_from_report が空辞書に変換する）。
    """
    path = Path(out_dir) / domain / "report.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _design_stage_items(out_dir: Path, domain: str) -> tuple[list[dict[str, Any]], str, int]:
    """01 の 8 段階を画面用に並べる（案5・案2）。

    各段階の status は承認 UI がそのまま出せる形（approved/skipped/pending/
    current）に正規化する。戻り値の 2, 3 番目は「いま確認すべき段階」の
    名前と no（1〜8）——全段階が承認・スキップ済みなら no は 0 になる。

    要確認だけ止める既定（案2）に合わせ、各段階に review_queue の判定を
    添える——auto_approved（自動で確認済みの件数）、review（要確認のまま
    残っている項目・最大 5 件: item_id/text/reason）、review_count。
    """
    from autorun.review_queue import build_review_queue, page_urls_from_report
    from autorun.stages import STATUS_APPROVED, STATUS_SKIPPED

    pipeline = load_pipeline(out_dir, domain)
    page_urls = page_urls_from_report(_page_report(out_dir, domain))
    entries_by_stage: dict[str, list[Any]] = {}
    for entry in build_review_queue(pipeline, page_urls):
        entries_by_stage.setdefault(entry.stage_id, []).append(entry)

    current_id = pipeline.current_stage_id
    items: list[dict[str, Any]] = []
    current_name, current_no = "", 0
    for stage in pipeline.stages:
        definition = stage.definition
        if stage.status in (STATUS_APPROVED, STATUS_SKIPPED):
            status = stage.status
        elif stage.stage_id == current_id:
            status = "current"
            current_name, current_no = definition.name, definition.step_no
        else:
            status = "pending"
        entries = entries_by_stage.get(stage.stage_id, [])
        review = [e for e in entries if e.needs_review and not e.approved]
        items.append({
            "stage_id": stage.stage_id, "no": definition.step_no, "name": definition.name,
            "status": status, "item_count": len(stage.items),
            "approved_count": sum(1 for item in stage.items if item.approved),
            "auto_approved": sum(1 for e in entries if not e.needs_review),
            "review": [{"item_id": e.item_id, "text": e.title, "reason": e.reason} for e in review[:5]],
            "review_count": len(review),
        })
    return items, current_name, current_no


def advance_design_stages(out_dir: Path, domain: str, actor: str = "system") -> tuple[str, int]:
    """要確認だけ止める既定の進め方（案2）。

    tests_agent（承認を待つかどうかの判定）と workflow_actions._approve_stage
    （人が1段階片付けたあと、後続も連続で進めるため）の両方から呼ぶ——同じ
    判定を二重に持たないため。

    各段階の成果物（items）が出ている時点で review_queue（信頼度×リスク）を
    通し、要確認でない項目は自動承認する（01 の
    /api/autorun/review-queue/auto-approve と同じ判定・同じ記録）。要確認が
    0 件になった段階は、段階そのものも承認して次へ進む。要確認が 1 件以上
    残る段階に着くとそこで止まり、その段階名と件数を返す
    （空文字なら全段階が承認・スキップ済み）。stages.json が無ければ人が
    待っていないという意味なので ("", 0)。
    """
    from autorun.review_queue import build_review_queue, page_urls_from_report
    from autorun.stages import STATUS_APPROVED, STATUS_GENERATED, STATUS_SKIPPED

    if not stages_path(out_dir, domain).is_file():
        return "", 0
    pipeline = load_pipeline(out_dir, domain)
    if pipeline.all_approved:
        return "", 0
    page_urls = page_urls_from_report(_page_report(out_dir, domain))

    for stage in pipeline.stages:
        if stage.status in (STATUS_APPROVED, STATUS_SKIPPED):
            continue
        if stage.status != STATUS_GENERATED:
            # まだ内容が出ていない段階。生成は 03 AutoRun 側の役割で、
            # ここでは行わない——待っている段階の名前だけ返す。
            from web.services.auto_run_pipeline import _GATE_MESSAGES

            save_pipeline(out_dir, domain, pipeline)
            return _GATE_MESSAGES.get(stage.stage_id, ("", "", stage.definition.name))[2], 0

        entries = [e for e in build_review_queue(pipeline, page_urls) if e.stage_id == stage.stage_id]
        auto_ids = {e.item_id for e in entries if not e.needs_review and not e.approved}
        if auto_ids:
            updated = stage
            for item in stage.items:
                if item.item_id in auto_ids:
                    updated = updated.with_item(item.with_approval(True))
            pipeline = pipeline.replaced(updated).recorded(
                "item_approve", stage.stage_id,
                f"自動承認: 実測・低リスクの{len(auto_ids)}項目", actor,
            )

        review_pending = sum(1 for e in entries if e.needs_review and not e.approved)
        if review_pending:
            save_pipeline(out_dir, domain, pipeline)
            return stage.definition.name, review_pending

        current = pipeline.get(stage.stage_id)
        if not current.can_approve:
            # 要確認は 0 件だが、まだ承認できない状態（理論上の防御）。
            save_pipeline(out_dir, domain, pipeline)
            return stage.definition.name, 0
        pipeline = pipeline.replaced(current.with_status(STATUS_APPROVED)).recorded(
            "approve", stage.stage_id,
            f"{len(current.items)}項目を承認（自動: 確認が要る項目は0件）", actor,
        )

    save_pipeline(out_dir, domain, pipeline)
    return "", 0


def _failure_count(out_dir: Path, domain: str) -> int:
    """直近の実行結果から失敗したテストの件数を数える（接続先が無くても読める）。

    healing_agent.ready() は接続先を確認する前に失敗を数えないため、ここで
    別に読む。読めなければ 0（無いことを「多い」と誤解させない）。
    """
    from web.services.healing import autorun_bridge

    try:
        return len(autorun_bridge.load_failures(out_dir, domain))
    except Exception:  # noqa: BLE001 - 件数が出せなくても画面は止めない
        return 0


def _awaiting_reports(out_dir: Path, project_id: str) -> list[report_doc.MaintenanceReport]:
    if not project_id:
        return []
    return [
        r for r in report_doc.list_reports(out_dir, project_id=project_id, limit=200)
        if r.status == "awaiting"
    ]


def _report_sources(report: report_doc.MaintenanceReport) -> dict[str, str]:
    """報告書の各節の出所（T3）。

    事象・検証は本体が実測した事実。原因・対応は、テスト側の修正
    （fix_target="script"）なら差分という事実から組み立てているので measured、
    それ以外（製品側の修正）は AI の提案文なので llm。検証があとが空（未実行）
    なら unverified——「未検証」を「問題なし」と混同しない（T7）。
    """
    measured_cause = report.fix_target == "script"
    return {
        "incident": "measured",
        "cause": "measured" if measured_cause else "llm",
        "action": "measured" if measured_cause else "llm",
        "verify": "measured" if str(report.verify_after or "").strip() else "unverified",
    }


def _report_item(report: report_doc.MaintenanceReport) -> dict[str, Any]:
    # 「PR」は開発者用語（T8）。利用者には「修正を送る」、届いた先の説明は
    # 画面側で薄字 1 行として添える。
    primary = "承認して修正を送る" if report.fix_target != "script" else "承認"
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
        "sources": _report_sources(report),
    }


def _awaiting_bundles(out_dir: Path, project_id: str) -> list[report_doc.Bundle]:
    """判断カードの単位（案3）。801 通の個票ではなく、画面 × 観点の束で見せる。"""
    if not project_id:
        return []
    return report_doc.list_bundles(out_dir, project_id=project_id, status="awaiting")


def _bundle_sources(bundle: report_doc.Bundle) -> dict[str, str]:
    """束の出所（T3）。_report_sources と同じ考え方を束の粒度に広げる——
    束の中身が全部テスト側の修正（script）なら実測、1 件でも製品側（repo）が
    混じれば AI の提案。検証は、束の中に未実行が 1 件でも残れば未検証。
    """
    measured_cause = bool(bundle.fix_targets) and bundle.fix_targets <= {"script"}
    unverified = bundle.count > bundle.verify_after_ok_count
    return {
        "incident": "measured",
        "cause": "measured" if measured_cause else "llm",
        "action": "measured" if measured_cause else "llm",
        "verify": "unverified" if unverified else "measured",
    }


def _bundle_item(bundle: report_doc.Bundle) -> dict[str, Any]:
    scripts_only = bool(bundle.fix_targets) and bundle.fix_targets <= {"script"}
    primary = "承認" if scripts_only else "承認して修正を送る"
    return {
        "bundle_id": bundle.bundle_id,
        "title": bundle.title,
        "count": bundle.count,
        "awaiting_count": bundle.awaiting_count,
        "needs_review": bundle.needs_review,
        "review_reason": bundle.review_reason,
        "verify_after_ok_count": bundle.verify_after_ok_count,
        "fix_targets": sorted(bundle.fix_targets),
        "sources": _bundle_sources(bundle),
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


def _current_for_setup(domain: str = "") -> _Current:
    """サイト未登録、またはサイトはあるが指揮の実行記録・対象（プロジェクト）が無い状態。

    domain が空 = サイト 0 件（未登録）。domain があれば観測済みサイトは存在するので
    「登録されていない」とは言わず、指揮の対象が未設定である事実と次の行動 1 つを返す。
    """
    if domain:
        return _Current(
            key="setup", state="human", headline="指揮を始める",
            text=f"サイト {domain} はありますが、指揮の対象（プロジェクト）が未設定です。"
                 "解析を始めると対象が作られます。",
            text_source="user", action=_action("start", primary="解析を始める"))
    return _Current(key="setup", state="human", headline="サイトを指定", text=_SETUP_TEXT,
                     text_source="user", action=_action("start", primary="解析を始める"))


def _current_for_waiting(out_dir: Path, run: ConductorRun, record: StepRecord) -> _Current:
    step_key = _AGENT_OF_STEP.get(record.name, "analyze")
    headline = dict(_STEP_DEFS).get(step_key, step_key)

    if record.name == "docs" and record.human_action == _LOGIN_HUMAN_ACTION:
        login_url = _login_url_of(record.handle) or f"http://{run.domain}/"
        return _Current(
            key="analyze", state="human", headline=headline,
            text="この先はログインが必要な画面です。サイトにログインしてください。",
            text_source="user",
            action=_action("login", primary="ログインした", secondary="ログインの要る画面は飛ばす",
                           items=[{"login_url": login_url}]),
        )
    if record.name == "tests":
        items, stage_name, stage_no = _design_stage_items(out_dir, run.domain)
        current_item = next((it for it in items if it["status"] == "current"), None)
        review_count = int(current_item["review_count"]) if current_item else 0
        if stage_no and review_count:
            text = f"テスト設計「{stage_name}」に確認が要る項目が{review_count}件あります"
        elif stage_no:
            text = f"テスト設計の {stage_no} 段階目「{stage_name}」を確認してください"
        else:
            text = record.human_action or "テスト設計の承認待ちです。"
        return _Current(
            key="design", state="human", headline=headline, text=text,
            action=_action("approve_stage", primary="確認して次へ", secondary="差し戻す（メモ）",
                           items=items),
        )
    if record.name == "healing":
        # healing_agent と同じ文字列で照合する（docs/login の _LOGIN_HUMAN_ACTION
        # と同じやり方。private だが同じ conductor 配下のエージェントなので、
        # 文字列を二重管理するより import する方が食い違いに強い）。
        from web.services.orchestration.agents.healing_agent import _NOT_CONNECTED

        if record.human_action == _NOT_CONNECTED:
            count = _failure_count(out_dir, run.domain)
            return _Current(
                key="fix", state="human", headline="分析して直す",
                text=f"失敗が {count} 件ありました。直すにはコードの場所が要ります",
                action=_action("connect", primary="接続する", items=_list_repos(out_dir)),
            )
        decide = _decide_current(out_dir, run.project_id, run.domain)
        if decide is not None:
            return decide
        return _Current(key="fix", state="human", headline="分析して直す",
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


def _run_progress_text(out_dir: Path, run: ConductorRun, record: StepRecord) -> str:
    """実行中の見込み・進捗（案・T2/T8）。

    conductor._await_step は非同期の段を 10 秒毎に見ているが、記録
    （record.summary）へ書き戻すのは段が終わったとき（_settle）だけ——
    running の間はここを読んでも更新されない。件数・目安は run_agent.status
    が実測（メタ件数・進捗 ndjson）から作るので、ここで直接呼んで読みに行く。
    """
    from web.services.orchestration import registry
    from web.services.orchestration.ports import Context

    try:
        agent = registry.get_agent("run")
        ctx = Context(out_dir=out_dir, domain=run.domain, project_id=run.project_id,
                      params=run.params)
        status = agent.status(ctx, record.handle)
    except Exception:  # noqa: BLE001 - 進捗が読めなくても既定の文言で表示は続ける
        return ""
    return status.summary or ""


def _current_for_running(out_dir: Path, run: ConductorRun, record: StepRecord) -> _Current:
    step_key = _AGENT_OF_STEP.get(record.name, "observe")
    headline = dict(_STEP_DEFS).get(step_key, step_key)
    text = record.summary or f"{headline}を進めています"
    if record.name == "run" and record.handle:
        text = _run_progress_text(out_dir, run, record) or text
    return _Current(key=step_key, state="running", headline=headline, text=text,
                     elapsed_sec=_elapsed_sec(record.started_at))


def _decide_current(out_dir: Path, project_id: str, domain: str = "") -> _Current | None:
    """承認待ちの束があれば「判断」のカード。無ければ None。

    run に接続先 ID が無いとき（domain だけで起こした run）は domain から引く。
    """
    if not project_id and domain:
        project = _project_for(out_dir, domain)
        project_id = getattr(project, "project_id", "") if project else ""
    bundles = _awaiting_bundles(out_dir, project_id)
    if not bundles:
        return None
    total = sum(b.awaiting_count for b in bundles)
    return _Current(
        key="decide", state="human", headline="判断",
        text=f"確認が要る束が {len(bundles)} 件（報告書 {total} 通）あります。"
             "内容を確認して判断してください。",
        action=_action("decide_bundle", primary=_bundle_item(bundles[0])["primary"],
                       secondary="差し戻す・却下",
                       items=[_bundle_item(b) for b in bundles]),
    )


def _decided_count(out_dir: Path, run: ConductorRun) -> tuple[int, list[int]]:
    """判断が済んだ報告書の通数と、承認で出来た PR 番号（重複なし）。"""
    project_id = run.project_id
    if not project_id:
        project = _project_for(out_dir, run.domain)
        project_id = getattr(project, "project_id", "") if project else ""
    if not project_id:
        return 0, []
    try:
        reports = report_doc.list_reports(out_dir, project_id=project_id, limit=1000)
    except Exception:  # noqa: BLE001 - 読めなければ 0（判断済みとは言わない）
        return 0, []
    since = str(run.started_at or "")
    decided = [r for r in reports
               if r.status in ("approved", "rejected", "returned", "submitted")
               and (not since or str(r.updated_at or "") >= since)]
    prs = sorted({int(r.pr_number) for r in decided if getattr(r, "pr_number", 0)})
    return len(decided), prs


def _current_for_terminal(run: ConductorRun, record: StepRecord, out_dir: Path) -> _Current:
    step_key = _AGENT_OF_STEP.get(record.name, "observe")
    headline = dict(_STEP_DEFS).get(step_key, step_key)
    if run.status == "cancelled":
        return _Current(key=step_key, state="cancelled", headline=headline,
                         text="ここまでの結果は残っています。もう一度始めると、"
                              "指定したところからやり直します。",
                         action=_action("start", primary="もう一度始める"))
    # 修正が 1 件も適用できず failed で終わっても、下書きされた報告書
    # （「直っていません」）は人が判断するもの（T7）。報告書があれば判断へ
    if record.name == "healing":
        decide = _decide_current(out_dir, run.project_id, run.domain)
        if decide is not None:
            return decide
        decided, prs = _decided_count(out_dir, run)
        if decided:
            # 報告書は全部判断済み。この周の仕事は終わり
            project = _project_for(out_dir, run.domain)
            monitor_time = str(getattr(project, "monitor_time", "") or _DEFAULT_MONITOR_TIME)
            if prs:
                sent = "・".join(f"#{n}" for n in prs)
                middle = f"修正を送りました（PR {sent}）。開発者が取り込むとサイトに反映されます。"
            else:
                middle = "適用された修正は無いので、サイトは変わっていません。"
            return _Current(
                key="finished", state="done", headline="完了",
                text=f"報告書 {decided} 通を判断しました。{middle}"
                     f"明日から毎朝 {monitor_time} に見張ります。",
                text_source="measured",
                action=_action("monitor", primary="見張りの時刻を変える", secondary="最初から",
                               items=[_monitor_item(project)]))
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


def _current_of(out_dir: Path, run: ConductorRun | None, domain: str = "") -> _Current:
    if run is None:
        return _current_for_setup(domain)
    if run.status == "succeeded":
        return _current_for_finished(out_dir, run)
    index = int(run.step_index or 0)
    record = run.steps[index] if 0 <= index < len(run.steps) else None
    if record is None:
        return _current_for_setup(domain)
    if run.status == "waiting_human":
        return _current_for_waiting(out_dir, run, record)
    if run.status in ("running", "queued"):
        return _current_for_running(out_dir, run, record)
    return _current_for_terminal(run, record, out_dir)


def _current_index(current: _Current) -> int:
    if current.key == "finished":
        return _FINISHED_INDEX
    # "setup"（サイト未登録）は 5 工程のどれでもない。-1 にして全工程を
    # todo のまま出す——先頭工程がもう動いているように見せない。
    return _STEP_INDEX.get(current.key, -1)


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
            # human / running はそのまま。cancelled・failed も現在の工程の実情
            # として出す——done に丸めると、中止・失敗が完了に見えてしまう
            # （通し検証で指摘された表示矛盾）。それ以外（succeeded 等）は done。
            if current.state in ("human", "running", "cancelled", "failed"):
                state = current.state
            else:
                state = "done"
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

    current = _current_of(out_dir, run, resolved_domain)
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
            "text": current.text, "text_source": current.text_source,
            "elapsed_sec": current.elapsed_sec, "error": current.error,
            "action": current.action or _action("none"),
        },
        "run_id": run.run_id if run is not None else "",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
