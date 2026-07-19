"""UXレビュー成果物の主張境界（第7弾 F）。

守るべきは「自動検出できる範囲の観測であること」を成果物が必ず明示し、
かつ経年で嘘になる数値（捕捉率%）を載せないこと。
"""

from __future__ import annotations

from generator.accessibility_reporter import build_accessibility_audit
from generator.ux_reporter import UX_CLAIM_SCOPE, build_ux_review


def test_ux_review_declares_automated_subset_claim_scope() -> None:
    review = build_ux_review(pages=[], page_ids={}, axe_results={}, ux_findings={})

    assert review["meta"]["claim_scope"] == UX_CLAIM_SCOPE
    assert "自動検出可能な範囲" in review["meta"]["disclaimer"]


def test_ux_disclaimer_does_not_hardcode_coverage_percentage() -> None:
    review = build_ux_review(pages=[], page_ids={}, axe_results={}, ux_findings={})

    disclaimer = review["meta"]["disclaimer"]
    assert "30" not in disclaimer and "40" not in disclaimer and "%" not in disclaimer


def test_accessibility_audit_declares_claim_scope() -> None:
    audit = build_accessibility_audit(pages=[], page_ids={}, axe_results={})

    assert audit["meta"]["claim_scope"] == "automated_detectable_subset_only"
    assert audit["meta"]["manual_review_required"] is True
