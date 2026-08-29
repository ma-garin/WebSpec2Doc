"""テスト実行ジョブの参照・中止 API。

投入は各機能側（例: /api/test-steps/<domain>/run）が行い、ここは
「今どうなっているか」を返すことに徹する。実行中は完了を待たずに、
Playwright の進捗レポーターが書く NDJSON をそのまま読んで返す
（完了までブロックすると、画面は数分間なにも出せない）。

domain は必ず検証してからパス要素へ渡す。検証せずに渡すと `../` で
他テナントの出力を読めてしまう。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from flask import Blueprint

from web.services import test_run_job
from web.validation import _valid_domain

logger = logging.getLogger(__name__)

bp = Blueprint("test_runs", __name__)

#: 実行中の進捗が書かれる NDJSON のファイル名（Playwright の進捗レポーター）
_PROGRESS_NAME = "playwright_progress.ndjson"


def _progress_payload(output_dir: str) -> dict[str, Any] | None:
    """実行中ジョブの進捗。ファイルが無ければ None（0 件と未計測を混同しない）。

    「まだ 1 件も終わっていない（total=0/done=0）」と「進捗が取れない」を
    同じ形で返すと、画面は 0 件を実測値として表示してしまう。取れないときは
    キーごと返さない。
    """
    from web.services.playwright_executor import _read_progress_ndjson

    path = Path(output_dir) / _PROGRESS_NAME
    if not path.is_file():
        return None
    total, tests = _read_progress_ndjson(path)
    if total is None and not tests:
        return None
    return {
        "total": total or 0,
        "done": len(tests),
        "passed": sum(1 for t in tests if t.get("status") == "passed"),
        "failed": sum(1 for t in tests if t.get("status") == "failed"),
        # 画面に出すのは直近分だけでよい（全件は完了後の成果物が持つ）
        "tests": tests[-40:],
    }


@bp.get("/api/test-runs/<domain>/jobs")
def api_list_jobs(domain: str) -> dict | tuple[dict, int]:
    """ドメインの実行ジョブ一覧（メモリ＋履歴 jsonl のマージ、新しい順）。"""
    if not _valid_domain(domain):
        return {"error": "not found"}, 404
    jobs = test_run_job.list_jobs(domain)
    return {"jobs": jobs, "total": len(jobs)}


@bp.get("/api/test-runs/jobs/<job_id>")
def api_get_job(job_id: str) -> dict | tuple[dict, int]:
    """ジョブ詳細。running 中は進捗（progress）も返す。"""
    job = test_run_job.get_job(job_id)
    if job is None:
        return {"error": "ジョブが見つかりません（job_id が古い可能性があります）。"}, 404
    payload = job.to_dict()
    payload["queued_position"] = test_run_job.queued_position(job_id)
    payload["elapsed_sec"] = job.elapsed_sec()
    if job.status == "running":
        progress = _progress_payload(job.output_dir)
        if progress is not None:
            payload["progress"] = progress
    return payload


@bp.post("/api/test-runs/jobs/<job_id>/cancel")
def api_cancel_job(job_id: str) -> dict | tuple[dict, int]:
    """ジョブを中止する。

    404: 未知の job_id / 409: すでに終了している（中止しようがない）
    """
    outcome = test_run_job.cancel_job(job_id)
    if outcome == "not_found":
        return {"error": "ジョブが見つかりません（job_id が古い可能性があります）。"}, 404
    if outcome == "already_finished":
        return {"error": "このジョブはすでに終了しています。", "status": outcome}, 409
    return {"cancelled": True, "job_id": job_id, "status": outcome}
