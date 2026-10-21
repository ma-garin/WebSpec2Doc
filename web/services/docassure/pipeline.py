"""決定論の分析を段階ごとに実行し、ステージ単位で失敗を隔離する。LLM は使わない（DEGRADED でも同じ結果）。"""
from __future__ import annotations

import hashlib
import time
from typing import Callable

from web.services.docassure import decisions as decisions_mod
from web.services.docassure import model as M

_EXTRACT_CACHE: dict[tuple, tuple] = {}   # (文書ID, 本文 hash) -> 要件単位。未変更文書は再解析しない
_CACHE_MAX = 256


def _extract_cached(requirement_engine, doc_id: str, text: str, text_hash: str, stats: dict) -> list:
    key = (doc_id, text_hash)
    hit = _EXTRACT_CACHE.get(key)
    if hit is not None:
        stats["cache_hits"] += 1
        return list(hit)
    units = requirement_engine.extract(doc_id, text)
    if len(_EXTRACT_CACHE) >= _CACHE_MAX:
        _EXTRACT_CACHE.pop(next(iter(_EXTRACT_CACHE)))
    _EXTRACT_CACHE[key] = tuple(units)
    stats["cache_misses"] += 1
    return units


STAGES = ("structuring", "rules", "quality", "conflicts", "trace", "analyzers", "readiness")


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
            policy: dict | None = None, decisions: list[dict] | None = None,
            design_tests: list[dict] | None = None, execution: dict | None = None) -> dict:
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
    stats = {"cache_hits": 0, "cache_misses": 0}

    def structure():
        for d in docs:
            units_by_doc[d["id"]] = _extract_cached(requirement_engine, d["id"], d["text"], d["hash"], stats)
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
            tests[f"{u.document_id}:{u.requirement_id}"] = testability.assess(u)
        scores.update(quality.score_document(all_units, findings))
    _, timings["quality"] = _stage("quality", run_quality, errors, None)

    conflicts: list = []
    _, timings["conflicts"] = _stage("conflicts", lambda: conflicts.extend(conflict.detect(units_by_doc)), errors, None)

    if decisions:
        fl, cl = decisions_mod.apply([_d(f) for f in findings], conflicts, decisions)
        findings[:] = fl
        conflicts[:] = cl
    trace: dict = {}

    def run_trace():
        from web.services.docassure import coverage, trace_graph
        g = trace_graph.build(units_by_doc, design_tests)
        trace.update({"graph": g, "coverage": coverage.compute(g, execution)})
    _, timings["trace"] = _stage("trace", run_trace, errors, None)

    analyzers: dict = {"state": [], "decision_tables": [], "crud": [], "nfr": [], "completeness": [], "boundary": [], "glossary": {}}

    def run_analyzers():
        from web.services.docassure import boundary, completeness, crud_matrix, decision_table, glossary, nfr, state_transition
        analyzers["completeness"] = completeness.check(all_units)
        analyzers["boundary"] = [{**boundary.derive(u), "requirement_id": u.requirement_id, "document_id": u.document_id}
                                 for u in all_units]
        analyzers["glossary"] = glossary.build(units_by_doc)
        for d in docs:
            st = state_transition.extract(d["text"], d["id"])
            analyzers["state"].append({"document_id": d["id"], "model": st, "issues": state_transition.analyze(st)})
            analyzers["decision_tables"].extend(decision_table.extract(d["text"], d["id"]))
            analyzers["crud"].append({"document_id": d["id"], **crud_matrix.build(d["text"], d["id"])})
            analyzers["nfr"].extend(nfr.classify(d["text"], d["id"]))
    _, timings["analyzers"] = _stage("analyzers", run_analyzers, errors, None)

    def run_derived_scores():
        """矛盾・追跡から得られる次元。比較できていない・つながりを測れていない場合は value=None のまま。"""
        n = len(all_units)
        failed = {e["stage"] for e in errors}
        if n and "conflicts" not in failed and len(docs) >= 2 and scores.get("Consistency") is not None:
            unresolved = decisions_mod.unresolved(conflicts)
            scores["Consistency"] = M.Score(
                "Consistency", max(0.0, 100.0 - 20.0 * len(unresolved)), 1.0,
                (f"未解決の矛盾候補 {len(unresolved)} 件（1 件ごとに 20 点減点）",),
                ("文書間・文書内の数値/権限/時系列の矛盾候補",), ())
        elif "Consistency" in scores and scores["Consistency"].value is None:
            why = "文書が 1 本のため文書間の比較をしていない" if len(docs) < 2 else "矛盾検出の段階が失敗した"
            scores["Consistency"] = M.Score("Consistency", None, 0.0, (), (), (why,))
        t = trace.get("graph") or {}
        reqs = [x["id"] for x in t.get("nodes", []) if x.get("type") == "Requirement"]
        if reqs and len(docs) >= 2 and "trace" not in failed and "Traceability" in scores:
            lk = {"references": 1.0, "mentions": 1.0, "verifies": 1.0, "relates": 0.5}
            best: dict[str, float] = {}
            for e in t.get("edges", []):
                w = lk.get(e["kind"])
                if w is None:
                    continue   # contains（文書・節に含まれる）は設計とのつながりではない
                for end in (e["src"], e["dst"]):
                    if end in reqs:
                        best[end] = max(best.get(end, 0.0), w)
            ratio = sum(best.values()) / len(reqs)
            trace["linked_ratio"] = round(ratio, 3)
            scores["Traceability"] = M.Score(
                "Traceability", round(100.0 * ratio, 1), 1.0,
                (f"設計・参照とのつながりが無い要件 {len(reqs) - len(best)} / {len(reqs)} 件（推論リンクは 0.5 として数える）",),
                ("要件→設計・画面・API・テストの明示/推論リンク",), (("テスト実行結果を反映済み（System02）",) if execution else ("テスト実行 Evidence は未取込",)))
    _, timings["derived"] = _stage("derived", run_derived_scores, errors, None)

    gate, timings["readiness"] = _stage("readiness", lambda: readiness.gate(scores, [_d(f) for f in findings],
                                                                          conflicts, {"trace_coverage": trace.get("linked_ratio"), **(policy or {})}), errors,
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
        "trace": trace,
        "analyzers": analyzers,
        "mode": "DETERMINISTIC_ONLY",
        "errors": errors,
        "timings": timings,
        "metrics": {**stats, "rules": len(results), "stages_failed": [e["stage"] for e in errors],
                    "duration_sec": round(sum(timings.values()), 3)},   # 本文・秘密は含めない
        "counts": {"documents": len(docs), "requirements": len(all_units), "findings": len(findings),
                   "conflicts": len(conflicts)},
    }


