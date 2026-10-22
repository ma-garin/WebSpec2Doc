"""System06 要件 ⇔ System02（テスト自動化）の往復。製品内サービス層で完結する。

push_candidates: テスト候補を System02 の tests.json へ設計案として登録する（candidate_id で冪等）。
pull_status: System02 の実データから要件ごとの状態を返す。実行結果が無ければ None（NOT_EVALUATED）。
真実規律: 生成≠実行済み、未評価≠PASS。テナント境界は docverify store と ta2_store が担う。
"""
from __future__ import annotations

from typing import Any

from web.services import ta2_store as _ta2
from web.services.docverify import perm as _perm
from web.services.docverify import store as _dv

_FAIL = {"fail", "flaky"}


def domain_of(iid: str) -> str:
    _dv.doc_dir(iid)  # iid の形式検証（不正なら例外）
    return f"docassure-{iid}"


def _check_inspection(iid: str) -> str:
    _dv.load(iid)  # 他テナント・不在は KeyError（テナント境界つき）
    return domain_of(iid)


def _steps_text(cand: dict) -> list[str]:
    return [str(s) for s in cand.get("steps") or []]


def _new_test(data: dict, c: dict) -> dict:
    return {
        "id": _ta2._next_id(data), "case_id": c["candidate_id"], "screen": "", "name": str(c.get("title") or ""),
        "technique": str(c.get("kind") or ""), "category": "docassure", "source": "docassure",
        "steps": [], "design_steps": _steps_text(c), "status": "new", "history": [], "last": {},
        "candidate_id": c["candidate_id"], "requirement_id": str(c.get("requirement_id") or ""),
        "state": "GENERATED", "execution": "NOT_EXECUTED", "verification": "NOT_VERIFIED",
        "provenance": str(c.get("provenance") or "INFERRED"), "updated_at": _ta2._now(),
    }


def push_candidates(iid: str, candidates: list[dict]) -> dict:
    """設計案を System02 へ登録する。候補なし（required_clarification）は登録しない。"""
    domain = _check_inspection(iid)
    created: list[dict] = []
    skipped: list[str] = []
    rejected: list[str] = []
    with _perm.locked(_ta2.base_dir(domain)):
        data = _ta2._loaded(domain)
        existing = {str(t.get("candidate_id")): t for t in data.get("tests") or [] if t.get("candidate_id")}
        tests = [dict(t) for t in data.get("tests") or []]
        data = {**data, "tests": tests}
        for c in candidates or []:
            cid = c.get("candidate_id")
            if not cid or c.get("required_clarification"):
                rejected.append(str(c.get("requirement_id") or ""))
                continue
            if cid in existing:
                skipped.append(cid)
                continue
            t = _new_test(data, c)
            tests.append(t)
            existing[cid] = t
            created.append({"candidate_id": cid, "test_id": t["id"]})
        if created:
            _ta2.save(domain, data)
    return {"domain": domain, "created": created, "already_registered": skipped,
            "not_registered_requirements": rejected, "state": "GENERATED", "execution": "NOT_EXECUTED",
            "verification": "NOT_VERIFIED"}


def _tests(iid: str) -> list[dict]:
    domain = _check_inspection(iid)
    return [t for t in (_ta2.load(domain).get("tests") or []) if t.get("source") == "docassure"]


def _executed(t: dict) -> bool:
    return bool((t.get("last") or {}).get("at"))


def pull_status(iid: str, requirement_ids: list[str] | None = None) -> dict[str, dict]:
    tests = _tests(iid)
    wanted = list(requirement_ids) if requirement_ids is not None else sorted({t["requirement_id"] for t in tests})
    out: dict[str, dict] = {}
    for rid in wanted:
        ts = [t for t in tests if t.get("requirement_id") == rid]
        ran = [t for t in ts if _executed(t)]
        failed = any(t.get("status") in _FAIL for t in ran)
        passed = bool(ran) and not failed and all(t.get("status") == "pass" for t in ran)
        verified = passed and len(ran) == len(ts) and all(t.get("verification") == "VERIFIED" for t in ts)
        out[rid] = {
            "designed": bool(ts),
            "generated": any(t.get("state") == "GENERATED" for t in ts),
            "executed": True if ran else None,
            "result": "FAILED" if failed else ("PASSED" if passed else "NONE"),
            "verified": True if verified else None,
            "test_ids": [t["id"] for t in ts],
        }
    return out


def as_execution(iid: str) -> dict[str, dict]:
    """coverage.compute の execution 引数用。未実行のテストは NOT_EXECUTED（実行に数えない）。"""
    out: dict[str, dict] = {}
    for t in _tests(iid):
        if not _executed(t):
            s = "NOT_EXECUTED"
        else:
            s = "PASSED" if t.get("status") == "pass" else "FAILED"
        out[f"TEST:{t['id']}"] = {"status": s}
    return out


def tests_for_graph(iid: str) -> list[dict]:
    """trace_graph の tests 引数用（要件 ID を明示リンクとして持つ）。"""
    return [{"test_id": t["id"], "title": t.get("name", ""), "requirement_ids": [t["requirement_id"]]}
            for t in _tests(iid)]
