"""準備状態ゲート（ルールベース）。reasons には必ず根拠数値を含める。AI は承認しない。"""
from __future__ import annotations

from typing import Any

from .testability import to_dict

DEFAULT_POLICY = {
    "min_overall": 70.0, "min_dimension": 60.0, "min_trace_coverage": 0.8,
    "major_dimensions": ("Testability", "Consistency", "Completeness", "Clarity"),
    "required_sections": (), "present_sections": (),
    "approval_required": False, "approved": False,
    "testability": {}, "requirement_severity": {},
}


def _sd(s: Any) -> dict:
    return to_dict(s) if s is not None else {}


def gate(scores: dict, findings: list, conflicts: list, policy: dict | None = None) -> dict:
    p = {**DEFAULT_POLICY, **(policy or {})}
    sc = {k: _sd(v) for k, v in (scores or {}).items()}
    fs = [to_dict(f) for f in (findings or [])]
    cs = [to_dict(c) for c in (conflicts or [])]
    blocked: list[str] = []
    crit_open = [c for c in cs if c.get("severity") == "critical"
                 and c.get("status", "OPEN") not in ("RESOLVED", "CONFIRMED_RESOLVED", "REJECTED")
                 and not c.get("resolved")]
    if crit_open:
        blocked.append(f"未解決の critical 矛盾が {len(crit_open)} 件")
    miss = [s for s in p["required_sections"] if s not in set(p["present_sections"])]
    if miss:
        blocked.append(f"必須セクション欠落 {len(miss)} 件（{', '.join(miss)}）")
    crit_nt = {f.get("requirement_id") for f in fs if f.get("severity") == "critical"
               and f.get("result") == "FAIL" and "TESTAB" in (f.get("rule_id") or "").upper()}
    crit_nt |= {r for r, v in p["testability"].items()
                if v == "NOT_TESTABLE" and p["requirement_severity"].get(r) == "critical"}
    if crit_nt:
        blocked.append(f"critical かつ NOT_TESTABLE の要件が {len(crit_nt)} 件")
    if p["approval_required"] and not p["approved"]:
        blocked.append("承認未完（approved=False）")
    if blocked:
        return {"state": "BLOCKED", "reasons": blocked}

    overall = sc.get("Overall", {})
    evaluated = [k for k, v in sc.items() if k != "Overall" and v.get("value") is not None]
    if not sc or (overall.get("value") is None and not evaluated):
        return {"state": "DRAFT", "reasons": [f"評価済み次元 {len(evaluated)} 件（全体 coverage={overall.get('coverage', 0)}）。評価不能のため DRAFT"]}

    unevaluated = [d for d in p["major_dimensions"] if sc.get(d, {}).get("value") is None]
    if unevaluated:
        return {"state": "REVIEWABLE",
                "reasons": [f"主要次元 {len(unevaluated)} 件が評価不能（{', '.join(unevaluated)}）のため READY にしない"]}

    high = [f for f in fs if f.get("severity") == "high" and f.get("result") == "FAIL"]
    tr = sc.get("Traceability", {})
    trace_cov = tr.get("coverage", 0.0) or 0.0
    cond: list[str] = []
    if high:
        cond.append(f"high 指摘 {len(high)} 件")
    if trace_cov < p["min_trace_coverage"]:
        cond.append(f"trace coverage {trace_cov} < {p['min_trace_coverage']}")
    if cond:
        return {"state": "CONDITIONALLY_READY", "reasons": cond}

    low_dims = [f"{d}={sc[d]['value']}" for d in p["major_dimensions"] if sc[d]["value"] < p["min_dimension"]]
    ov = overall.get("value")
    if ov is None or ov < p["min_overall"] or low_dims:
        return {"state": "REVIEWABLE",
                "reasons": [f"Overall={ov}（基準 {p['min_overall']}）", *([f"基準 {p['min_dimension']} 未満: {', '.join(low_dims)}"] if low_dims else [])]}
    return {"state": "READY",
            "reasons": [f"Overall={ov} >= {p['min_overall']}", f"主要次元すべて >= {p['min_dimension']}",
                        f"trace coverage {trace_cov} >= {p['min_trace_coverage']}", "high 指摘 0 件"]}
