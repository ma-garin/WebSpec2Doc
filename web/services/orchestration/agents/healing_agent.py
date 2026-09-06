"""05 オートヒーリングを指揮者から呼ぶためのアダプタ（修正と報告書）。

やることは monitor.py::run_now の後半と同じ——落ちたテストを欠陥として拾い、
報告書の下書きまで進めて、人の判断を待つ。違うのは出どころ（actor / source）だけ。

出どころを付け替えるのは表示のためだけではない。報告書の「事象」欄は
「誰が何をした結果これが見つかったか」を記録する場所であり、指揮者が起こした
ものを「人が押した」と書けば、あとから経緯を追えなくなる。

start_run は非同期（サーバ側のスレッドが進める）なので run_id を handle として返す。
"""

from __future__ import annotations

from dataclasses import replace

from web.services.healing import autorun_bridge, orchestrator, project_store, report_doc
from web.services.healing.types import HealingProject
from web.services.orchestration.ports import (
    Context,
    Readiness,
    StepResult,
    StepStatus,
)

#: 指揮者が起こしたことを示す出どころ。実行者が分からないときの既定値で、
#: 監視が起こしたものは ctx.actor（"monitor"）がそのまま出どころになる。
CONDUCTOR_SOURCE = "conductor"


def _source(ctx: Context) -> str:
    """記録に残す出どころ。指揮を起こした人・仕組みの名前をそのまま使う。"""
    return str(getattr(ctx, "actor", "") or "").strip() or CONDUCTOR_SOURCE

_NOT_CONNECTED = "オートヒーリング › 設定で、このサイトのリポジトリを接続してください"
_APPROVE_REPORT = "報告書を確認して、承認・差し戻し・却下を決めてください"

#: run.status → STEP_STATES。ここに無いものは「まだ動いている」とみなす。
_STATE_MAP = {
    "succeeded": "succeeded",
    "no_defects": "succeeded",
    "failed": "failed",
    "cancelled": "failed",
    "awaiting_human": "waiting_human",
}


def _resolve_project(ctx: Context) -> tuple[HealingProject | None, str]:
    """接続先を決める。project_id が空ならサイトの一致で探す。

    domain が一致しない接続先を黙って使わない。別サイトのリポジトリを
    直しにいく事故は、報告書を見るまで気づけない。
    """
    if ctx.project_id:
        project = project_store.get_project(ctx.out_dir, ctx.project_id)
        if project is None:
            return None, _NOT_CONNECTED
        if str(getattr(project, "domain", "") or "") != ctx.domain:
            return None, _NOT_CONNECTED
        return project, ""
    for project in project_store.list_projects(ctx.out_dir):
        if str(getattr(project, "domain", "") or "") == ctx.domain:
            return project, ""
    return None, _NOT_CONNECTED


def _connection_gap(project: HealingProject) -> str:
    """必須の接続確認で最初に落ちている項目の説明。全部 OK なら空文字。"""
    try:
        checks = project_store.check_connection(project)
    except Exception as exc:  # noqa: BLE001 - 判定できないなら走らせない側に倒す
        return f"接続を確認できませんでした: {exc}"
    for check in checks:
        if str(getattr(check, "severity", "required")) == "required" and not check.ok:
            return str(getattr(check, "detail", "") or getattr(check, "label", ""))
    return ""


#: 前の実行がまだ動いているときの説明。画面にそのまま出る。
_STILL_RUNNING = "前の実行がまだ終わっていません"

#: 「もう報告書がある」とみなす報告書の状態（types.REPORT_STATUSES の部分集合）。
#: returned（差し戻し）は「人が直しを求めて戻した」ので作り直す側に残す。
#: rejected（却下）を含めるのは、直さないと決めた欠陥を毎日また報告書に
#: しないため。含めないと人は同じ却下を無限に繰り返すことになる。
_REPORTED_STATES = ("awaiting", "approved", "rejected", "submitted")


def _reaped_note(count: int) -> str:
    """片付けた実行の件数を人に伝える 1 文（0 件なら空）。

    黙って片付けると、利用者からは「前は動かなかったのに今日は動いた」
    としか見えない。何を片付けたかは必ず結果に出す。
    """
    return f"止まっていた実行 {count} 件を失敗として片付けました。" if count else ""


