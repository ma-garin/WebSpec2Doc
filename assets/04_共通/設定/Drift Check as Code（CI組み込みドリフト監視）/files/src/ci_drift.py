"""CI向けドリフトサマリの保存とstdout契約。"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

DRIFT_SUMMARY_FILE_NAME = "drift_summary.json"


def save_drift_summary(
    diff: object | None,
    output_dir: Path,
    target_url: str,
    *,
    first_run: bool,
    report_file_name: str,
) -> bool:
    """CI・外部連携向けの版付きドリフトサマリを毎回保存する。"""

    def count(name: str) -> int:
        return len(getattr(diff, name, ()) or ()) if diff is not None else 0

    counts = {
        "added_pages": count("added_pages"),
        "removed_pages": count("removed_pages"),
        "field_changes": count("field_changes"),
        "link_changes": count("link_changes"),
        "title_changes": count("title_changes"),
        "api_changes": count("api_changes"),
    }
    severity_counts = {"breaking": 0, "warning": 0, "info": 0}
    if diff is not None:
        for item in getattr(diff, "attribute_diffs", ()) or ():
            severity = str(getattr(item, "severity", ""))
            if severity in severity_counts:
                severity_counts[severity] += 1
    has_changes = not first_run and bool(any(counts.values()) or any(severity_counts.values()))
    payload = {
        "version": 1,
        "site_url": target_url,
        "compared_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "first_run": first_run,
        "has_changes": has_changes,
        "counts": counts,
        "severity_counts": severity_counts,
        "report_url": str(output_dir / report_file_name),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / DRIFT_SUMMARY_FILE_NAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return has_changes


def emit_ci_summary(output_dir: Path, *, exit_code: int) -> None:
    """CIログへ解析しやすい単一行サマリを出力する。"""
    summary_path = output_dir / DRIFT_SUMMARY_FILE_NAME
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {
            "version": 1,
            "first_run": False,
            "has_changes": False,
            "error": "drift_summary_unavailable",
        }
        exit_code = 2
    payload["exit_code"] = exit_code
    _write_ci_line(payload)


def emit_ci_error(error: str) -> None:
    _write_ci_line(
        {
            "version": 1,
            "has_changes": False,
            "error": error,
            "exit_code": 2,
        }
    )


def _write_ci_line(payload: dict[str, object]) -> None:
    sys.stdout.write(
        "CI_SUMMARY:"
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    )
    sys.stdout.flush()
