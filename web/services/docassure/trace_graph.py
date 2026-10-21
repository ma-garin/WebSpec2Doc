"""文書・要件・設計・テスト・証跡のトレースグラフ。LLM は使わない。

真実規律: edge は必ず出所を持つ。明示 ID 参照＝EXPLICIT、語の重なり＝INFERRED（confidence 付き）。
孤立は欠陥と断定せず CANDIDATE。リンクが無い≠無いと証明、ではなく「見つからなかった」を表す。
"""
from __future__ import annotations

import re
import unicodedata

EXPLICIT, OBSERVED, DERIVED, INFERRED = "EXPLICIT", "OBSERVED", "DERIVED", "INFERRED"
PROVENANCES = (EXPLICIT, OBSERVED, DERIVED, INFERRED)
INFER_MIN = 0.35   # INFERRED リンクを張る語の重なり下限（dice）

_ID_STRICT = re.compile(r"\b[A-Z]{2,4}-\d{1,5}\b|\bRU-[A-Za-z0-9_]+-\d+\b")
_SCREEN = re.compile(r"([^\s、。,.（）()「」はがをにでのともやへ]{1,12}?画面)")  # 助詞・動詞を含む断片を画面名にしない
_API = re.compile(r"\b(?:GET|POST|PUT|DELETE|PATCH)\s+(/[\w/{}\-.:]*)|(?<![\w/])(/api/[\w/{}\-.:]*)")


def _g(u, key, default=""):
    if isinstance(u, dict):
        return u.get(key, default)
    return getattr(u, key, default)


def _loc(u, key, default=""):
    loc = _g(u, "location", None)
    if loc is None:
        return default
    return loc.get(key, default) if isinstance(loc, dict) else getattr(loc, key, default)


def _grams(s: str) -> set[str]:
    t = unicodedata.normalize("NFKC", _ID_STRICT.sub("", s)).lower()
    t = "".join(c for c in t if unicodedata.category(c)[0] not in "ZPSC")
    return {t[i:i + 2] for i in range(len(t) - 1)}


def dice(a: str, b: str) -> float:
    x, y = _grams(a), _grams(b)
    return 2 * len(x & y) / (len(x) + len(y)) if x and y else 0.0


def _ids_in(text: str) -> set[str]:
    return set(_ID_STRICT.findall(unicodedata.normalize("NFKC", text)))


class _G:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self._seen: set[tuple] = set()

    def node(self, nid, typ, label, doc=""):
        self.nodes.setdefault(nid, {"id": nid, "type": typ, "label": label[:80], "document_id": doc})

    def edge(self, src, dst, kind, prov, conf, basis):
        k = (src, dst, kind)
        if k in self._seen or src == dst:
            return
        self._seen.add(k)
        self.edges.append({"src": src, "dst": dst, "kind": kind, "provenance": prov,
                           "confidence": round(conf, 2), "basis": basis})


def _req_type(u) -> str:
    return "BusinessRule" if _g(u, "kind") in ("business_rule",) else "Requirement"


