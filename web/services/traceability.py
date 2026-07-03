from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RequirementLink:
    """1 つの要件とテストケースの対応。"""

    req_id: str
    req_title: str
    test_ids: tuple[str, ...]
    page_url: str
    coverage: str  # "covered" / "partial" / "uncovered"


@dataclass(frozen=True)
class TraceabilityMatrix:
    domain: str
    generated_at: str  # ISO 8601
    requirements: tuple[RequirementLink, ...]
    total_requirements: int
    covered_count: int
    coverage_rate: float  # 0.0〜1.0


def _collect_step_urls(candidates: list[dict]) -> set[str]:
    """candidates のすべての steps から URL を収集する。"""
    urls: set[str] = set()
    for cand in candidates:
        for step in cand.get("steps", []):
            url = step.get("url", "")
            if url:
                urls.add(url)
    return urls


def _collect_test_ids_for_url(url: str, candidates: list[dict]) -> tuple[str, ...]:
    """page_url と完全一致する URL を持つ candidates の ID を返す。"""
    ids: list[str] = []
    for cand in candidates:
        for step in cand.get("steps", []):
            if step.get("url", "") == url:
                cand_id = cand.get("id", "")
                if cand_id and cand_id not in ids:
                    ids.append(cand_id)
                break
    return tuple(ids)


def _collect_test_ids_prefix(url: str, candidates: list[dict]) -> tuple[str, ...]:
    """page_url の前方一致（完全一致以外）で candidates の ID を返す。"""
    ids: list[str] = []
    for cand in candidates:
        for step in cand.get("steps", []):
            step_url = step.get("url", "")
            if step_url and step_url != url and step_url.startswith(url):
                cand_id = cand.get("id", "")
                if cand_id and cand_id not in ids:
                    ids.append(cand_id)
                break
    return tuple(ids)


def _determine_coverage(
    exact_ids: tuple[str, ...], prefix_ids: tuple[str, ...]
) -> tuple[str, tuple[str, ...]]:
    """カバレッジ区分とテストケース ID リストを返す。"""
    if exact_ids:
        return "covered", exact_ids
    if prefix_ids:
        return "partial", prefix_ids
    return "uncovered", ()


def _collect_test_ids_by_metadata(screen: dict, test_metadata: list[dict]) -> tuple[str, ...]:
    """メタデータ JSON（test_id/page_id/fingerprint）で画面に紐づくテスト ID を返す。

    fingerprint 一致を優先し、なければ page_id 一致で照合する。
    """
    fingerprint = str(screen.get("fingerprint") or "")
    page_id = str(screen.get("page_id") or "")
    ids: list[str] = []
    for metadata in test_metadata:
        test_id = str(metadata.get("test_id") or "")
        if not test_id:
            continue
        matched = (fingerprint and str(metadata.get("fingerprint") or "") == fingerprint) or (
            page_id and str(metadata.get("page_id") or "") == page_id
        )
        if matched and test_id not in ids:
            ids.append(test_id)
    return tuple(ids)


def _build_requirement(
    index: int,
    screen: dict,
    candidates: list[dict],
    test_metadata: list[dict] | None = None,
) -> RequirementLink:
    """1 画面分の RequirementLink を構築する。

    メタデータ JSON（fingerprint / page_id）照合を優先し、
    メタデータがない場合は従来の URL 照合にフォールバックする。
    """
    req_id = f"REQ-{index + 1:03d}"
    req_title = screen.get("title", screen.get("url", req_id))
    page_url = screen.get("url", "")

    metadata_ids = _collect_test_ids_by_metadata(screen, test_metadata or [])
    if metadata_ids:
        coverage, test_ids = "covered", metadata_ids
    else:
        exact_ids = _collect_test_ids_for_url(page_url, candidates)
        prefix_ids = _collect_test_ids_prefix(page_url, candidates)
        coverage, test_ids = _determine_coverage(exact_ids, prefix_ids)

    return RequirementLink(
        req_id=req_id,
        req_title=req_title,
        test_ids=test_ids,
        page_url=page_url,
        coverage=coverage,
    )


def build_matrix(
    domain: str,
    report_data: dict,
    candidates: list[dict],
    test_metadata: list[dict] | None = None,
) -> TraceabilityMatrix:
    """report.json の各画面・フォームを「要件」として、
    それをカバーするテストケース（candidates / メタデータ JSON）を紐付ける。
    """
    screens: list[dict] = report_data.get("screens", [])
    requirements = tuple(
        _build_requirement(i, screen, candidates, test_metadata)
        for i, screen in enumerate(screens)
    )
    total = len(requirements)
    covered_count = sum(1 for r in requirements if r.coverage != "uncovered")
    coverage_rate = covered_count / total if total > 0 else 0.0

    return TraceabilityMatrix(
        domain=domain,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        requirements=requirements,
        total_requirements=total,
        covered_count=covered_count,
        coverage_rate=coverage_rate,
    )


def matrix_to_dict(matrix: TraceabilityMatrix) -> dict:
    """JSON シリアライズ可能な dict に変換して返す。"""
    return {
        "domain": matrix.domain,
        "generated_at": matrix.generated_at,
        "total_requirements": matrix.total_requirements,
        "covered_count": matrix.covered_count,
        "coverage_rate": matrix.coverage_rate,
        "requirements": [
            {
                "req_id": r.req_id,
                "req_title": r.req_title,
                "test_ids": list(r.test_ids),
                "page_url": r.page_url,
                "coverage": r.coverage,
            }
            for r in matrix.requirements
        ],
    }
