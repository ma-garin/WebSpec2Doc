"""02 テスト自動化を指揮者から呼ぶためのアダプタ（QA 生成 → Playwright 化）。

01→02→03 の連鎖にある _phase_generate_qa（QA 成果物の生成）をそのまま呼び、
そのあとテストケース表を Playwright の .spec.ts へ落とす。パイプラインに
「どこまで走らせるか」を指定する仕組みは無いので、フェーズ関数を自分の
スレッドから順に呼ぶ。

Playwright 化に _phase_generate_scripts を使わないのは、あれが 03 AutoRun 用の
qa_process/autorun.spec.ts を作るものだからで、02 の成果物は
testcases/testcases.spec.ts（03 も 05 もこちらを先に読む）。同じ表から 2 つの
スクリプトを作ると、どちらが回ったのか結果から判別できなくなる。

人の承認は代行しない。03 AutoRun の段階承認（観点・設計）が未承認のまま
残っているサイトでは waiting_human を返して止まる。承認そのものは
待たない——承認を待って 2 時間ブロックすると、指揮者から見て「動いている」段と
「人待ちの段」の区別がつかなくなる。

要確認だけ止める（案2）: 段階の成果物が出ている時点で review_queue（信頼度×
リスク）を通し、要確認でない項目は自動承認する。要確認が 0 件の段階は
人を待たずに次へ進む（workflow_view.advance_design_stages）。要確認が
1 件以上残る段階だけ waiting_human で止まる。WEBSPEC2DOC_STAGE_REVIEW=all
で、案2 適用前の「全段階を人が見る」動作に戻せる。
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from web.services.orchestration.ports import (
    Context,
    Readiness,
    StepResult,
    StepStatus,
)

_NO_REPORT = "先にこのサイトの画面を解析してください（「保守下に置く」で始まります）"
_NO_HANDLE = "テスト作成の記録がありません"
_NO_EXECUTABLE = "自動実行できるテストケースがありません。テストケース表を確認してください"
#: 段階承認が残っているときの依頼文。{subject} に「テスト観点」等が入る。
_APPROVE_ACTION = "{subject}を承認してください"
#: 誰も承認していないまま作ったことを、成果物の外へ出すための 1 文。
_UNAPPROVED_NOTE = "テスト観点・設計の承認は経ていません（03 AutoRun の画面で確認できます）"

_SPEC_RELPATH = "testcases/testcases.spec.ts"
_CANCEL_NOTE = "テスト作成を中止しました"


@dataclass
class _Work:
    """1 回のテスト作成。status() は handle が指すこれだけを見る。"""

    state: str = "running"
    label: str = "テストを作成中"
    summary: str = ""
    error: str = ""
    human_action: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    #: 中止を頼まれたか。作成スレッドは横から止められないので、あとから来る
    #: 結果でこの状態を上書きしないための印として持つ。
    cancelled: bool = False
    #: 作成に使っている AutoRunJob（中止の合図を渡すため）。
    job: Any = None


_WORKS: dict[str, _Work] = {}
_WORKS_LOCK = threading.Lock()


def _report_path(ctx: Context) -> Path:
    return ctx.out_dir / ctx.domain / "report.json"


def _load_report(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("screens"), list):
        return None
    return data


def _stage_review_mode() -> str:
    """WEBSPEC2DOC_STAGE_REVIEW の値。既定は "review"（要確認だけ止める・案2）。

    "all" にすると案2適用前の挙動（全段階を人の承認待ちにする）へ戻せる
    余地を残す。テナントではなくプロセス単位の環境変数。
    """
    import os

    return str(os.environ.get("WEBSPEC2DOC_STAGE_REVIEW") or "review").strip().lower()


def _legacy_pending_gate(pipeline: Any) -> str:
    """WEBSPEC2DOC_STAGE_REVIEW=all のときの旧動作（案2 適用前）。

    自動承認は一切せず、8 段階を順に見て最初の未承認段階の名前を返す。
    """
    from autorun.stages import DESIGN_STAGE_IDS, STATUS_APPROVED, STATUS_SKIPPED
    from web.services.auto_run_pipeline import _GATE_MESSAGES

    if pipeline.all_approved:
        return ""
    for stage_id in DESIGN_STAGE_IDS:
        stage = pipeline.get(stage_id)
        if stage is not None and stage.status not in (STATUS_APPROVED, STATUS_SKIPPED):
            return _GATE_MESSAGES.get(stage_id, ("", "", "テスト設計"))[2]
    return "テスト設計"


def _pending_gate(ctx: Context) -> tuple[str, int]:
    """未承認のまま残っている段階の名前と、確認が要る項目数を返す（案2）。

    既定（WEBSPEC2DOC_STAGE_REVIEW=review、未設定時も同じ）では
    workflow_view.advance_design_stages に判定を委ねる——各段階の成果物が
    出ている時点で review_queue（信頼度×リスク）を通し、要確認でない項目は
    自動承認したうえで、要確認が 0 件の段階は次へ進める。要確認が 1 件以上
    残る段階だけで止まり、その段階名と件数を返す。

    WEBSPEC2DOC_STAGE_REVIEW=all では自動承認をせず、案2 適用前の挙動
    （最初の未承認段階の名前だけを返す・件数は常に 0）に戻す。

    stages.json が無いのは「03 AutoRun でこのサイトの段階承認をまだ一度も
    使っていない」という意味で、承認を待っている人は居ない。無いことを
    「未承認」と読むと、01→02 だけを使う経路が永久に止まる。空文字なら
    通過済み（進めてよい）。
    """
    stages_path = ctx.out_dir / ctx.domain / "qa_process" / "stages.json"
    if not stages_path.is_file():
        return "", 0
    try:
        if _stage_review_mode() == "all":
            from autorun.stages import Pipeline

            pipeline = Pipeline.from_dict(json.loads(stages_path.read_text(encoding="utf-8")))
            return _legacy_pending_gate(pipeline), 0

        from web.services.orchestration import workflow_view

        return workflow_view.advance_design_stages(ctx.out_dir, ctx.domain, actor="system")
    except Exception:  # noqa: BLE001 - 読めないものを「未承認」と決めつけない
        return "", 0


def _finish(handle: str, **fields: Any) -> None:
    with _WORKS_LOCK:
        work = _WORKS.get(handle)
        if work is None or work.cancelled:
            return  # 中止が先。あとから来た結果で中止を消さない
        for key, value in fields.items():
            setattr(work, key, value)


def _generate_qa(job: object, ctx: Context) -> str:
    """QA 成果物を生成する（01→02→03 の連鎖と同じ関数）。失敗の説明を返す。"""
    from web.services.auto_run_pipeline import _phase_generate_qa
    from web.services.viewpoint_store import get_viewpoint_store

    snapshot = get_viewpoint_store().select_snapshot({"url": job.url})
    job._viewpoint_snapshot = snapshot
    job.viewpoint_set_id = snapshot["set_id"]
    job.viewpoint_set_name = snapshot["set_name"]
    job.viewpoint_version = int(snapshot["version"])
    job.viewpoint_checksum = snapshot["checksum"]
    job.viewpoint_selection_reason = snapshot["selection_reason"]
    ctx.log(f"観点セットを固定しました（{job.viewpoint_set_name} v{job.viewpoint_version}）")
    _phase_generate_qa(job)
    if job.status == "failed":
        return str(job.error or "QA 成果物を生成できませんでした")
    return ""


def _build(handle: str, ctx: Context, job: object) -> None:
    """QA 生成 →（未承認の確認）→ Playwright 化。どの経路でも状態を必ず書く。"""
    from web.services.testcase_spec_generator import (
        SpecGenerationError,
        generate_spec,
        is_executable,
    )
    from web.services.testcase_table_store import build_rows

    try:
        failure = _generate_qa(job, ctx)
        if failure:
            _finish(handle, state="failed", label="QA 成果物の生成に失敗",
                    summary="テストの材料を作れませんでした", error=failure)
            return

        subject, review_count = _pending_gate(ctx)
        if subject:
            action = (
                f"テスト設計「{subject}」に確認が要る項目が{review_count}件あります"
                if review_count else _APPROVE_ACTION.format(subject=subject)
            )
            _finish(handle, state="waiting_human", label=f"{subject}の承認待ち",
                    summary=f"{subject}が承認されていません", human_action=action)
            return

        report = _load_report(_report_path(ctx))
        if report is None:
            _finish(handle, state="failed", label="解析結果を読めません",
                    summary=_NO_REPORT, error=_NO_REPORT)
            return

        rows = build_rows(report)
        spec_dir = ctx.out_dir / ctx.domain / "testcases"
        try:
            generate_spec(rows, spec_dir)
        except SpecGenerationError as exc:
            _finish(handle, state="failed", label="テストを作れません",
                    summary=_NO_EXECUTABLE, error=str(exc))
            return

        count = sum(1 for row in rows if is_executable(row))
        ctx.log(_UNAPPROVED_NOTE)
        _finish(handle, state="succeeded", label="テスト作成 完了",
                summary=f"テスト {count} 件を作成",
                artifacts={"spec": f"{ctx.domain}/{_SPEC_RELPATH}"})
    except Exception as exc:  # noqa: BLE001 - 例外でスレッドを黙って終わらせない
        _finish(handle, state="failed", label="テスト作成に失敗",
                summary="テストを作れませんでした",
                error=f"テストの作成中に問題が起きました: {exc}")


class TestsAgent:
    """02: 解析結果からテストを作り、Playwright のスクリプトへ落とす。"""

    name = "tests"
    label = "テストの作成"

    def ready(self, ctx: Context) -> Readiness:
        report = _load_report(_report_path(ctx))
        if report is None:
            return Readiness(
                ok=False, human_action=_NO_REPORT,
                detail=f"{ctx.domain} の解析結果がありません",
            )
        screens = len(report.get("screens") or [])
        if screens == 0:
            return Readiness(
                ok=False, human_action=_NO_REPORT,
                detail=f"{ctx.domain} は 1 画面も解析できていません",
            )
        return Readiness(ok=True, detail=f"解析済み {screens} 画面")

    def run(self, ctx: Context) -> StepResult:
        from web.services.auto_run_job import AutoRunJob

        report = _load_report(_report_path(ctx))
        if report is None:
            return StepResult(
                status="waiting_human", summary="解析結果がありません",
                human_action=_NO_REPORT,
            )

        url = str(report.get("site_url") or "").strip() or f"http://{ctx.domain}/"
        job = AutoRunJob(
            job_id=uuid.uuid4().hex, url=url, domain=ctx.domain,
            started_at=datetime.now().isoformat(timespec="seconds"),
        )
        job._output_dir = ctx.out_dir
        # 段階承認はここでは待たない（_pending_gate が未承認を waiting_human に写す）。
        job.require_stage_approval = False

        handle = job.job_id
        with _WORKS_LOCK:
            _WORKS[handle] = _Work(job=job)
        summary = f"{len(report.get('screens') or [])} 画面からテストを作ります"
        ctx.log(summary)
        threading.Thread(
            target=_build, args=(handle, ctx, job),
            name=f"tests-{handle[:8]}", daemon=True,
        ).start()
        return StepResult(status="running", summary=summary, handle=handle)

    def status(self, ctx: Context, handle: str) -> StepStatus:
        with _WORKS_LOCK:
            work = _WORKS.get(str(handle or "").strip())
        if work is None:
            return StepStatus(
                state="failed", label="記録なし", summary=_NO_HANDLE, error=_NO_HANDLE,
            )
        return StepStatus(
            state=work.state, label=work.label, summary=work.summary,
            artifacts=dict(work.artifacts), error=work.error,
            human_action=work.human_action,
        )

    def cancel(self, ctx: Context, handle: str) -> bool:
        """テスト作成に中止を伝える。生成中のスレッドは横から止められない。

        作成は QA 生成（LLM を含む）の中で進んでおり、割り込めない。できるのは
        中止の印を立てて、承認待ちで眠っているスレッドを起こすことだけ。
        印は _finish より強い（あとから来る結果で中止を消さない）。
        """
        key = str(handle or "").strip()
        with _WORKS_LOCK:
            work = _WORKS.get(key)
            if work is None:
                return False
            work.cancelled = True
            work.state = "cancelled"
            work.label = "テスト作成 中止"
            work.summary = _CANCEL_NOTE
            work.human_action = ""
            job = work.job
        if job is not None:
            try:
                job.cancel()  # 承認・入力待ちで眠っているスレッドを起こす
            except Exception:  # noqa: BLE001 - 合図の失敗で中止そのものを失敗にしない
                pass
        ctx.log("テスト作成の中止を伝えました（生成中の処理は区切りで止まります）")
        return True