def build(docs_units: dict[str, list], tests: list[dict] | None = None,
          evidence: list[dict] | None = None) -> dict:
    g = _G()
    reqs: dict[str, tuple[str, object]] = {}   # requirement_id -> (node id, unit)
    for doc, units in docs_units.items():
        did = f"DOC:{doc}"
        g.node(did, "Document", doc, doc)
        for u in units:
            rid = _g(u, "requirement_id")
            nid = f"REQ:{rid}"
            reqs[rid] = (nid, u)
            g.node(nid, _req_type(u), _g(u, "raw_text") or rid, doc)
            sec = _loc(u, "section")
            if sec:
                sid = f"SEC:{doc}:{sec}"
                g.node(sid, "Section", sec, doc)
                g.edge(did, sid, "contains", OBSERVED, 1.0, "見出し構造")
                g.edge(sid, nid, "contains", OBSERVED, 1.0, "節内の記述")
            else:
                g.edge(did, nid, "contains", OBSERVED, 1.0, "文書内の記述")
            text = _g(u, "raw_text")
            for m in _SCREEN.finditer(text):
                s = m.group(1)
                g.node(f"SCR:{s}", "Screen", s, doc)
                g.edge(nid, f"SCR:{s}", "mentions", OBSERVED, 1.0, f"原文に「{s}」")
            for m in _API.finditer(text):
                p = m.group(1) or m.group(2)
                g.node(f"API:{p}", "API", p, doc)
                g.edge(nid, f"API:{p}", "mentions", OBSERVED, 1.0, f"原文に {p}")
    # 要件 → 要件: 明示 ID 参照 (EXPLICIT)、別文書の語の重なり (INFERRED)
    items = list(reqs.items())
    for rid, (nid, u) in items:
        for ref in _ids_in(_g(u, "raw_text")):
            if ref != rid and ref in reqs:
                g.edge(nid, reqs[ref][0], "references", EXPLICIT, 1.0, f"原文に ID {ref}")
    for i, (ra, (na, ua)) in enumerate(items):
        for rb, (nb, ub) in items[i + 1:]:
            if _g(ua, "document_id") == _g(ub, "document_id"):
                continue
            if (na, nb, "references") in g._seen or (nb, na, "references") in g._seen:
                continue
            d = dice(_g(ua, "raw_text"), _g(ub, "raw_text"))
            if d >= INFER_MIN:
                g.edge(na, nb, "relates", INFERRED, d, f"語の重なり dice={d:.2f}（推測。明示リンクではない）")
    # テスト
    test_ids = []
    for t in tests or []:
        tid_raw = str(t.get("test_id") or t.get("id") or "")
        if not tid_raw:
            continue
        tid = f"TEST:{tid_raw}"
        test_ids.append(tid)
        text = " ".join(str(t.get(k, "")) for k in ("title", "text", "steps"))
        g.node(tid, "Test", t.get("title") or tid_raw, "")
        explicit = set(t.get("requirement_ids") or []) | _ids_in(text)
        hit = False
        for rid in explicit:
            if rid in reqs:
                g.edge(tid, reqs[rid][0], "verifies", EXPLICIT, 1.0, f"テストに要件 ID {rid}")
                hit = True
        if not hit:
            for rid, (nid, u) in items:
                d = dice(text, _g(u, "raw_text"))
                if d >= INFER_MIN:
                    g.edge(tid, nid, "verifies", INFERRED, d, f"語の重なり dice={d:.2f}（推測。明示リンクではない）")
        for m in _API.finditer(text):
            p = m.group(1) or m.group(2)
            g.node(f"API:{p}", "API", p, "")
            g.edge(tid, f"API:{p}", "exercises", OBSERVED, 1.0, f"テストに {p}")
    for e in evidence or []:
        eid = str(e.get("evidence_id") or e.get("id") or "")
        if not eid:
            continue
        nid = f"EVD:{eid}"
        g.node(nid, "Evidence", e.get("label") or eid, "")
        tid = f"TEST:{e.get('test_id')}" if e.get("test_id") else ""
        if tid in g.nodes:
            g.edge(nid, tid, "evidences", EXPLICIT, 1.0, "証跡に test_id")
    return {"nodes": list(g.nodes.values()), "edges": g.edges, "orphans": _orphans(g)}


def _orphans(g: _G) -> list[dict]:
    typ = {n["id"]: n["type"] for n in g.nodes.values()}
    touch: dict[str, list[dict]] = {}
    for e in g.edges:
        touch.setdefault(e["src"], []).append(e)
        touch.setdefault(e["dst"], []).append(e)
    out = []

    def add(nid, kind, reason):
        out.append({"node_id": nid, "kind": kind, "status": "CANDIDATE", "reason": reason})

    for nid, t in typ.items():
        es = touch.get(nid, [])
        if t in ("Requirement", "BusinessRule"):
            if not any(typ[e["dst"] if e["src"] == nid else e["src"]] in ("Screen", "API")
                       for e in es if e["kind"] == "mentions"):
                add(nid, "requirement_without_design", "画面・API への言及が見つからない（設計が無いと断定はしない）")
            if not any(e["kind"] == "verifies" and e["dst"] == nid for e in es):
                add(nid, "requirement_without_test", "紐づくテストが見つからない（テスト未作成と断定はしない）")
        elif t == "API":
            if not any(e["kind"] == "mentions" for e in es):
                add(nid, "api_without_requirement", "この API に言及する要件が見つからない")
        elif t == "Test":
            if not any(e["kind"] == "verifies" for e in es if e["src"] == nid):
                add(nid, "test_without_requirement", "このテストが検証する要件が見つからない")
    return out


def neighborhood(graph: dict, node_id: str, depth: int = 2) -> dict:
    seen, frontier = {node_id}, {node_id}
    for _ in range(max(depth, 0)):
        nxt = set()
        for e in graph["edges"]:
            if e["src"] in frontier and e["dst"] not in seen:
                nxt.add(e["dst"])
            if e["dst"] in frontier and e["src"] not in seen:
                nxt.add(e["src"])
        seen |= nxt
        frontier = nxt
    return {"nodes": [n for n in graph["nodes"] if n["id"] in seen],
            "edges": [e for e in graph["edges"] if e["src"] in seen and e["dst"] in seen]}


def filter_by_provenance(graph: dict, provenances) -> dict:
    keep = {provenances} if isinstance(provenances, str) else set(provenances)
    return {**graph, "edges": [e for e in graph["edges"] if e["provenance"] in keep]}
