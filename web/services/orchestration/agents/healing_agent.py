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

from web.services.healing import autorun_bridge, orchestrator, project_store
from web.services.healing.types import HealingProject
from web.services.orchestration.ports import (
    Context,
    Readiness,
    StepResult,
    StepStatus,
)

#: 指揮者が起こしたことを示す出どころ。monitor.py の "monitor" に対応する。
CONDUCTOR_SOURCE = "conductor"

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
            return StepResult(status="skipped", summary=note + _STILL_RUNNING)

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
            )

        # 出どころを指揮者に付け替える。autorun_bridge は画面から押されたときと
        # 同じ Defect を作るので、そのままだと「人が押した」と読める記録が残る。
        defects = [replace(d, source=CONDUCTOR_SOURCE) for d in defects]
        summary = note + f"{len(defects)} 件の失敗から報告書を下書きしています"
        ctx.log(summary)
        try:
            # 確認と開始が一体になった関数で起こす。見張り（monitor）と指揮者は
            # 別スレッドから呼ぶので、確認と開始が分かれていると二重に起きる。
            run = orchestrator.start_run_if_idle(
                out_dir=ctx.out_dir,
                project=project,
                actor=CONDUCTOR_SOURCE,
                defects=defects,
            )
        except Exception as exc:  # noqa: BLE001 - 例外は握らず結果として返す
            return StepResult(
                status="failed", summary="修正を始められませんでした",
                error=f"ヒーリングの起動に失敗しました: {exc}",
            )
        if run is None:
            return StepResult(status="skipped", summary=note + _STILL_RUNNING)
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
        summary = _APPROVE_REPORT if state == "waiting_human" else ""
        return StepStatus(
            state=state,
            label=str(getattr(run, "step_label", "") or raw),
            summary=summary,
            artifacts={
                f"report:{rid}": f".healing/reports/{rid}.json"
                for rid in (getattr(run, "report_ids", None) or [])
            },
            error=str(getattr(run, "error", "") or ""),
        )
