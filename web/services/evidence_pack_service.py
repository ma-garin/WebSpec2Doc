"""AutoRun の実行結果から証跡パックを生成する配線層。

材料の読み取りと保存だけを担い、組み立ての判断は src/evidence/ に置く。
生成に失敗しても AutoRun 本体は止めない（証跡は付加価値であり、実行結果そのものは
すでに job.outputs に残っているため）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from evidence.pack_model import build_evidence_pack
from evidence.pack_reporter import save_evidence_pack
from web.services.auto_run_job import AutoRunJob

logger = logging.getLogger(__name__)

AUDIT_EXCERPT_LIMIT = 50


def generate_evidence_pack(job: AutoRunJob, output_dir: Path) -> dict[str, Path]:
    """証跡パックを生成し、書き出したファイルのパスを返す。"""
    domain_dir = output_dir / job.domain
    qa_dir = domain_dir / "qa_process"

    pack = build_evidence_pack(
        report=_read_json(qa_dir / "playwright_report.json"),
        viewpoints=_read_json(qa_dir / "quality_viewpoints.json"),
        meta=_read_json(qa_dir / "autorun.meta.json"),
        classifications=job.failure_classifications or None,
        screenshots=_screenshots_by_page(domain_dir),
        manual_procedures=_read_text(qa_dir / "manual_procedures.md"),
        audit_entries=_read_audit_tail(domain_dir / "audit.jsonl"),
        mutation_check=_read_json(qa_dir / "mutation_verification.json"),
    )
    return save_evidence_pack(pack, qa_dir)


def attach_evidence_pack(job: AutoRunJob, output_dir: Path) -> None:
    """証跡パックを生成して job.outputs へ登録する。失敗しても実行結果は壊さない。"""
    try:
        outputs = generate_evidence_pack(job, output_dir)
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("証跡パックを生成できませんでした: %s", exc)
        job.add_log(f"証跡パックの生成に失敗しました（実行結果は保持）: {exc}")
        return
    for key, path in outputs.items():
        if path.is_file():
            job.outputs[key] = str(path.resolve())
    job.add_log("検収用の証跡パックを生成しました（実行した事実の記録）")


# ─────────────────── 材料の読み取り ───────────────────


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _screenshots_by_page(domain_dir: Path) -> dict[str, str]:
    """実在する画面キャプチャだけを page_id -> 相対パス で返す。"""
    shots_dir = domain_dir / "screenshots"
    if not shots_dir.is_dir():
        return {}
    return {path.stem: f"../screenshots/{path.name}" for path in sorted(shots_dir.glob("*.png"))}


def _read_audit_tail(path: Path, limit: int = AUDIT_EXCERPT_LIMIT) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            entries.append(item)
    return entries
