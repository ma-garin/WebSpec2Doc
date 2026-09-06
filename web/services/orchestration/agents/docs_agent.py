"""01 ドキュメントを指揮者から呼ぶためのアダプタ（画面の観測）。

01→02→03 の連鎖は web/services/auto_run_pipeline.py::_run_job に既にある。
ここはそれを作り直さず、**先頭の 3 フェーズだけを同じ順で呼ぶ**:

    _phase_discover（到達確認）→ ログイン入力待ち →（_do_login）→ _phase_crawl（観測）

パイプラインに「どこまで走らせるか」を指定する仕組みは無い（mode / stop_after /
phases のいずれも存在しない）ので、_run_job が呼んでいるものと同じ関数を同じ順で
自分のスレッドから呼ぶ。ここに観測の手順を書き写すと、01 の仕様がこの 1 ファイルに
複製され、片方だけが直る。

人の入力は代行しない。ログイン情報の入力待ちで止まったら waiting_human と
「03 AutoRun の画面でログイン情報を入力してください」を返し、スレッドは待たせたまま
にする（人が入力すれば、その待ちが解けて観測が続く）。

出力先は ctx.out_dir に固定する（job._output_dir）。出力ディレクトリ名は 01 が
URL のホストから決めるため、ctx.domain と一致しない URL は ready() で断る——
一致しないまま走らせると、02 以降が読む out_dir/<ctx.domain> ではない場所へ書き込む。
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from web.services.orchestration.ports import (
    Context,
    Readiness,
    StepResult,
    StepStatus,
)

_LOGIN_ACTION = "03 AutoRun の画面でログイン情報を入力してください"
_APPROVE_ACTION = "03 AutoRun の画面で観測結果を承認してください"
_NO_HANDLE = "観測の記録がありません"
_NO_DOMAIN = "観測するサイトを指定してください"
_NO_REPORT = "観測結果（画面の一覧）が保存されていません"

#: 既定の観測範囲。指揮者は params を渡さないので、この既定がそのまま効く。
DEFAULT_DEPTH = 1
DEFAULT_MAX_PAGES = 5

#: AutoRunJob.status → STEP_STATES。ここに無いものは「まだ動いている」とみなす。
_STATE_MAP = {
    "failed": "failed",
    "cancelled": "cancelled",
    "awaiting_input": "waiting_human",
    "awaiting_stages": "waiting_human",
    "awaiting_approval": "waiting_human",
}

_HUMAN_ACTION = {
    "awaiting_input": _LOGIN_ACTION,
    "awaiting_stages": _APPROVE_ACTION,
    "awaiting_approval": _APPROVE_ACTION,
}

#: 起こした観測（job_id → AutoRunJob）。status() は handle が指すものだけを見る。
_JOBS: dict[str, object] = {}
_JOBS_LOCK = threading.Lock()


def _int_param(ctx: Context, key: str, default: int) -> int:
    try:
        value = int(ctx.params.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _url_of(ctx: Context) -> str:
    """観測する URL。指定が無ければサイト名から推定する。"""
    given = str(ctx.params.get("url") or "").strip()
    return given or f"http://{ctx.domain}/"


def _domain_mismatch(ctx: Context, url: str) -> str:
    """URL と ctx.domain がずれていたら、その説明。合っていれば空文字。"""
    from web.validation import _domain_of

    actual = _domain_of(url)
    if actual == ctx.domain:
        return ""
    return f"指定された URL は {actual} のもので、{ctx.domain} と一致しません"


def _report_path(ctx: Context) -> Path:
    return ctx.out_dir / ctx.domain / "report.json"


def _screen_count(path: Path) -> int:
    """保存された観測結果の画面数。読めなければ -1（0 件と区別する）。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return -1
    screens = data.get("screens") if isinstance(data, dict) else None
    return len(screens) if isinstance(screens, list) else -1


def _observe(job: object, depth: int, max_pages: int) -> None:
    """_run_job の前半（到達確認 → ログイン → 観測）だけを同じ順で進める。"""
    import time

    from web.services.auto_run_pipeline import (
        LOGIN_INPUT_TIMEOUT_SEC,
        _do_login,
        _phase_crawl,
        _phase_discover,
    )

    try:
        _phase_discover(job, depth, max_pages)
        if job.status in ("failed", "cancelled"):
            return

        # ログイン情報の入力待ち。人が入力するまでこのスレッドは待つ
        # （status() は job の状態を読んで waiting_human を返す）。
        if job.status == "awaiting_input":
            job.awaiting_deadline_epoch = time.time() + LOGIN_INPUT_TIMEOUT_SEC
            job._input_event.wait(timeout=LOGIN_INPUT_TIMEOUT_SEC)
            job.awaiting_deadline_epoch = 0.0
            if job._cancelled:
                return
            if not job._input_data:
                job.add_unverified(
                    "ログイン情報の入力がタイムアウトし、"
                    "未ログインで到達できる範囲だけを対象にしました。"
                )
            if job._input_data.get("type") == "login" and not job._input_data.get("skip"):
                _do_login(job)
                if job.status == "failed":
                    return

        _phase_crawl(job, depth, max_pages)
        if job.status in ("failed", "cancelled"):
            return
        job.status = "complete"
        job.step_label = "観測完了"
        job.finished_at = datetime.now().isoformat(timespec="seconds")
    except Exception as exc:  # noqa: BLE001 - 例外でスレッドを黙って終わらせない
        job.status = "failed"
        job.error = f"観測の途中で問題が起きました: {exc}"
        job.finished_at = datetime.now().isoformat(timespec="seconds")
        job.add_log(job.error)


