"""カバレッジ。要件・設計・テスト設計・実行・合格・検証済みを別々に出す。

テスト案が存在する≠実行済み。実行結果が無い項目は None（NOT_EVALUATED）で、0% にしない。
"""
from __future__ import annotations

_REQ = ("Requirement", "BusinessRule")
_PASS = {"PASS", "PASSED", "OK"}
_NOT_RUN = {"", "NOT_RUN", "NOT_EXECUTED", "SKIPPED", "NOT_EVALUATED", "PENDING"}


def _status(v) -> str:
    s = v.get("status") or v.get("result") or "" if isinstance(v, dict) else v
    return str(s or "").upper()


def _metric(n: int, total: int) -> dict:
    return {"count": n, "total": total, "ratio": round(n / total, 3) if total else None}


def compute(graph: dict, execution: dict | None = None) -> dict:
    typ = {n["id"]: n["type"] for n in graph["nodes"]}
    reqs = [i for i, t in typ.items() if t in _REQ]
    designed = {e["src"] for e in graph["edges"] if e["kind"] == "mentions" and typ.get(e["dst"]) in ("Screen", "API")}
    tests_of: dict[str, list[dict]] = {r: [] for r in reqs}
    for e in graph["edges"]:
        if e["kind"] == "verifies" and e["dst"] in tests_of:
            tests_of[e["dst"]].append(e)
    n = len(reqs)
    out = {
        "requirement": _metric(n, n),
        "design": _metric(sum(r in designed for r in reqs), n),
        "test_designed": _metric(sum(bool(tests_of[r]) for r in reqs), n),
        "test_designed_explicit": _metric(
            sum(any(e["provenance"] == "EXPLICIT" for e in tests_of[r]) for r in reqs), n),
        "execution": None, "passed": None, "verified": None,
        "status": {"execution": "NOT_EVALUATED", "passed": "NOT_EVALUATED", "verified": "NOT_EVALUATED"},
        "note": "テスト案があることは実行済みを意味しない。実行結果が無い項目は評価しない。",
    }
    if not execution:
        return out
    res = {(k[5:] if str(k).startswith("TEST:") else str(k)): _status(v) for k, v in execution.items()}

    def st(edge):
        return res.get(edge["src"][5:], "")

    executed = passed = verified = 0
    for r in reqs:
        es = tests_of[r]
        ran = [e for e in es if st(e) not in _NOT_RUN]
        if ran:
            executed += 1
        if ran and all(st(e) in _PASS for e in ran):
            passed += 1
            if len(ran) == len(es) and any(e["provenance"] == "EXPLICIT" for e in ran):
                verified += 1
    out["execution"], out["passed"], out["verified"] = (
        _metric(executed, n), _metric(passed, n), _metric(verified, n))
    out["status"] = {"execution": "EVALUATED", "passed": "EVALUATED", "verified": "EVALUATED"}
    return out
