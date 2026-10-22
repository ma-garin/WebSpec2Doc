"""前版との回帰レビュー。条件・異常系の文が消えたものは欠落の候補（CANDIDATE）として出す。"""
from __future__ import annotations

from . import baseline, semantic_diff
from .model import CANDIDATE

COND_WORDS = ("の場合", "場合は", "とき", "時は", "エラー", "失敗時", "失敗した", "拒否", "例外", "却下", "タイムアウト", "不正")
_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def _lost(text_b: str, text_a: str) -> list[str]:
    return [w for w in COND_WORDS if w in text_b and w not in text_a]


def lost_conditions(before_reqs: list, after_reqs: list) -> list[dict]:
    out = []
    for d in semantic_diff.diff(before_reqs, after_reqs):
        if d["change"] not in ("REMOVED", "MODIFIED"):
            continue
        tb = (d.get("before") or {}).get("text", "")
        ta = (d.get("after") or {}).get("text", "") if d["change"] == "MODIFIED" else ""
        words = _lost(tb, ta)
        if words:
            out.append({"requirement_id": d["requirement_id"], "change": d["change"], "lost_terms": words,
                        "before_text": tb[:200], "status": CANDIDATE,
                        "note": "条件・異常系の記述が消えた可能性。意図した削除か確認してください"})
    return out


def _conflict_key(c: dict) -> str:
    ids = c.get("requirement_ids") or c.get("requirements") or c.get("ids") or []
    return f"{c.get('type') or c.get('kind') or ''}|{'/'.join(sorted(map(str, ids)))}" if ids else str(c.get("id") or c)


def review(before: dict, after: dict) -> dict:
    bk, ak = baseline.keyed(before), baseline.keyed(after)
    resolved_before = set(before.get("resolved_keys") or [])
    has_findings = "findings" in before
    new_issues = [baseline._slim(f) for k, f in ak.items() if k not in bk] if has_findings else []
    resolved = [baseline._slim(f) for k, f in bk.items() if k not in ak]
    reopened = [baseline._slim(f) for k, f in ak.items() if k in resolved_before and k not in bk]
    sev = [{"finding_id": ak[k].get("finding_id"), "rule_id": ak[k].get("rule_id"),
            "before": bk[k].get("severity"), "after": ak[k].get("severity")}
           for k in ak if k in bk and bk[k].get("severity") != ak[k].get("severity")]
    bc = {_conflict_key(c) for c in before.get("conflicts") or []}
    new_conf = [c for c in after.get("conflicts") or [] if _conflict_key(c) not in bc] if "conflicts" in before else []
    trace = None
    tb, ta = (before.get("scores") or {}).get("Traceability"), (after.get("scores") or {}).get("Traceability")
    if tb and ta and tb.get("value") is not None and ta.get("value") is not None and ta["value"] < tb["value"]:
        trace = {"before": tb["value"], "after": ta["value"], "delta": round(ta["value"] - tb["value"], 1)}
    return {"new_issues": new_issues, "resolved": resolved, "reopened": reopened, "severity_changed": sev,
            "new_conflicts": new_conf, "trace_degradation": trace,
            "missing_candidates": lost_conditions(before.get("requirements") or [], after.get("requirements") or []),
            "compared_findings": has_findings}