def _publish_to_autorun(job: object) -> None:
    """03 AutoRun の画面から見えるようにジョブを登録する（失敗しても観測は続ける）。

    ログイン情報の入力・承認は 03 の画面から行う。登録しないと human_action が
    「03 の画面で入力してください」と言っておいて、その画面に何も出ない。
    """
    try:
        from web.routes.auto_run import _JOBS as autorun_jobs
        from web.routes.auto_run import _JOBS_LOCK as autorun_lock

        with autorun_lock:
            autorun_jobs[job.job_id] = job
    except Exception:  # noqa: BLE001 - 画面への露出は付加価値。観測を止めない
        job.add_log("03 AutoRun の画面への登録に失敗しました（観測はこのまま進みます）")


class DocsAgent:
    """01: サイトを観測して画面の一覧（report.json）を作る。"""

    name = "docs"
    label = "画面の観測"

    def ready(self, ctx: Context) -> Readiness:
        if not str(ctx.domain or "").strip():
            return Readiness(ok=False, human_action=_NO_DOMAIN, detail="サイト名が空です")
        url = _url_of(ctx)
        mismatch = _domain_mismatch(ctx, url)
        if mismatch:
            return Readiness(
                ok=False,
                human_action="観測したいサイトと同じ URL を指定してください",
                detail=mismatch,
            )
        return Readiness(ok=True, detail=f"観測対象: {url}")

    def run(self, ctx: Context) -> StepResult:
        from web.services.auto_run_job import AutoRunJob

        url = _url_of(ctx)
        mismatch = _domain_mismatch(ctx, url)
        if mismatch:
            return StepResult(
                status="waiting_human", summary=mismatch,
                human_action="観測したいサイトと同じ URL を指定してください",
            )
        depth = _int_param(ctx, "depth", DEFAULT_DEPTH)
        max_pages = _int_param(ctx, "max_pages", DEFAULT_MAX_PAGES)

        job = AutoRunJob(
            job_id=uuid.uuid4().hex,
            url=url,
            domain=ctx.domain,
            started_at=datetime.now().isoformat(timespec="seconds"),
        )
        # テナントの解決はやり直さない。指揮者が渡した出力先をそのまま使う。
        job._output_dir = ctx.out_dir
        with _JOBS_LOCK:
            _JOBS[job.job_id] = job
        _publish_to_autorun(job)

        summary = f"{url} を観測します（深さ {depth} / 最大 {max_pages} 画面）"
        ctx.log(summary)
        threading.Thread(
            target=_observe, args=(job, depth, max_pages),
            name=f"docs-{job.job_id[:8]}", daemon=True,
        ).start()
        return StepResult(status="running", summary=summary, handle=job.job_id)

    def status(self, ctx: Context, handle: str) -> StepStatus:
        with _JOBS_LOCK:
            job = _JOBS.get(str(handle or "").strip())
        if job is None:
            return StepStatus(
                state="failed", label="観測の記録なし", summary=_NO_HANDLE, error=_NO_HANDLE,
            )
        raw = str(getattr(job, "status", "") or "")
        state = _STATE_MAP.get(raw)
        if state is not None:
            return StepStatus(
                state=state,
                label=str(getattr(job, "step_label", "") or raw),
                summary=str(getattr(job, "error", "") or "") if state == "failed" else "",
                error=str(getattr(job, "error", "") or ""),
                human_action=_HUMAN_ACTION.get(raw, ""),
            )
        if raw != "complete":
            return StepStatus(state="running", label=str(job.step_label or "観測中"))

        report = _report_path(ctx)
        screens = _screen_count(report)
        if screens < 0:
            return StepStatus(
                state="failed", label="観測結果を読めません",
                summary=_NO_REPORT, error=_NO_REPORT,
            )
        return StepStatus(
            state="succeeded",
            label="観測完了",
            summary=f"画面 {screens} 件を観測",
            artifacts={"report": f"{ctx.domain}/report.json"},
        )
