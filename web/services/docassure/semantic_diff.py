"""意味指紋ベースの差分。位置だけの変更は MOVED（要件変更にしない）。LLM は使わない。"""
from __future__ import annotations

from web.services.docassure.trace_graph import dice, _g, _loc
from web.services.docassure.units import normalize_quantity

SPLIT_MERGE_MIN = 0.55


def _auto(rid: str) -> bool:
    return rid.startswith("RU-")


def _ref(u) -> dict:
    return {"requirement_id": _g(u, "requirement_id"), "document_id": _g(u, "document_id"),
            "section": _loc(u, "section"), "text": _g(u, "raw_text")}


def _topic(u) -> str:
    f = _g(u, "fields", {}) or {}
    for k in ("object", "action"):
        v = f.get(k)
        v = getattr(v, "value", v.get("value") if isinstance(v, dict) else v) if v else ""
        if v:
            return v
    return _g(u, "raw_text")[:20]


def _qty(text: str) -> list[tuple]:
    return [(q["unit_kind"], q["canonical_value"], q["raw"]) for q in normalize_quantity(text)]


def _threshold(b, a):
    qb, qa = _qty(_g(b, "raw_text")), _qty(_g(a, "raw_text"))
    if not qb or len(qb) != len(qa):
        return None
    for (kb, vb, rb), (ka, va, ra) in zip(qb, qa):
        if kb == ka and vb != va:
            ratio = max(vb, va) / min(vb, va) if min(vb, va) else float("inf")
            return rb, ra, ("high" if ratio >= 2 else "medium")
    return None


def _impacted(after_units, target) -> list[str]:
    rid, text, out = _g(target, "requirement_id"), _g(target, "raw_text"), []
    for u in after_units:
        o = _g(u, "requirement_id")
        if o == rid:
            continue
        if rid in _g(u, "raw_text") or dice(text, _g(u, "raw_text")) >= 0.3:
            out.append(o)
    return out


def diff(before_units: list, after_units: list) -> list[dict]:
    B, A = list(before_units), list(after_units)
    pairs: list[tuple] = []          # (b, a, how)
    ub, ua = set(range(len(B))), set(range(len(A)))
    # 1) 指紋一致（同 ID を優先）
    for pref_same_id in (True, False):
        for i in sorted(ub):
            for j in sorted(ua):
                fb, fa = _g(B[i], "fingerprint"), _g(A[j], "fingerprint")
                if fb and fb == fa and (not pref_same_id or _g(B[i], "requirement_id") == _g(A[j], "requirement_id")):
                    pairs.append((B[i], A[j], "fp"))
                    ub.discard(i); ua.discard(j)
                    break
    # 2) 明示 ID 一致 → 内容が変わった
    for i in sorted(ub):
        rid = _g(B[i], "requirement_id")
        if _auto(rid):
            continue
        for j in sorted(ua):
            if _g(A[j], "requirement_id") == rid:
                pairs.append((B[i], A[j], "id")); ub.discard(i); ua.discard(j); break
    # 3) 自動採番は語の重なりで対応づけ
    for i in sorted(ub):
        best = max(((dice(_g(B[i], "raw_text"), _g(A[j], "raw_text")), j) for j in ua), default=(0, -1))
        if best[0] >= 0.6 and _auto(_g(B[i], "requirement_id")):
            pairs.append((B[i], A[best[1]], "sim")); ub.discard(i); ua.discard(best[1])

    out: list[dict] = []
    # 順序比較: 対応済み要件の文書内相対順
    rank_b = {id(b): k for k, b in enumerate(sorted((p[0] for p in pairs), key=B.index))}
    rank_a = {id(a): k for k, a in enumerate(sorted((p[1] for p in pairs), key=A.index))}
    for b, a, how in pairs:
        same_fp = _g(b, "fingerprint") and _g(b, "fingerprint") == _g(a, "fingerprint")
        base = {"requirement_id": _g(a, "requirement_id"), "before": _ref(b), "after": _ref(a)}
        if same_fp:
            moved = ((_g(b, "document_id"), _loc(b, "section")) != (_g(a, "document_id"), _loc(a, "section"))
                     or rank_b[id(b)] != rank_a[id(a)] or _g(b, "requirement_id") != _g(a, "requirement_id"))
            if moved:
                out.append({**base, "change": "MOVED", "note": "位置・順序・採番のみの変更。要件内容は同じ"})
            continue
        item = {**base, "change": "MODIFIED"}
        th = _threshold(b, a)
        if th:
            item.update({"change_type": "threshold_change", "topic": _topic(a), "before_value": th[0],
                         "after_value": th[1], "risk": th[2], "impacted_requirements": _impacted(A, a)})
            item["before_topic_value"], item["after_topic_value"] = th[0], th[1]
        out.append(item)
    rem_b, rem_a = [B[i] for i in sorted(ub)], [A[j] for j in sorted(ua)]
    used_b, used_a = set(), set()
    for b in rem_b:   # SPLIT
        parts = [a for a in rem_a if id(a) not in used_a and (
            _g(a, "parent_id") == _g(b, "requirement_id") or _cover(a, b) >= SPLIT_MERGE_MIN)]
        if len(parts) >= 2:
            out.append({"change": "SPLIT", "requirement_id": _g(b, "requirement_id"), "before": _ref(b),
                        "after_ids": [_g(a, "requirement_id") for a in parts]})
            used_b.add(id(b)); used_a |= {id(a) for a in parts}
    for a in rem_a:   # MERGED
        if id(a) in used_a:
            continue
        parts = [b for b in rem_b if id(b) not in used_b and _cover(b, a) >= SPLIT_MERGE_MIN]
        if len(parts) >= 2:
            out.append({"change": "MERGED", "requirement_id": _g(a, "requirement_id"), "after": _ref(a),
                        "before_ids": [_g(b, "requirement_id") for b in parts]})
            used_a.add(id(a)); used_b |= {id(b) for b in parts}
    for b in rem_b:
        if id(b) not in used_b:
            out.append({"change": "REMOVED", "requirement_id": _g(b, "requirement_id"), "before": _ref(b)})
    for a in rem_a:
        if id(a) not in used_a:
            out.append({"change": "CREATED", "requirement_id": _g(a, "requirement_id"), "after": _ref(a)})
    return out


def _cover(small, big) -> float:
    """small の語が big にどれだけ含まれるか（部分集合度）。"""
    from web.services.docassure.trace_graph import _grams
    s, b = _grams(_g(small, "raw_text")), _grams(_g(big, "raw_text"))
    return len(s & b) / len(s) if s else 0.0
