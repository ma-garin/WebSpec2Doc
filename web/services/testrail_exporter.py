"""TestRail の公式 CSV インポート形式でテストケースをエクスポートするサービス。"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

CSV_HEADER = ["Section", "Title", "Steps", "Expected Result", "Priority", "Type", "References"]
CSV_ENCODING = "utf-8-sig"

PRIORITY_CRITICAL = "Critical"
PRIORITY_HIGH = "High"
PRIORITY_MEDIUM = "Medium"
PRIORITY_LOW = "Low"

RISK_THRESHOLD_CRITICAL = 30
RISK_THRESHOLD_HIGH = 15
RISK_THRESHOLD_MEDIUM = 5

DEFAULT_EXPECTED = "仕様通り動作すること"
DEFAULT_CASE_TYPE = "Functional"


@dataclass(frozen=True)
class TestRailCase:
    """TestRail CSV の 1 行。"""

    section: str
    title: str
    steps: str
    expected: str
    priority: str
    case_type: str
    refs: str


def risk_score_to_priority(risk_score: float) -> str:
    """リスクスコアを TestRail の優先度ラベルに変換する。"""
    if risk_score >= RISK_THRESHOLD_CRITICAL:
        return PRIORITY_CRITICAL
    if risk_score >= RISK_THRESHOLD_HIGH:
        return PRIORITY_HIGH
    if risk_score >= RISK_THRESHOLD_MEDIUM:
        return PRIORITY_MEDIUM
    return PRIORITY_LOW


def export_to_testrail_csv(cases: list[TestRailCase], output_path: Path) -> Path:
    """TestRailCase のリストを BOM 付き UTF-8 CSV ファイルに書き出す。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding=CSV_ENCODING) as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        for case in cases:
            writer.writerow([
                case.section,
                case.title,
                case.steps,
                case.expected,
                case.priority,
                case.case_type,
                case.refs,
            ])
    logger.info("TestRail CSV 出力完了: %s (%d 件)", output_path, len(cases))
    return output_path


def build_testrail_cases_from_report(report_data: dict) -> list[TestRailCase]:
    """report.json の構造から TestRailCase リストを構築する。

    report_data は generate_json_report() が出力する dict を想定する。
    トップレベルキー "screens" の各要素に含まれるフォームフィールドの
    test_conditions をテストケースに変換する。
    """
    cases: list[TestRailCase] = []
    screens = report_data.get("screens", [])
    for screen in screens:
        title: str = screen.get("title", "")
        url: str = screen.get("url", "")
        for form in screen.get("forms", []):
            for field in form.get("fields", []):
                conditions: list[str] = field.get("test_conditions", [])
                if not conditions:
                    continue
                field_name: str = field.get("name", "") or field.get("element_id", "")
                case_title = f"{title} - {field_name}" if field_name else title
                steps = "\n".join(str(c) for c in conditions)
                cases.append(
                    TestRailCase(
                        section=title,
                        title=case_title,
                        steps=steps,
                        expected=DEFAULT_EXPECTED,
                        priority=PRIORITY_MEDIUM,
                        case_type=DEFAULT_CASE_TYPE,
                        refs=url,
                    )
                )
    return cases
