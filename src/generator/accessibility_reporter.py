"""axe-core 実測だけを独立したアクセシビリティ監査成果物へ変換する。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ux.axe_runner import axe_violation_to_dict

if TYPE_CHECKING:
    from crawler.page_crawler import PageData
    from ux.axe_runner import AxeViolation

ACCESSIBILITY_AUDIT_FILE_NAME = "accessibility_audit.json"
DISCLAIMER = (
    "axe-core による機械判定可能な項目だけの一次スクリーニングです。"
    "WCAG/JIS X 8341-3 への適合を保証せず、残りの項目は人による手動確認が必要です。"
)


def build_accessibility_audit(
    pages: list[PageData],
    page_ids: dict[str, str],
    axe_results: dict[str, tuple[AxeViolation, ...]],
) -> dict[str, Any]:
    screens: list[dict[str, Any]] = []
    impact_counts = {impact: 0 for impact in ("critical", "serious", "moderate", "minor")}
    total = 0
    for page in pages:
        violations = [axe_violation_to_dict(item) for item in axe_results.get(page.url, ())]
        total += len(violations)
        for violation in violations:
            impact = str(violation.get("impact") or "")
            if impact in impact_counts:
                impact_counts[impact] += 1
        screens.append(
            {
                "page_id": page_ids.get(page.url, ""),
                "url": page.url,
                "title": page.title,
                "screenshot_path": page.screenshot_path,
                "violations": violations,
            }
        )
    return {
        "meta": {
            "engine": "axe-core",
            "disclaimer": DISCLAIMER,
            "manual_review_required": True,
        },
        "summary": {"violations": total, **impact_counts},
        "screens": screens,
    }


def save_accessibility_audit(payload: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / ACCESSIBILITY_AUDIT_FILE_NAME
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
