"""実行結果（JUnit XML）の取り込みと、判定帯「全体／今回の変更分」の計算。"""
from __future__ import annotations

import re

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from . import boundary

MAX_XML = 5 * 1024 * 1024
_CASE_ID = re.compile(r"\b(B-\d{2,3})\b")


class ResultError(ValueError):
    pass


def parse_junit(data: bytes, case_ids: set[str], ts: str) -> list[dict]:
    """pytest の JUnit XML から、ケース ID ごとの結果を取り出す。ケース表に無い ID は捨てる。"""
    if not data:
        raise ResultError("結果ファイルが空です。テストを実行して出た結果ファイルを選んでください。")
    if len(data) > MAX_XML:
        raise ResultError("結果ファイルが大きすぎます（5MB まで）。1 案件分の結果だけを選んでください。")
    try:
        root = ElementTree.fromstring(data)
    except (ElementTree.ParseError, DefusedXmlException) as exc:
        raise ResultError("結果ファイルを読めません。JUnit 形式の XML を選んでください。") from exc
    out: dict[str, dict] = {}
    for tc in root.iter("testcase"):
        m = _CASE_ID.search(tc.get("name", ""))
        if not m or m.group(1) not in case_ids:
            continue
        failed = tc.find("failure") if tc.find("failure") is not None else tc.find("error")
        skipped = tc.find("skipped")
        if failed is not None:
            outcome, msg = "failed", (failed.get("message") or failed.text or "")[:300]
        elif skipped is not None:
            outcome, msg = "skipped", (skipped.get("message") or "")[:300]
        else:
            outcome, msg = "passed", ""
        out[m.group(1)] = {"id": m.group(1), "outcome": outcome, "message": msg.strip(), "at": ts}
    if not out:
        raise ResultError("ケース表の ID と一致する結果がありません。最新のテストコードで実行した結果を選んでください。")
    return list(out.values())


def case_state(case: dict, results: dict[str, dict]) -> str:
    """要確認 / 手動確認 / 合格 / 不合格 / 未実行（スキップ） / 未実行。"""
    if case.get("ask"):
        return "要確認"
    if case.get("manual"):
        return "手動確認"
    r = results.get(case["id"])
    if not r:
        return "未実行"
    return {"passed": "合格", "failed": "不合格"}.get(r["outcome"], "未実行（スキップ）")


def _scope(cases: list[dict], results: dict[str, dict], label: str) -> dict:
    states = {c["id"]: case_state(c, results) for c in cases}
    count = lambda s: sum(1 for v in states.values() if v == s)  # noqa: E731
    failed = [cid for cid, s in states.items() if s == "不合格"]
    unverified = [cid for cid, s in states.items() if s not in ("合格", "不合格")]
    if not cases:
        verdict, reason = "判定不能", "対象のケースがありません。"
    elif failed:
        verdict, reason = "不合格", f"不合格 {len(failed)} 件: {'・'.join(failed[:8])}"
    elif unverified:
        verdict, reason = "判定保留", f"未検証 {len(unverified)} 件が残っています。"
    else:
        verdict, reason = "合格", "すべてのケースが合格しました。"
    return {"label": label, "total": len(cases), "passed": count("合格"), "failed": len(failed),
            "ask": count("要確認"), "manual": count("手動確認"),
            "unrun": count("未実行") + count("未実行（スキップ）"),
            "verdict": verdict, "reason": reason, "failed_ids": failed, "unverified_ids": unverified}


def verdict(job: dict) -> dict:
    cases = job.get("cases") or []
    results = {r["id"]: r for r in job.get("results") or []}
    changed = [c for c in cases if c.get("changed")]
    have = {c["obs"] for c in cases}
    missing = [o for o in boundary.DEFAULT_OBS if o not in have] if cases else []
    unverified = [{"id": c["id"], "obs": c["obs"], "state": case_state(c, results), "pre": c["pre"]}
                  for c in cases if case_state(c, results) not in ("合格", "不合格")]
    return {"states": {c["id"]: case_state(c, results) for c in cases},
            "overall": _scope(cases, results, "全体"), "changed": _scope(changed, results, "今回の変更分"),
            "missing_obs": missing, "unverified": unverified,
            "results_at": max((r["at"] for r in results.values()), default=None)}


def mark_changed(old: list[dict], new: list[dict]) -> list[dict]:
    """作り直しの前後で、観点・入力・期待結果のどれかが変わったケースに changed=True を付ける。"""
    key = lambda c: (c["obs"], c["pre"], c["exp"])  # noqa: E731
    before = {key(c) for c in old}
    return [{**c, "changed": (not old) or key(c) not in before or bool(c.get("changed") and c.get("origin") == "manual")}
            for c in new]
