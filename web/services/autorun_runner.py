"""AutoRun パイプラインを Flask リクエストコンテキスト外（CLI 等）から実行するランナー。

GUI では `web/routes/auto_run.py` の各 API ハンドラが `request` を解析して
`AutoRunJob` を組み立て、`_run_job` をバックグラウンドスレッドで回している。
本モジュールはその「ジョブ組み立て」と「段階承認の解除」を Flask 非依存で
再現し、CLI（`python src/main.py --autorun`）から同じパイプラインを走らせる。

設計上のポイント:

- パイプライン本体（`_run_job` と各 `_phase_*`）は `request`/`session` を一切
  参照せず `AutoRunJob` だけで動く。よって本ランナーは `_run_job` をそのまま
  再利用し、ロジックを二重化しない。
- 段階承認（仕様7〜14）は本来 HTTP エンドポイントで解除されるが、CLI では
  人が居ないため 2 モードを用意する:
    - approve="auto": 各段階の内容を生成・提示したうえで自動承認する
      （`require_stage_approval=True` のまま、関門到達を検知して解除）。
      設計成果物（stages.json / QualityForward CSV 等）も生成される。
    - approve="skip": `require_stage_approval=False`。関門自体を素通りし、
      「人の確認を経ていない」ことをログへ残す（最速・成果物は簡素）。
- ログイン壁が検知された場合は、渡された認証情報を投入するか、スキップする。
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TERMINAL_STATUSES = frozenset({"complete", "failed", "cancelled"})
_POLL_INTERVAL_SEC = 0.3


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_autorun_job(
    url: str,
    *,
    output_dir: Path,
    auth_path: str = "",
    mode: str = "url",
    reference_docs: list[str] | None = None,
    selection_criterion: str = "vertex_coverage",
    target_page_id: str = "",
    observe_validation: bool = False,
    viewpoint_set_id: str = "",
    viewpoint_version: int | None = None,
    require_stage_approval: bool = True,
) -> Any:
    """CLI 実行用に `AutoRunJob` を組み立てる（`api_autorun_start` と等価）。

    観点セットはストアから固定スナップショットとして選択する。set_id 未指定なら
    既定の公開版が選ばれる。ここで例外が起きた場合は呼び出し側へ伝播させる
    （CLI は明確なエラーで終了する）。
    """
    from web.services.auto_run_job import AutoRunJob
    from web.services.viewpoint_store import get_viewpoint_store

    snapshot = get_viewpoint_store().select_snapshot(
        {"url": url},
        set_id=viewpoint_set_id or None,
        version_number=int(viewpoint_version) if viewpoint_version else None,
    )

    job = AutoRunJob(
        job_id=uuid.uuid4().hex,
        url=url,
        started_at=_now_iso(),
        viewpoint_set_id=snapshot["set_id"],
        viewpoint_set_name=snapshot["set_name"],
        viewpoint_version=int(snapshot["version"]),
        viewpoint_checksum=snapshot["checksum"],
        viewpoint_selection_reason=snapshot["selection_reason"],
        viewpoint_count=int(snapshot["viewpoint_count"]),
        mode=mode,
        selection_criterion=selection_criterion,
        target_page_id=target_page_id,
        observe_validation=observe_validation,
        require_stage_approval=require_stage_approval,
    )
    job._viewpoint_snapshot = snapshot
    job._output_dir = Path(output_dir)
    job._reference_docs = list(reference_docs or [])
    if auth_path:
        job.auth_path = auth_path
    job.add_log(
        f"観点セットを固定: {job.viewpoint_set_name} v{job.viewpoint_version} "
        f"({job.viewpoint_count}件 / {job.viewpoint_selection_reason})"
    )
    return job


def run_autorun_job(
    job: Any,
    depth: int,
    max_pages: int,
    *,
    login: dict[str, str] | None = None,
    on_log: Callable[[str], None] | None = None,
    poll_interval: float = _POLL_INTERVAL_SEC,
) -> Any:
    """`_run_job` をスレッド実行し、ログ配信・ログイン投入・段階自動承認を仲介する。

    - `on_log` には新規ログ行を逐次渡す（既定は何もしない）。
    - `login` が {"username","password"} を持てばログイン壁で投入、無ければスキップ。
    - `job.require_stage_approval` が True の場合、関門（awaiting_stages）到達を
      検知して自動承認する（GUI の承認ボタン相当）。False の場合はパイプライン側で
      素通りするため、ここでは何もしない。

    戻り値は同じ `job`（終了状態・成果物・テスト結果を保持）。
    """
    from web.routes.auto_run import _run_job

    emit = on_log or (lambda _line: None)

    worker = threading.Thread(target=_run_job, args=(job, depth, max_pages), daemon=True)
    worker.start()

    emitted = 0
    login_handled = False
    approved_gate = ""

    while worker.is_alive() or job.status not in TERMINAL_STATUSES:
        # 新規ログを配信する。
        current = len(job.log)
        if current > emitted:
            for line in job.log[emitted:current]:
                emit(line)
            emitted = current

        # ログイン入力待ち（discover でログイン壁を検知した場合のみ発生）。
        if job.status == "awaiting_input" and not login_handled:
            login_handled = True
            if login and login.get("username"):
                job._input_data = {
                    "type": "login",
                    "username": login.get("username", ""),
                    "password": login.get("password", ""),
                }
            else:
                job._input_data = {"type": "login", "skip": True}
            job._input_event.set()

        # 段階承認の自動解除（require_stage_approval=True のとき）。
        gate = job.awaiting_stage_id
        if job.status == "awaiting_stages" and gate and gate != approved_gate:
            approved_gate = gate
            job._stages_event.set()

        if not worker.is_alive() and job.status not in TERMINAL_STATUSES:
            # スレッドは終了したが終端状態が付いていない（キャンセル等）。
            break
        time.sleep(poll_interval)

    # 残りのログを吐き切る。
    if len(job.log) > emitted:
        for line in job.log[emitted:]:
            emit(line)
    return job


def autorun_exit_code(job: Any) -> int:
    """CLI 終了コードをジョブ状態とテスト結果から決める。

    0: テスト完走かつ失敗ゼロ / 1: 完走したがテスト失敗あり /
    2: 実行エラー（failed 等） / 130: キャンセル。
    """
    if job.status == "cancelled":
        return 130
    if job.status == "failed":
        return 2
    failed = int((job.test_results or {}).get("failed", 0) or 0)
    return 1 if failed > 0 else 0
