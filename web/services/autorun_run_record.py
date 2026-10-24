"""AutoRun 実行記録の保存（結果ページの判定・常時表示ログの素材）。

実行ログと未確認事項はジョブのメモリ上にしか無く、再起動や再読込で消える。
結果ページで「何が起きたか」を示すには、終端に達した時点で成果物として残す必要がある。
前回の記録は run_record.prev.json に退避し、「今回の変更分」の比較に使う。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RECORD_FILE = "run_record.json"
PREV_RECORD_FILE = "run_record.prev.json"


def _test_outcomes(qa: Path) -> dict[str, str]:
    """テスト名 → 結果。比較のために名前で引けるようにする。"""
    path = qa / "playwright_report.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("実行結果を読めません %s: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        return {}
    tests = data.get("tests") or data.get("results") or []
    outcomes: dict[str, str] = {}
    for t in tests:
        if isinstance(t, dict):
            name = str(t.get("title") or t.get("name") or "").strip()
            if name:
                outcomes[name] = str(t.get("status") or "")
    return outcomes


def build_record(job_dict: dict[str, Any], qa: Path) -> dict[str, Any]:
    """ジョブの状態から保存用の記録を作る（入力を変更しない）。"""
    input_request = job_dict.get("input_request") or {}
    return {
        "job_id": job_dict.get("job_id", ""),
        "url": job_dict.get("url", ""),
        "status": job_dict.get("status", ""),
        "error": job_dict.get("error", ""),
        "started_at": job_dict.get("started_at", ""),
        "finished_at": job_dict.get("finished_at", ""),
        "log": list(job_dict.get("log") or []),
        "unverified": list(job_dict.get("unverified") or []),
        "input_request_type": input_request.get("type", "") if isinstance(input_request, dict) else "",
        "login_required": int(((job_dict.get("step_data") or {}).get("discover") or {}).get("login_required") or 0),
        "test_results": job_dict.get("test_results") or {},
        "test_outcomes": _test_outcomes(qa),
    }


def save_run_record(job_dict: dict[str, Any], qa: Path) -> Path | None:
    """記録を書き、既存の記録を前回分として退避する。失敗しても実行を壊さない。"""
    try:
        qa.mkdir(parents=True, exist_ok=True)
        current = qa / RECORD_FILE
        if current.is_file():
            current.replace(qa / PREV_RECORD_FILE)
        current.write_text(
            json.dumps(build_record(job_dict, qa), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return current
    except OSError as exc:
        logger.warning("実行記録を保存できません %s: %s", qa, exc)
        return None
