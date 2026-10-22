"""確度の算出。AI の自己申告だけに頼らず、観測できる信号から出す（根拠 basis を必ず返す）。"""
from __future__ import annotations

from typing import Any

SELF_WEIGHT = 0.15  # 自己申告は上限 0.15 までしか効かない


def calibrate_detail(finding: dict, signals: dict | None) -> dict[str, Any]:
    """signals: direct_evidence(bool|int) / sources(int) / contradictions(int) /
    rule_verified(bool) / reviewer_agreement(int: 同じ対象を指摘した他 Reviewer 数)。"""
    s = signals or {}
    value, basis = 0.05, ["base 0.05"]
    try:
        self_c = max(0.0, min(1.0, float(finding.get("confidence", 0.0))))
    except (TypeError, ValueError):
        self_c = 0.0
    add = round(self_c * SELF_WEIGHT, 3)
    value += add
    basis.append(f"self_reported {self_c:.2f} x {SELF_WEIGHT} = +{add}")
    if s.get("direct_evidence"):
        value += 0.35
        basis.append("direct_evidence +0.35")
    n = max(0, int(s.get("sources", 0) or 0))
    if n:
        add = 0.08 * min(n, 3)
        value += add
        basis.append(f"sources={n} +{add:.2f}")
    if s.get("rule_verified"):
        value += 0.25
        basis.append("rule_verified +0.25")
    agree = max(0, int(s.get("reviewer_agreement", 0) or 0))
    if agree:
        add = 0.07 * min(agree, 3)
        value += add
        basis.append(f"reviewer_agreement={agree} +{add:.2f}")
    contra = max(0, int(s.get("contradictions", 0) or 0))
    if contra:
        sub = 0.2 * min(contra, 3)
        value -= sub
        basis.append(f"contradictions={contra} -{sub:.2f}")
    if not s.get("direct_evidence"):
        value = min(value, 0.4)
        basis.append("no direct evidence: cap 0.4")
    value = round(max(0.0, min(1.0, value)), 3)
    return {"confidence": value, "basis": tuple(basis)}


def calibrate(finding: dict, signals: dict | None) -> float:
    return calibrate_detail(finding, signals)["confidence"]
