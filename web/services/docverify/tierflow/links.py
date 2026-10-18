"""文書のつながり（ノードと線）と結論の自動判定。"""
from __future__ import annotations

import re

from . import tiers

LEVEL_LABEL = {"pass": "合格", "conditional": "条件付き", "fail": "不合格"}
_EDGE_TYPE = {"CONFLICT": "conflict", "REVERSE_REF": "reverse_ref", "DUPLICATE": "duplicate"}


ID_RE = re.compile(r"(?<![A-Za-z0-9-])[A-Z]{2,5}-\d{1,4}(?!\d)")
SINGLE_DOC_NOTE = "文書が 1 件だけです。つながりを確かめるには 2 件以上の文書が必要です。"


def _is_heading(text: str, first_id: str) -> bool:
    """行がその ID を定義する見出しか。Markdown の「#」見出し、または行頭が ID で句点で終わらない 80 字以内の行。"""
    t = text.strip()
    if t.startswith("#"):
        return t.lstrip("#").strip().startswith(first_id)
    return t.startswith(first_id) and len(t) <= 80 and not t.endswith(("。", "."))


def ids(documents: list[dict]) -> dict[str, dict]:
    """文書ごとの定義 ID（見出し行に出る ID）と参照 ID（それ以外の本文に出る ID）。

    戻り値: {文書id: {"defined": {ID: passage}, "refs": {ID: [passage, ...]}}}（出現順を保つ）
    """
    out: dict[str, dict] = {}
    for d in documents:
        defined: dict[str, dict] = {}
        refs: dict[str, list[dict]] = {}
        for p in d.get("passages") or []:
            text = p.get("text") or ""
            found = ID_RE.findall(text)
            # 見出し行の先頭の ID だけを定義とみなす。Word 等は「#」が無いので、
            # 行頭が ID で始まり文で終わらない短い行（例「REQ-001 会員登録」）も見出しとして扱う
            own = found[0] if found and _is_heading(text, found[0]) else None
            for m in found:
                if m == own:
                    defined.setdefault(m, p)
                else:
                    refs.setdefault(m, []).append(p)
        out[d["id"]] = {"defined": defined, "refs": {k: v for k, v in refs.items() if k not in defined}}
    return out


def definers(table: dict[str, dict]) -> dict[str, list[str]]:
    """ID → それを定義した文書 id の一覧。"""
    out: dict[str, list[str]] = {}
    for doc_id, t in table.items():
        for i in t["defined"]:
            out.setdefault(i, []).append(doc_id)
    return out


def _traces(documents: list[dict]) -> list[dict]:
    table = ids(documents)
    owner = definers(table)
    grouped: dict[tuple, list[str]] = {}
    for d in documents:
        for i in table[d["id"]]["refs"]:
            for to in owner.get(i, []):
                if to != d["id"]:
                    grouped.setdefault((d["id"], to), []).append(i)
    return [{"from": a, "to": b, "type": "traces", "finding_ids": [], "ids": found,
             "reason": f"{'、'.join(found)} を参照"} for (a, b), found in grouped.items()]


def note(documents: list[dict]) -> str | None:
    """結論に添える注記。合否は変えない。"""
    return SINGLE_DOC_NOTE if len(documents) == 1 else None


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
        k = d.get("kind") or tiers.kind(d.get("name") or "", d.get("passages") or [])[0]
        out.append({"id": d["id"], "name": d["name"], "tier": d["tier"], "kind": k, "kind_label": tiers.KIND_LABEL[k],
                    "status": _status(mine), "issues": len(mine)})
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
    return {"nodes": _nodes(documents, live),
            "edges": _follows(documents) + _traces(documents) + _problem_edges(documents, live),
            "note": note(documents)}


def conclude(findings: list[dict], reports: dict) -> str:
    live = _live(findings, reports)
    if any(f["severity"] == "high" for f in live):
        return "fail"
    return "conditional" if live else "pass"
