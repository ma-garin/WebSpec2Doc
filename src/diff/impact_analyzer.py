from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

SEVERITY_BREAKING = "breaking"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

_URL_PATTERN = re.compile(r"page\.goto\(['\"]([^'\"]+)['\"]\)")


@dataclass(frozen=True)
class ImpactedTest:
    test_id: str
    reason: str
    page_url: str
    severity: str  # "breaking" / "warning" / "info"


def analyze_impact(
    diff_result: Any,  # DiffResult（循環 import 回避のため Any）
    candidates: list[dict],  # playwright_candidates.json の candidates リスト
) -> list[ImpactedTest]:
    """DiffResult と spec.ts 候補リストを照合し、再実行が必要なテストを返す。"""
    results: list[ImpactedTest] = []
    results.extend(_impacts_from_field_changes(diff_result, candidates))
    results.extend(_impacts_from_added_pages(diff_result, candidates))
    results.extend(_impacts_from_removed_pages(diff_result, candidates))
    results.extend(_impacts_from_attribute_diffs(diff_result, candidates))
    return _deduplicate(results)


def format_impact_report(impacted_tests: list[ImpactedTest]) -> dict:
    """影響分析結果を JSON シリアライズ可能な dict で返す。"""
    breaking = sum(1 for t in impacted_tests if t.severity == SEVERITY_BREAKING)
    warning = sum(1 for t in impacted_tests if t.severity == SEVERITY_WARNING)
    info = sum(1 for t in impacted_tests if t.severity == SEVERITY_INFO)
    return {
        "total": len(impacted_tests),
        "breaking": breaking,
        "warning": warning,
        "info": info,
        "tests": [
            {
                "test_id": t.test_id,
                "reason": t.reason,
                "page_url": t.page_url,
                "severity": t.severity,
            }
            for t in impacted_tests
        ],
    }


def _extract_url_from_steps(steps: list[Any]) -> str:
    """steps リストから page.goto('...') の URL を抽出する。"""
    for step in steps:
        m = _URL_PATTERN.search(str(step))
        if m:
            return m.group(1)
    return ""


def _candidate_url(candidate: dict) -> str:
    steps: list[Any] = candidate.get("steps") or []
    return _extract_url_from_steps(steps)


def _impacts_from_field_changes(
    diff_result: Any,
    candidates: list[dict],
) -> list[ImpactedTest]:
    impacts: list[ImpactedTest] = []
    field_changes = getattr(diff_result, "field_changes", ()) or ()
    for fc in field_changes:
        page_url: str = getattr(fc, "page_url", "")
        field_name: str = getattr(fc, "field_name", "")
        change_type: str = getattr(fc, "change_type", "")
        for candidate in candidates:
            if _candidate_url(candidate) == page_url:
                reason = f"フィールド '{field_name}' が {change_type}"
                severity = _severity_for_change_type(change_type)
                impacts.append(
                    ImpactedTest(
                        test_id=str(candidate.get("id", "")),
                        reason=reason,
                        page_url=page_url,
                        severity=severity,
                    )
                )
    return impacts


def _impacts_from_added_pages(
    diff_result: Any,
    candidates: list[dict],
) -> list[ImpactedTest]:
    impacts: list[ImpactedTest] = []
    added_pages = getattr(diff_result, "added_pages", ()) or ()
    for page in added_pages:
        page_url: str = getattr(page, "url", "")
        impacts.append(
            ImpactedTest(
                test_id="",
                reason="新規画面追加",
                page_url=page_url,
                severity=SEVERITY_INFO,
            )
        )
    return impacts


def _impacts_from_removed_pages(
    diff_result: Any,
    candidates: list[dict],
) -> list[ImpactedTest]:
    impacts: list[ImpactedTest] = []
    removed_pages = getattr(diff_result, "removed_pages", ()) or ()
    for page in removed_pages:
        page_url: str = getattr(page, "url", "")
        matching = [c for c in candidates if _candidate_url(c) == page_url]
        if matching:
            for candidate in matching:
                impacts.append(
                    ImpactedTest(
                        test_id=str(candidate.get("id", "")),
                        reason="画面削除",
                        page_url=page_url,
                        severity=SEVERITY_BREAKING,
                    )
                )
        else:
            impacts.append(
                ImpactedTest(
                    test_id="",
                    reason="画面削除",
                    page_url=page_url,
                    severity=SEVERITY_BREAKING,
                )
            )
    return impacts


def _impacts_from_attribute_diffs(
    diff_result: Any,
    candidates: list[dict],
) -> list[ImpactedTest]:
    impacts: list[ImpactedTest] = []
    attribute_diffs = getattr(diff_result, "attribute_diffs", ()) or ()
    breaking_diffs = [d for d in attribute_diffs if getattr(d, "severity", "") == SEVERITY_BREAKING]
    for ad in breaking_diffs:
        page_url: str = getattr(ad, "page_url", "")
        field_name: str = getattr(ad, "field_name", "")
        attribute: str = getattr(ad, "attribute", "")
        before: str = getattr(ad, "before", "")
        after: str = getattr(ad, "after", "")
        for candidate in candidates:
            if _candidate_url(candidate) == page_url:
                reason = f"フィールド '{field_name}' の {attribute} が変化 ({before} → {after})"
                impacts.append(
                    ImpactedTest(
                        test_id=str(candidate.get("id", "")),
                        reason=reason,
                        page_url=page_url,
                        severity=SEVERITY_BREAKING,
                    )
                )
    return impacts


def _severity_for_change_type(change_type: str) -> str:
    if change_type == "removed":
        return SEVERITY_BREAKING
    if change_type == "modified":
        return SEVERITY_WARNING
    return SEVERITY_INFO


def _deduplicate(impacts: list[ImpactedTest]) -> list[ImpactedTest]:
    """test_id + reason + page_url の重複を除去する。"""
    seen: set[tuple[str, str, str]] = set()
    result: list[ImpactedTest] = []
    for item in impacts:
        key = (item.test_id, item.reason, item.page_url)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
