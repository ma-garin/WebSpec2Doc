"""版の差分: 断片を本文の正規化一致で対応付ける。"""
from __future__ import annotations

import difflib
import re
import unicodedata


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or "")).lower()


def _brief(p: dict) -> dict:
    return {"id": p.get("id"), "text": p.get("text"), "location": p.get("location")}


def compare(old_passages: list[dict], new_passages: list[dict]) -> dict:
    old_keys = {_norm(p["text"]) for p in old_passages}
    new_keys = {_norm(p["text"]) for p in new_passages}
    removed = [p for p in old_passages if _norm(p["text"]) not in new_keys]
    added = [p for p in new_passages if _norm(p["text"]) not in old_keys]
    changed, used = [], set()
    for o in removed:
        best, score = None, 0.6
        for i, n in enumerate(added):
            if i in used:
                continue
            r = difflib.SequenceMatcher(None, _norm(o["text"]), _norm(n["text"])).ratio()
            if r > score:
                best, score = i, r
        if best is not None:
            used.add(best)
            changed.append({"old": _brief(o), "new": _brief(added[best])})
    paired_old = {id(c_old) for c_old in removed if any(c["old"]["id"] == c_old.get("id") for c in changed)}
    return {
        "added": [_brief(n) for i, n in enumerate(added) if i not in used],
        "removed": [_brief(o) for o in removed if id(o) not in paired_old],
        "changed": changed,
    }


def carry_findings(old_findings: list[dict], old_passages: list[dict], new_passages: list[dict]) -> list[dict]:
    """旧指摘を新しい版へ引き継ぐ。消えた断片の採用済み指摘は fixed にする。"""
    new_by_key = {_norm(p["text"]): p for p in new_passages}
    old_by_id = {p["id"]: p for p in old_passages}
    out = []
    for f in old_findings:
        g = dict(f)
        op = old_by_id.get(f.get("passage_id"))
        np_ = new_by_key.get(_norm(op["text"])) if op else None
        if np_ is not None:
            g["passage_id"] = np_["id"]
            g["location"] = np_.get("location", g.get("location"))
        elif op is not None and f.get("status") == "adopted":
            g["status"] = "fixed"
        out.append(g)
    return out
