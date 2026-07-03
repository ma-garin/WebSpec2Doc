"""差分検出結果と生成テストのメタデータを照合し、再実行が必要なテストを特定する。

テストの特定は spec_ts_generator が併産するメタデータ JSON
（test_id・page_id・fingerprint・url）との照合で行う。URL 文字列が変わっても
fingerprint が一致すれば同一画面のテストとして影響を特定できる。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from analyzer.html_analyzer import AnalyzedPage
    from diff.differ import DiffResult

logger = logging.getLogger(__name__)

SEVERITY_BREAKING = "breaking"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


@dataclass(frozen=True)
class ImpactedTest:
    test_id: str
    reason: str
    page_url: str
    severity: str  # "breaking" / "warning" / "info"


def build_url_fingerprints(pages: list[AnalyzedPage]) -> dict[str, str]:
    """AnalyzedPage リストから URL → fingerprint のマップを構築する。"""
    from analyzer.canonicalizer import group_canonical_screens

    canonical = group_canonical_screens(pages)
    return {
        page.page_data.url: canonical[page.page_id].fingerprint
        for page in pages
        if page.page_id in canonical
    }


def analyze_impact(
    diff_result: DiffResult,
    test_metadata: list[dict],
    url_fingerprints: dict[str, str] | None = None,
) -> list[ImpactedTest]:
    """DiffResult とテストメタデータ JSON を照合し、再実行が必要なテストを返す。

    test_metadata: spec_ts_generator が併産するメタデータ（tests リスト）。
        各要素は test_id / page_id / fingerprint / url を持つ。
    url_fingerprints: page_url → fingerprint のマップ（新旧スナップショット由来）。
        fingerprint 一致を優先し、なければ URL 完全一致にフォールバックする。
    """
    fingerprints = url_fingerprints or {}
    results: list[ImpactedTest] = []
    results.extend(_impacts_from_field_changes(diff_result, test_metadata, fingerprints))
    results.extend(_impacts_from_added_pages(diff_result))
    results.extend(_impacts_from_removed_pages(diff_result, test_metadata, fingerprints))
    results.extend(_impacts_from_attribute_diffs(diff_result, test_metadata, fingerprints))
    return _deduplicate(results)


def format_impact_report(impacted_tests: list[ImpactedTest]) -> dict:
    """影響分析結果を JSON シリアライズ可能な dict で返す（再実行推奨リスト付き）。"""
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
        # 再実行推奨: breaking / warning のテスト ID（重複除去・順序保持）
        "rerun_recommended": list(
            dict.fromkeys(
                t.test_id
                for t in impacted_tests
                if t.test_id and t.severity in (SEVERITY_BREAKING, SEVERITY_WARNING)
            )
        ),
    }


def _tests_for_page(
    page_url: str,
    test_metadata: list[dict],
    url_fingerprints: dict[str, str],
) -> list[dict]:
    """変更ページに紐づくテストメタデータを返す。

    fingerprint 一致を優先し、見つからなければ URL 完全一致で照合する。
    """
    fingerprint = url_fingerprints.get(page_url, "")
    if fingerprint:
        matched = [m for m in test_metadata if str(m.get("fingerprint") or "") == fingerprint]
        if matched:
            return matched
    return [m for m in test_metadata if str(m.get("url") or "") == page_url]


def _test_id_of(metadata: dict) -> str:
    return str(metadata.get("test_id") or metadata.get("id") or "")


def _impacts_from_field_changes(
    diff_result: DiffResult,
    test_metadata: list[dict],
    url_fingerprints: dict[str, str],
) -> list[ImpactedTest]:
    impacts: list[ImpactedTest] = []
    field_changes = getattr(diff_result, "field_changes", ()) or ()
    for fc in field_changes:
        page_url: str = getattr(fc, "page_url", "")
        field_name: str = getattr(fc, "field_name", "")
        change_type: str = getattr(fc, "change_type", "")
        reason = f"フィールド '{field_name}' が {change_type}"
        severity = _severity_for_change_type(change_type)
        for metadata in _tests_for_page(page_url, test_metadata, url_fingerprints):
            impacts.append(
                ImpactedTest(
                    test_id=_test_id_of(metadata),
                    reason=reason,
                    page_url=page_url,
                    severity=severity,
                )
            )
    return impacts


def _impacts_from_added_pages(diff_result: DiffResult) -> list[ImpactedTest]:
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
    diff_result: DiffResult,
    test_metadata: list[dict],
    url_fingerprints: dict[str, str],
) -> list[ImpactedTest]:
    impacts: list[ImpactedTest] = []
    removed_pages = getattr(diff_result, "removed_pages", ()) or ()
    for page in removed_pages:
        page_url: str = getattr(page, "url", "")
        matching = _tests_for_page(page_url, test_metadata, url_fingerprints)
        if matching:
            for metadata in matching:
                impacts.append(
                    ImpactedTest(
                        test_id=_test_id_of(metadata),
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
    diff_result: DiffResult,
    test_metadata: list[dict],
    url_fingerprints: dict[str, str],
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
        reason = f"フィールド '{field_name}' の {attribute} が変化 ({before} → {after})"
        for metadata in _tests_for_page(page_url, test_metadata, url_fingerprints):
            impacts.append(
                ImpactedTest(
                    test_id=_test_id_of(metadata),
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
