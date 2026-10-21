"""決定論の分析を段階ごとに実行し、ステージ単位で失敗を隔離する。LLM は使わない（DEGRADED でも同じ結果）。"""
from __future__ import annotations

import hashlib
import time
from typing import Callable

from web.services.docassure import model as M

STAGES = ("structuring", "rules", "quality", "conflicts", "readiness")


def _d(x):
    return x.to_dict() if hasattr(x, "to_dict") else x


def _stage(name: str, fn: Callable, errors: list, default):
    t = time.monotonic()
    try:
        return fn(), round(time.monotonic() - t, 3)
    except Exception as e:  # ステージ失敗は隔離し、他の結果は返す（再実行可能）
        errors.append({"stage": name, "error": type(e).__name__})
        return default, round(time.monotonic() - t, 3)


def analyze(documents: list[dict], profile: str = "default", pack_extra: dict | None = None,
            policy: dict | None = None) -> dict:
    """documents: [{id,name,type,text}]。戻りは JSON 化できる dict。"""
    from web.services.docassure import conflict, quality, readiness, requirement_engine, testability
    from web.services.docassure.rules import engine as rules
    errors: list[dict] = []
    timings: dict[str, float] = {}
    docs = [{"id": str(d.get("id") or f"D{i+1}"), "name": d.get("name") or "", "type": d.get("type") or "other",
             "text": str(d.get("text") or ""),
             "hash": hashlib.sha1(str(d.get("text") or "").encode()).hexdigest()[:12]}
            for i, d in enumerate(documents)]
    texts = {d["id"]: d["text"] for d in docs}

    units_by_doc: dict[str, list] = {}

    def structure():
        for d in docs:
            units_by_doc[d["id"]] = requirement_engine.extract(d["id"], d["text"])
        return units_by_doc
    _, timings["structuring"] = _stage("structuring", structure, errors, None)

    findings: list = []
    results: list = []

    def run_rules():
        pack = rules.load_pack(profile, pack_extra)
        for d in docs:
            others = {k: v for k, v in texts.items() if k != d["id"]}
            r = rules.run_rules(d["id"], d["text"], units_by_doc.get(d["id"], []), pack, others)
            findings.extend(r["findings"])
            results.extend(r["results"])
    _, timings["rules"] = _stage("rules", run_rules, errors, None)

    all_units = [u for us in units_by_doc.values() for u in us]
    scores: dict = {}
    tests: dict = {}

    def run_quality():
        for u in all_units:
            tests[u.requirement_id] = testability.assess(u)
        scores.update(quality.score_document(all_units, findings))
    _, timings["quality"] = _stage("quality", run_quality, errors, None)

    conflicts: list = []
    _, timings["conflicts"] = _stage("conflicts", lambda: conflicts.extend(conflict.detect(units_by_doc)), errors, None)

    gate, timings["readiness"] = _stage("readiness", lambda: readiness.gate(scores, [_d(f) for f in findings],
                                                                          conflicts, policy), errors,
                                        {"state": M.DRAFT, "reasons": ["段階の失敗のため判定できません"]})
    if errors:  # 失敗した段階があるなら READY にしない
        gate = {**gate, "state": gate["state"] if gate["state"] in (M.DRAFT, "BLOCKED") else M.DRAFT,
                "reasons": [*gate["reasons"], "失敗した分析段階: " + ",".join(e["stage"] for e in errors)]}
    return {
        "documents": [{k: d[k] for k in ("id", "name", "type", "hash")} for d in docs],
        "requirements": [_d(u) for u in all_units],
        "findings": [_d(f) for f in findings],
        "rule_results": results,
        "testability": tests,
        "scores": {k: _d(v) for k, v in scores.items()},
        "conflicts": conflicts,
        "readiness": gate,
        "mode": "DETERMINISTIC_ONLY",
        "errors": errors,
        "timings": timings,
        "counts": {"documents": len(docs), "requirements": len(all_units), "findings": len(findings),
                   "conflicts": len(conflicts)},
    }
