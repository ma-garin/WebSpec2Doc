"""指摘への利用者フィードバック。集計は提案のみで、ルールは自動変更しない。"""
from __future__ import annotations

from datetime import datetime, timezone

from . import _sidecar

_NAME = "assurance_feedback.json"
KINDS = ("useful", "false_positive", "not_applicable")


def add(iid: str, finding_id: str, kind: str, by: str = "") -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind が不正です: {kind}")
    if not finding_id:
        raise ValueError("finding_id が空です")
    entry = {"kind": kind, "by": by, "at": datetime.now(timezone.utc).isoformat(),
             "rule_id": finding_id.split(":")[0]}
    _sidecar.update(iid, _NAME, {}, lambda d: {**d, finding_id: entry})
    return {finding_id: entry}


def stats(iid: str, requirement_count: int = 0, finding_count: int = 0) -> dict:
    per: dict = {}
    for e in _sidecar.load(iid, _NAME, {}).values():
        r = per.setdefault(e["rule_id"], {"useful": 0, "false_positive": 0, "not_applicable": 0})
        r[e["kind"]] += 1
    for r in per.values():
        n = sum(r.values())
        r["dismiss_rate"] = round((r["false_positive"] + r["not_applicable"]) / n, 3) if n else 0.0
    suggestions = [{"rule_id": k, "proposal": "誤検知が多いルールです。しきい値・語彙の見直しを検討してください（自動では変更しません）"}
                   for k, v in per.items() if v["dismiss_rate"] >= 0.5 and v["false_positive"] + v["not_applicable"] >= 3]
    return {"rules": per, "suggestions": suggestions,
            "issue_density": round(finding_count / requirement_count, 3) if requirement_count else None}