def rejudge(result: dict, decisions: list[dict], policy: dict | None = None) -> dict:
    """保存済みの分析結果へ人の判断だけを適用し直す（再分析しない）。

    組織ポリシー・System02 の結果など分析時の入力はそのまま残る。判断の対象以外の指摘は変えない。
    """
    from web.services.docassure import readiness
    fs, cs = decisions_mod.apply(list(result.get("findings") or []), list(result.get("conflicts") or []), decisions)
    scores = dict(result.get("scores") or {})
    cons = scores.get("Consistency")
    if cons and cons.get("value") is not None and len(result.get("documents") or []) >= 2:
        open_cf = decisions_mod.unresolved(cs)
        scores["Consistency"] = {**cons, "value": max(0.0, 100.0 - 20.0 * len(open_cf)),
                                 "explanation": [f"未解決の矛盾候補 {len(open_cf)} 件（1 件ごとに 20 点減点）"]}
    trace = result.get("trace") or {}
    gate = readiness.gate(scores, fs, cs, {"trace_coverage": trace.get("linked_ratio"), **(policy or {})})
    if result.get("errors"):
        gate = {**gate, "state": gate["state"] if gate["state"] in (M.DRAFT, "BLOCKED") else M.DRAFT}
    return {**result, "findings": fs, "conflicts": cs, "scores": scores, "readiness": gate}
