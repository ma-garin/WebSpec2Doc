"""文書のつながり（ノードと線）と結論の自動判定。"""
from __future__ import annotations

LEVEL_LABEL = {"pass": "合格", "conditional": "条件付き", "fail": "不合格"}
_EDGE_TYPE = {"CONFLICT": "conflict", "REVERSE_REF": "reverse_ref", "DUPLICATE": "duplicate"}


def _live(findings: list[dict], reports: dict) -> list[dict]:
    return [f for f in findings if f["id"] not in (reports or {})]


def _status(items: list[dict]) -> str:
    if any(f["severity"] == "high" for f in items):
        return "ng"
    return "warn" if items else "ok"


def _nodes(documents: list[dict], live: list[dict]) -> list[dict]:
    out = []
    for d in documents:
        mine = [f for f in live if f["doc_id"] == d["id"] or f.get("related_doc_id") == d["id"]]
        out.append({"id": d["id"], "name": d["name"], "tier": d["tier"], "status": _status(mine), "issues": len(mine)})
    return out


def _follows(documents: list[dict]) -> list[dict]:
    tiers = sorted({d["tier"] for d in documents})
    edges = []
    for d in documents:
        upper = [t for t in tiers if t < d["tier"]]
        if not upper:
            continue
        for u in documents:
            if u["tier"] == upper[-1]:
                edges.append({"from": d["id"], "to": u["id"], "type": "follows", "finding_ids": []})
    return edges


def _problem_edges(documents: list[dict], live: list[dict]) -> list[dict]:
    tier = {d["id"]: d["tier"] for d in documents}
    grouped: dict[tuple, list[str]] = {}
    for f in live:
        rel = f.get("related_doc_id")
        typ = _EDGE_TYPE.get(f["rule"])
        if not rel or not typ or rel not in tier or f["doc_id"] not in tier:
            continue
        a, b = f["doc_id"], rel
        if tier[a] < tier[b]:
            a, b = b, a
        grouped.setdefault((a, b, typ), []).append(f["id"])
    return [{"from": a, "to": b, "type": t, "finding_ids": ids} for (a, b, t), ids in grouped.items()]


def build(documents: list[dict], findings: list[dict], reports: dict) -> dict:
    live = _live(findings, reports)
    return {"nodes": _nodes(documents, live), "edges": _follows(documents) + _problem_edges(documents, live)}


def conclude(findings: list[dict], reports: dict) -> str:
    live = _live(findings, reports)
    if any(f["severity"] == "high" for f in live):
        return "fail"
    return "conditional" if live else "pass"
