"""AutoRun承認前プレビューの読み取りモデル。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from web.services.auto_run_job import AutoRunJob
from web.services.document_autorun import candidate_filename
from web.services.spec_ts_generator import compute_filter_counts


def build_autorun_preview(job: AutoRunJob, output_dir: Path) -> dict[str, Any]:
    """選定済み候補の集計と生成済みspec内容を返す。"""
    candidates_path = output_dir / job.domain / "qa_process" / candidate_filename(job.mode)
    result: dict[str, Any] = {"job_id": job.job_id, "domain": job.domain}
    if candidates_path.is_file():
        try:
            data = json.loads(candidates_path.read_text(encoding="utf-8"))
            candidates: list[dict[str, Any]] = data.get("candidates", [])
            by_status: dict[str, int] = {}
            by_title: dict[str, int] = {}
            for candidate in candidates:
                status = candidate.get("automation_status", "")
                title = candidate.get("title", "")
                by_status[status] = by_status.get(status, 0) + 1
                by_title[title] = by_title.get(title, 0) + 1
            result["candidates"] = candidates
            result["summary"] = {
                "total": len(candidates),
                "by_status": by_status,
                "by_title": by_title,
                "filter_counts": compute_filter_counts(candidates),
            }
        except Exception as exc:
            result["candidates"] = []
            result["summary"] = {"error": str(exc)}
    else:
        result["candidates"] = []
        result["summary"] = {}

    spec_path = Path(job.outputs.get("spec_ts", ""))
    if spec_path.is_file():
        try:
            result["spec_content"] = spec_path.read_text(encoding="utf-8")
        except Exception:
            result["spec_content"] = ""
    else:
        result["spec_content"] = ""
    return result
