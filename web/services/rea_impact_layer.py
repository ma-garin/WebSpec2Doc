"""影響度分析（System 09）に System 01 のリバース解析（REA）の module 依存を別の Evidence 層として流す。

既存の文書項目 BFS（web/services/impact/）は置換しない。ここは layer="code_static" の別結果を返す純関数だけを持つ。
状態（inferred / ambiguous / unknown）は提供元の値をそのまま通し、上げない。依存は静的で実行時の依存ではない。
"""
from __future__ import annotations

import re
from collections import deque
from pathlib import Path
from typing import Any

LAYER = "code_static"
NOTICE = "静的依存（実行時の依存ではない）"
TESTS_NOTE = "System 02 のリバース解析由来のテスト観点（静的候補由来。到達・実行は未確認）。該当が無ければ 0 件"
BEFORE_REASON = ("既存の影響分析は文書・項目・変更要求が単位で、サイト（コード依存）の概念が無いため、"
                 "このサイトに対する依存 edge・影響候補は 0 件です。")  # fmt: skip
UNCONFIRMED = "未確認（結果なし）"
_LOC = re.compile(r":\d+(?::\d+)?$")
MAX_DEPTH = 8


def norm_module(name: Any) -> str:
    """'./chunk-A.js' や 'a/b/chunk-A.js?x' を 'chunk-A.js' に揃える（file 名で突き合わせる）。"""
    s = str(name or "").split("?", 1)[0].strip().replace("\\", "/")
    return s.rsplit("/", 1)[-1]


def loc_file(location: Any) -> str:
    s = str(location or "")
    if not s or s.startswith("実行記録"):
        return ""
    return norm_module(_LOC.sub("", s))


def _empty(site: str, module: str, message: str, state: str = "unconfirmed") -> dict:
    zero = {"dependency_edges": 0, "candidates": 0, "routes": 0, "apis": 0, "tests": 0}
    return {"layer": LAYER, "site": site, "state": state, "module": module, "notice": NOTICE,
            "message": message, "impacted": [], "external": [], "sources": [],
            "metrics": {"before": {**zero, "reason": BEFORE_REASON}, "after": dict(zero)},
            "tests": {"count": 0, "note": TESTS_NOTE}}  # fmt: skip


def _edge(d: dict) -> dict:
    return {"source": norm_module(d.get("source")), "target": norm_module(d.get("target")),
            "raw_target": str(d.get("target") or ""), "relation_label": d.get("relation_label") or "",
            "state": d.get("state") or "unknown", "location": d.get("location"),
            "external": bool(d.get("external")), "limitations": list(d.get("limitations") or []),
            "kind": "static_dependency"}  # fmt: skip


def _graph(deps: list) -> tuple[list[dict], dict, dict, list[dict]]:
    internal: list[dict] = []
    external: list[dict] = []
    for d in deps:
        if isinstance(d, dict):
            (external if d.get("external") else internal).append(_edge(d))
    fwd: dict[str, list[dict]] = {}
    rev: dict[str, list[dict]] = {}
    for e in internal:
        fwd.setdefault(e["source"], []).append(e)
        rev.setdefault(e["target"], []).append(e)
    return internal, fwd, rev, external


def _bfs(start: str, adj: dict, forward: bool) -> list[dict]:
    """start から辿れる module を幅優先で返す。forward=False は「start を import している側」を辿る。"""
    seen = {start}
    out: list[dict] = []
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    while queue:
        cur, depth = queue.popleft()
        if depth >= MAX_DEPTH:
            continue
        for e in adj.get(cur, []):
            nxt = e["target"] if forward else e["source"]
            if nxt in seen:
                continue
            seen.add(nxt)
            out.append({"module": nxt, "depth": depth + 1, "via": e,
                        "direction": "forward" if forward else "reverse"})  # fmt: skip
            queue.append((nxt, depth + 1))
    return out


def _related(evidence: list) -> dict[str, dict[str, list[dict]]]:
    """module(file) ごとの route / 静的 API。実測 API（runtime）は page 単位で file を持たないので関連付けない。"""
    by: dict[str, dict[str, list[dict]]] = {}
    for ev in evidence:
        if not isinstance(ev, dict) or ev.get("origin") != "static" or ev.get("group") not in ("route", "api"):
            continue
        f = loc_file(ev.get("location"))
        if not f:
            continue
        item = {"id": ev.get("id"), "value": ev.get("value"), "method": ev.get("method"),
                "state": ev.get("state") or "unknown", "origin": "static",
                "location": ev.get("location")}  # fmt: skip
        key = "routes" if ev.get("group") == "route" else "apis"
        by.setdefault(f, {"routes": [], "apis": []})[key].append(item)
    return by


