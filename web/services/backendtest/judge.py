"""段階 8 の判定。実行結果の集計・事実と判断の分離・不具合候補（純関数）。

入力の dict は変更せず、新しい dict / list を返す。
合格に数えるのは state == "pass" だけ。未判定・未実行・実行不能・中止は合格に数えない。
"""
from __future__ import annotations

STATES = ("pass", "fail", "undetermined", "not_run", "cancelled", "error")
# 判定を確定させられない状態（合格に数えず、未検証として明示する）
UNVERIFIED_STATES = ("undetermined", "not_run", "cancelled", "error")

# System 03（defect_store.SEVERITIES）と同じ等級名
SEVERITIES = ("Critical", "High", "Medium", "Low")
_STATE_JA = {
    "pass": "合格",
    "fail": "不合格",
    "undetermined": "未判定",
    "not_run": "未実行",
    "cancelled": "中止",
    "error": "実行不能",
}
_PRIORITY_BASE = {"Must": 2, "Should": 1, "Could": 0}  # SEVERITIES の添字ではなく重み
_PRIORITY_TO_DEFECT = {"Must": "High", "Should": "Medium", "Could": "Low"}


def _state_of(result: dict) -> str:
    state = (result or {}).get("state")
    return state if state in STATES else "undetermined"


def summarize(results: list[dict]) -> dict:
    """状態ごとの件数。未知の状態は未判定に数える（合格にしない）。"""
    counts = {s: 0 for s in STATES}
    for r in results or []:
        counts[_state_of(r)] += 1
    total = sum(counts.values())
    unverified = sum(counts[s] for s in UNVERIFIED_STATES)
    return {**counts, "total": total, "unverified": unverified}


def verdict(summary: dict) -> dict:
    """全体判定。不合格 > 判定保留 > 合格の順に決める。"""
    fail = int(summary.get("fail", 0))
    unverified = int(summary.get("unverified", 0))
    total = int(summary.get("total", 0))
    passed = int(summary.get("pass", 0))
    if fail > 0:
        return {"verdict": "不合格", "reason": f"不合格 {fail} 件", "unverified": unverified}
    if unverified > 0:
        return {
            "verdict": "判定保留",
            "reason": f"未検証 {unverified} 件",
            "unverified": unverified,
        }
    if total > 0 and passed == total:
        return {"verdict": "合格", "reason": f"全 {total} 件が合格", "unverified": 0}
    return {"verdict": "判定保留", "reason": "結果が 0 件です。実行してください", "unverified": 0}


def _diff_counts(fact: dict) -> dict:
    """fact.diff_summary（added/removed/updated 件数）。無ければ空。"""
    ds = (fact or {}).get("diff_summary") or {}
    out = {}
    for key in ("added", "removed", "updated"):
        val = ds.get(key, 0)
        out[key] = len(val) if isinstance(val, (list, tuple)) else int(val or 0)
    return out


def _observed_facts(result: dict) -> dict:
    """機械が観測した事実だけ。合否や解釈は含めない。"""
    fact = result.get("fact") or {}
    return {
        "run": result.get("run"),
        "case": result.get("case"),
        "rc": fact.get("rc"),
        "observed": fact.get("observed"),
        "diff_counts": _diff_counts(fact),
        "diff_path": fact.get("diff"),
        "cause": result.get("cause"),
    }


def _judgement(result: dict, case: dict) -> dict:
    """合否と理由。人の判断があればそれを優先し、判断者を残す。"""
    state = _state_of(result)
    auto = result.get("auto") or {}
    human = result.get("human") or {}
    if human.get("verdict"):
        source, reason = "human", human.get("reason") or ""
        by = human.get("by")
    else:
        source, by = "auto", None
        reason = auto.get("rule") or result.get("cause") or ""
    if state in UNVERIFIED_STATES and not reason:
        reason = f"{_STATE_JA[state]}のため合否を判断できません"
    return {
        "state": state,
        "label": _STATE_JA[state],
        "reason": reason,
        "source": source,
        "by": by,
        "unverified": state in UNVERIFIED_STATES,
        "expected": case.get("expected") if case else None,
    }


def facts_and_judgement(results: list[dict], cases: list[dict]) -> list[dict]:
    """ケースごとに「事実」と「判断」を別フィールドで返す。"""
    by_id = {c.get("id"): c for c in cases or []}
    rows = []
    for r in results or []:
        case = by_id.get(r.get("case")) or {}
        rows.append(
            {
                "case": r.get("case"),
                "title": case.get("title") or case.get("viewpoint") or "",
                "facts": _observed_facts(r),
                "judgement": _judgement(r, case),
            }
        )
    return rows


def _severity(priority: str, counts: dict, rc) -> str:
    """観点の優先度（Must/Should/Could）を基準に、データへの影響で 1 段上げる。"""
    base = _PRIORITY_TO_DEFECT.get(priority, "Medium")
    touched = counts["removed"] + counts["updated"] + counts["added"] > 0
    crashed = isinstance(rc, int) and rc != 0
    if base == "High" and (touched or crashed):
        return "Critical"
    if base == "Medium" and touched:
        return "High"
    if base == "Low" and touched:
        return "Medium"
    return base


def _repro(result: dict, case: dict, counts: dict) -> dict:
    steps = case.get("steps") or []
    lines = [f"{i}. {s}" for i, s in enumerate(steps, 1)] if steps else []
    diff_text = (
        f"追加 {counts['added']} 件／削除 {counts['removed']} 件／変更 {counts['updated']} 件"
    )
    return {
        "input": case.get("pre") or "",
        "steps": "\n".join(lines),
        "diff": diff_text,
    }


def defects(results: list[dict], cases: list[dict]) -> list[dict]:
    """不合格から不具合候補を作る。登録（採番・保存）は呼び出し側が人の確認後に行う。"""
    by_id = {c.get("id"): c for c in cases or []}
    out = []
    for r in results or []:
        if _state_of(r) != "fail":
            continue
        case = by_id.get(r.get("case")) or {}
        counts = _diff_counts(r.get("fact") or {})
        priority = case.get("priority") or "Should"
        label = case.get("title") or case.get("viewpoint") or r.get("case")
        out.append(
            {
                "run": r.get("run"),
                "case": r.get("case"),
                "title": f"{label}: 期待と異なる結果",
                "severity": _severity(priority, counts, (r.get("fact") or {}).get("rc")),
                "priority": priority,
                "repro": _repro(r, case, counts),
                "candidate": True,
            }
        )
    return out
