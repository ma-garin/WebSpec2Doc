"""影響の候補を集める（DD-004 candidates.py）。①つながり（BFS）②意味の近さ ③語の一致。"""
from __future__ import annotations

import math
import re
from collections import deque

from .text import expand, norm, tokens

SEMANTIC_TOP = 30
SEMANTIC_MIN = 0.25
_CODE = re.compile(r"\b[A-Z]{2,5}-\d{3,4}\b")


def load_items(conn, sid: str) -> list[dict]:
    rows = conn.execute(
        "SELECT i.id, i.code, i.text, i.location, i.section, i.ord, i.document_id,"
        " d.name AS document_name, d.kind AS doc_kind"
        " FROM items i JOIN documents d ON d.id = i.document_id WHERE i.system_id = ? ORDER BY d.name, i.ord",
        (sid,)).fetchall()
    return [dict(r) for r in rows]


def load_adjacency(conn, sid: str) -> dict[str, set]:
    adj: dict[str, set] = {}
    for a, b in conn.execute("SELECT a_item, b_item FROM links WHERE system_id = ?", (sid,)).fetchall():
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


def seeds_for(change: dict, items: list[dict]) -> list[dict]:
    """変更箇所の所在項目: 所在・本文に書かれた code、所在の一致、本文の一致。"""
    codes = set(_CODE.findall(" ".join([change.get("location", ""), change.get("before", ""), change.get("after", "")])))
    loc = norm(change.get("location"))
    texts = {norm(change.get("before")), norm(change.get("after"))} - {""}
    return [it for it in items
            if it["code"] in codes or (loc and loc == norm(it.get("location")) and loc != "変更の指示")
            or norm(it["text"]) in texts]


def bfs(start_ids: list[str], adj: dict[str, set], depth: int) -> dict[str, tuple[int, str]]:
    """起点から depth 段までの {item_id: (段数, 直前の item_id)}。起点は 0 段。"""
    seen = {s: (0, "") for s in start_ids}
    q = deque(start_ids)
    while q:
        cur = q.popleft()
        d = seen[cur][0]
        if d >= depth:
            continue
        for nxt in sorted(adj.get(cur, ())):
            if nxt not in seen:
                seen[nxt] = (d + 1, cur)
                q.append(nxt)
    return seen


def make_query(change: dict) -> dict | None:
    """主題の語（変わっていない語）と差分の語（変わった語と言い換え）。"""
    before, after = tokens(change.get("before")), tokens(change.get("after"))
    diff = list(dict.fromkeys([t for t in after if t not in before] + [t for t in before if t not in after]))
    subject = [t for t in dict.fromkeys(after + before) if t not in diff]
    subject.sort(key=lambda t: -len(t))
    if not subject:
        subject, diff = diff[:2], diff[2:]
    subject = subject[:3]
    if not subject:
        return None
    ex = expand(diff)[:10]
    return {"subject": subject, "diff": ex, "terms": subject + ex, "must": subject}


def keyword_hits(change: dict, items: list[dict], texts: list[str]) -> list[tuple[int, list, list, float]]:
    q = make_query(change)
    if q is None:
        return []
    n = max(len(items), 1)
    df = {t: sum(1 for x in texts if t in x) for t in q["terms"]}
    out = []
    for i, text in enumerate(texts):
        if not any(m in text for m in q["must"]):
            continue
        matched = [t for t in q["terms"] if t in text]
        diff_hit = [t for t in q["diff"] if t in text]
        score = sum(math.log(1 + n / (1 + df[t])) for t in matched)
        out.append((i, matched, diff_hit, round(score, 2)))
    return out


def _add(merged: dict, item: dict, change_code: str, depth: int, ev: dict) -> None:
    c = merged.setdefault(item["id"], {"item": item, "change_ids": [], "depth": depth, "evidence": []})
    if change_code not in c["change_ids"]:
        c["change_ids"].append(change_code)
    c["depth"] = min(c["depth"], depth)
    if ev not in c["evidence"]:
        c["evidence"].append(ev)


def collect(conn, cr: dict, changes: list[dict], depth: int, embedder) -> list[dict]:
    """cand = {item, change_ids, depth, evidence:[{type, detail, score}]}。同一項目は統合する。"""
    sid = cr["system_id"]
    items = load_items(conn, sid)
    if not items or not changes:
        return []
    by_id = {it["id"]: it for it in items}
    adj = load_adjacency(conn, sid)
    texts = [re.sub(r"\s+", "", norm(it["text"])) for it in items]
    vectors = embedder.vectors([it["text"] for it in items]) if embedder is not None else []
    merged: dict[str, dict] = {}
    for ch in changes:
        code = ch["code"]
        seeds = seeds_for(ch, items)
        for iid, (d, prev) in bfs([s["id"] for s in seeds], adj, max(int(depth or 0), 0)).items():
            if d == 0:
                ev = {"type": "link", "detail": "変更箇所そのもの", "score": 1.0}
            else:
                ev = {"type": "link", "detail": f"{by_id[prev]['code']} から {d} 段目のつながり", "score": round(1 / (d + 1), 2)}
            _add(merged, by_id[iid], code, d, ev)
        if vectors:
            query = " ".join(x for x in (ch.get("before"), ch.get("after")) if x)
            for idx, score in embedder.similar(query, vectors, SEMANTIC_TOP):
                if score >= SEMANTIC_MIN:
                    kind = "埋め込み" if embedder.mode == "embedding" else "文字"
                    _add(merged, items[idx], code, 1,
                         {"type": "semantic", "detail": f"{kind}の近さ {score:.2f}", "score": score})
        for idx, matched, diff_hit, score in keyword_hits(ch, items, texts):
            detail = "一致語: " + "・".join(matched[:4])
            if diff_hit:
                detail += "（差分語: " + "・".join(diff_hit[:3]) + "）"
            _add(merged, items[idx], code, 1, {"type": "keyword", "detail": detail, "score": score})
    out = list(merged.values())
    for c in out:
        c["change_ids"].sort(key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)
    out.sort(key=lambda c: (c["depth"], -max(e["score"] for e in c["evidence"]), c["item"]["code"]))
    return out