def list_sources(deps: list) -> list[dict]:
    internal, fwd, rev, _ = _graph(deps)
    names = set(fwd) | set(rev)
    rows = [{"module": m, "imports": len(fwd.get(m, [])), "imported_by": len(rev.get(m, [])),
             "degree": len(fwd.get(m, [])) + len(rev.get(m, []))} for m in names]  # fmt: skip
    return sorted(rows, key=lambda r: (-r["degree"], r["module"]))


def build_layer(site: str, ev: dict, module: str = "") -> dict:
    """REA の site_evidence 結果から layer="code_static" の結果を作る。state != ok は 0 件・未確認。"""
    module = norm_module(module)
    if not isinstance(ev, dict) or ev.get("state") != "ok":
        msg = (ev or {}).get("message") if isinstance(ev, dict) else None
        return _empty(site, module, msg or "このサイトのリバース解析結果がありません。System 01 で実行すると依存関係が加わります。")
    deps = ev.get("dependencies") or []
    internal, fwd, rev, external = _graph(deps)
    sources = list_sources(deps)
    related = _related(ev.get("evidence") or [])
    vps = _viewpoints_by_evidence(ev)

    def tests_for(r: dict) -> list[dict]:
        return [vps[i["id"]] for i in r["routes"] + r["apis"] if i["id"] in vps]

    res = _empty(site, module, "", state="ok")
    res.update(sources=sources, message="")
    zero_before = res["metrics"]["before"]
    if not module:
        routes = {i["id"] for v in related.values() for i in v["routes"]}
        apis = {i["id"] for v in related.values() for i in v["apis"]}
        res["metrics"]["after"] = {"dependency_edges": len(internal) + len(external), "candidates": len(sources),
                                   "routes": len(routes), "apis": len(apis),
                                   "tests": len((routes | apis) & set(vps))}  # fmt: skip
        res["metrics"]["before"] = zero_before
        res["external_edges"] = len(external)
        return res
    if module not in set(fwd) | set(rev):
        res.update(state="unknown_module", message="この module は依存関係に現れません。")
        return res
    rev_c = _bfs(module, rev, forward=False)
    fwd_c = _bfs(module, fwd, forward=True)
    mods = [module] + [c["module"] for c in rev_c + fwd_c]
    for c in rev_c + fwd_c:
        r = related.get(c["module"], {"routes": [], "apis": []})
        c["routes"], c["apis"], c["tests"] = r["routes"], r["apis"], tests_for(r)
        c["note"] = NOTICE
    own = related.get(module, {"routes": [], "apis": []})
    res["own"] = {"module": module, "routes": own["routes"], "apis": own["apis"], "tests": tests_for(own)}
    res["impacted"] = rev_c + fwd_c
    res["external"] = [e for e in external if e["source"] in set(mods)]
    mod_set = set(mods)
    for c in rev_c + fwd_c:
        c["edges_n"] = sum(1 for e in internal if e["source"] == c["via"]["source"] and e["target"] == c["via"]["target"])
    seen_edges = {(e["source"], e["target"], e["location"], e["relation_label"]) for e in internal
                  if e["source"] in mod_set or e["target"] in mod_set}  # fmt: skip
    routes = {i["id"] for m in set(mods) for i in related.get(m, {}).get("routes", [])}
    apis = {i["id"] for m in set(mods) for i in related.get(m, {}).get("apis", [])}
    res["metrics"]["after"] = {"dependency_edges": len(seen_edges) + len(res["external"]),
                               "candidates": len(rev_c) + len(fwd_c), "routes": len(routes),
                               "apis": len(apis), "tests": len((routes | apis) & set(vps))}  # fmt: skip
    return res


def _viewpoints_by_evidence(ev: dict) -> dict[str, dict]:
    """System 02 の REA 由来テスト観点（新規分）を根拠 id で引けるようにする。"""
    from web.services.rea_test_viewpoints import build_viewpoints

    return {
        v["evidence_id"]: {"text": v.get("text"), "source": v.get("source"), "evidence_id": v["evidence_id"]}
        for v in build_viewpoints(ev).get("viewpoints", [])
        if v.get("is_new") and v.get("evidence_id")
    }


def sites_with_result(base: Path, valid, site_dir, result_dir: str, result_file: str) -> list[str]:
    """output 配下で REA 結果ファイルを持つサイト名の一覧。"""
    if not base.is_dir():
        return []
    out = []
    for p in sorted(base.iterdir()):
        if p.is_dir() and valid(p.name) and (site_dir(base, p.name) / result_dir / result_file).is_file():
            out.append(p.name)
    return out
