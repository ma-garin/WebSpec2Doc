"""段階 8 の判定帯（全体／今回の変更分）。純関数。入力は変更しない。

判定の語は共通語彙（合格／不合格／判定不能／未判定）だけを使い、件数だけでなく
不合格・未検証・期待値未確定のケースを名指しする。
今回の変更分 = 前回の判定より後に追加・変更されたケース（前回判定が無ければ全件）。
"""
from __future__ import annotations

from . import judge

NAMED_LIMIT = 20
_UNVERIFIED_JA = {"undetermined": "判定できない", "not_run": "未実行", "cancelled": "中止", "error": "実行不能"}


def _label(case: dict) -> str:
    return str(case.get("summary_ja") or case.get("variant") or case.get("check") or "")


def _changed_ids(cases: list[dict], previous: dict | None) -> set[str]:
    if not previous or not previous.get("at"):
        return {str(c.get("id")) for c in cases}
    prev_at, prev_ids = str(previous["at"]), set(previous.get("case_ids") or [])
    out = set()
    for c in cases:
        cid = str(c.get("id"))
        edited = any(str((h or {}).get("at") or "") > prev_at for h in c.get("history") or [])
        if edited or (prev_ids and cid not in prev_ids):
            out.add(cid)
    return out


def _common_verdict(summary: dict) -> str:
    if int(summary.get("total", 0)) == 0:
        return "未判定"
    if int(summary.get("fail", 0)) > 0:
        return "不合格"
    if int(summary.get("unverified", 0)) > 0:
        return "判定不能"
    return "合格"


def _band(scope: str, ids: list[str], latest: dict, by_id: dict) -> dict:
    rows = [latest.get(i) or {"case": i, "state": "not_run"} for i in ids]
    summary = judge.summarize(rows)
    named = []
    for r in rows:
        cid, state = r.get("case"), judge._state_of(r)
        case = by_id.get(cid) or {}
        if state == "fail":
            named.append({"case": cid, "kind": "不合格", "text": _label(case), "basis": case.get("basis") or "", "expected": case.get("expected") or ""})
        elif state in _UNVERIFIED_JA:
            named.append({"case": cid, "kind": "未検証", "text": f"{_UNVERIFIED_JA[state]}: {_label(case)}", "basis": case.get("basis") or "", "expected": case.get("expected") or ""})
        if (case.get("oracle") or {}).get("state") == "unconfirmed":
            named.append({"case": cid, "kind": "期待値未確定", "text": _label(case), "basis": case.get("basis") or "", "expected": ""})
    named.sort(key=lambda n: ({"不合格": 0, "期待値未確定": 1, "未検証": 2}[n["kind"]], str(n["case"])))
    return {"scope": scope, "verdict": _common_verdict(summary), "summary": summary,
            "named": named[:NAMED_LIMIT], "named_total": len(named)}


def bands(results: list[dict], cases: list[dict], previous: dict | None) -> list[dict]:
    """[全体, 今回の変更分] の 2 行。results は merged（ケースごとの最新）。"""
    latest = {str(r.get("case")): r for r in results or []}
    by_id = {str(c.get("id")): c for c in cases or []}
    all_ids = sorted(by_id) or sorted(latest)
    changed = sorted(_changed_ids(list(by_id.values()), previous))
    return [_band("全体", all_ids, latest, by_id), _band("今回の変更分", changed, latest, by_id)]