class HealingAgent:
    """05: 落ちたテストから報告書を下書きし、人の判断を待つ。"""

    name = "healing"
    label = "修正と報告書"

    def ready(self, ctx: Context) -> Readiness:
        project, missing = _resolve_project(ctx)
        if project is None:
            return Readiness(
                ok=False, human_action=missing,
                detail=f"{ctx.domain} に対応する接続先がありません",
            )
        gap = _connection_gap(project)
        if gap:
            return Readiness(ok=False, human_action=gap, detail=f"接続先: {project.name}")
        return Readiness(ok=True, detail=f"接続先: {project.name}")

    def run(self, ctx: Context) -> StepResult:
        project, missing = _resolve_project(ctx)
        if project is None:
            return StepResult(
                status="waiting_human", summary="修正するリポジトリが決まっていません",
                human_action=missing,
            )
        gap = _connection_gap(project)
        if gap:
            return StepResult(
                status="waiting_human", summary="接続の設定が足りません", human_action=gap,
            )
        # プロセスごと消えた実行を先に片付ける。放っておくと「まだ終わっていない
        # 実行がある」と見え続け、このサイトの修正は二度と起きない。
        reaped = orchestrator.reap_orphans(ctx.out_dir, project_id=project.project_id)
        note = _reaped_note(len(reaped))
        if note:
            ctx.log(note)

        if orchestrator.has_active_run(ctx.out_dir, project.project_id):
            return StepResult(status="skipped", summary=note + _STILL_RUNNING,
                              reason="busy")

        try:
            defects = autorun_bridge.load_failures(ctx.out_dir, ctx.domain)
        except Exception as exc:  # noqa: BLE001 - 例外は握らず結果として返す
            return StepResult(
                status="failed", summary="実行結果を読めませんでした",
                error=f"失敗の読み取りに失敗しました: {exc}",
            )
        if not defects:
            ctx.log("失敗はありません。報告書は作りません")
            return StepResult(
                status="skipped", summary=note + "失敗はありません。報告書は作りません",
                reason="no_defects",
            )

        # 前の周回で報告書になった欠陥は二重に出さない（2 周目以降、テストが
        # 変わらず落ち続けているだけの場合に起きる）。
        try:
            reported = {
                r.defect_id: str(r.status or "")
                for r in report_doc.list_reports(
                    ctx.out_dir, project_id=project.project_id, limit=500
                )
                if r.status in _REPORTED_STATES
            }
        except Exception:  # noqa: BLE001 - 照合の失敗で修正そのものは止めない
            reported = {}
        excluded = [d for d in defects if d.defect_id in reported]
        if excluded:
            defects = [d for d in defects if d.defect_id not in reported]
            ctx.log(f"既に報告書がある {len(excluded)} 件を除外しました")

        if not defects:
            # 報告書があること＝失敗が無いこと、ではない。テストは落ち続けている。
            # ここを「失敗はありません」で畳むと、承認待ちが溜まったサイトが
            # 毎日「異常なし・成功」と表示される。人の番であることを状態で出す。
            states = [reported[d.defect_id] for d in excluded]
            waiting = states.count("awaiting")
            if waiting:
                action = f"承認待ちの報告書 {waiting} 件を確認してください"
            elif any(s in ("approved", "submitted") for s in states):
                action = "PR のマージ待ちです"
            else:
                action = (f"却下した失敗 {len(states)} 件が続いています。"
                          "直さないままでよいか確認してください")
            summary = note + f"失敗 {len(excluded)} 件は報告書があります"
            ctx.log(summary)
            return StepResult(
                status="waiting_human", summary=summary,
                human_action=action, reason="already_reported",
            )

        # 出どころを指揮を起こした側に付け替える。autorun_bridge は画面から
        # 押されたときと同じ Defect を作るので、そのままだと「人が押した」と
        # 読める記録が残る。
        source = _source(ctx)
        defects = [replace(d, source=source) for d in defects]
        summary = note + f"{len(defects)} 件の失敗から報告書を下書きしています"
        ctx.log(summary)
        try:
            # 確認と開始が一体になった関数で起こす。見張り（monitor）と指揮者は
            # 別スレッドから呼ぶので、確認と開始が分かれていると二重に起きる。
            run = orchestrator.start_run_if_idle(
                out_dir=ctx.out_dir,
                project=project,
                actor=source,
                defects=defects,
            )
        except Exception as exc:  # noqa: BLE001 - 例外は握らず結果として返す
            return StepResult(
                status="failed", summary="修正を始められませんでした",
                error=f"ヒーリングの起動に失敗しました: {exc}",
            )
        if run is None:
            return StepResult(status="skipped", summary=note + _STILL_RUNNING,
                              reason="busy")
        return StepResult(status="running", summary=summary, handle=run.run_id)

    def status(self, ctx: Context, handle: str) -> StepStatus:
        if not handle:
            return StepStatus(state="skipped", label="未実行", summary="まだ始めていません")
        try:
            run = orchestrator.get_run(ctx.out_dir, handle)
        except Exception as exc:  # noqa: BLE001
            return StepStatus(
                state="failed", label="状態を取得できません",
                error=f"実行の状態を取得できませんでした: {exc}",
            )
        if run is None:
            return StepStatus(
                state="failed", label="実行が見つかりません",
                error=f"実行 {handle} が見つかりませんでした",
            )
        raw = str(getattr(run, "status", "") or "")
        state = _STATE_MAP.get(raw, "running")
        report_ids = list(getattr(run, "report_ids", None) or [])
        waiting = state == "waiting_human"
        return StepStatus(
            state=state,
            label=str(getattr(run, "step_label", "") or raw),
            # summary は事実、human_action は依頼。混ぜると画面が
            # 「何が起きたか」と「何をすればよいか」を出し分けられない。
            summary=f"報告書 {len(report_ids)} 件が承認待ちです" if waiting else "",
            artifacts={
                f"report:{rid}": f".healing/reports/{rid}.json" for rid in report_ids
            },
            error=str(getattr(run, "error", "") or ""),
            human_action=_APPROVE_REPORT if waiting else "",
        )

    def cancel(self, ctx: Context, handle: str) -> bool:
        """05 側の実行を止める。中止の手段は 05 に 1 つだけ置く。

        指揮者が代わりに止めずにいると、指揮の記録だけが cancelled になり、
        修正エージェントは worktree を触り続ける。同じ実行に 2 つの止め方を
        作らないため、画面の中止と同じ関数（cancel_run）を呼ぶ。
        """
        run_id = str(handle or "").strip()
        if not run_id:
            return False
        try:
            stopped = bool(orchestrator.cancel_run(run_id))
        except Exception as exc:  # noqa: BLE001 - 中止の失敗で呼び出し元を落とさない
            ctx.log(f"修正の中止に失敗しました: {exc}")
            return False
        if not stopped:
            ctx.log("この実行はもう動いていません")
        return stopped
