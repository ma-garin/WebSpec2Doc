"""System 05: 実行（run）の工程と、欠陥ごとの 根拠 → 修正差分 → 再検証 → 判断 を 1 つの dict にまとめる。

画面（static/js/healing-trace.js）はこの結果だけを描く。「修正済み」は AI が宣言せず、
再検証の実データ（verify_after の失敗一覧）から「通過／失敗のまま／未検証」を決める。
判断（採用／不採用／要確認）は人の記録（run.decisions）だけから決め、AI は書かない。
"""

from __future__ import annotations

from typing import Any, Mapping

_DIFF_MAX = 6000
_TEXT_MAX = 1200
_SEVERITY = {"critical": "高", "high": "高", "medium": "中", "low": "低"}
_SETTLED = ("succeeded", "no_defects", "failed", "cancelled", "awaiting_human")
_ADOPT = {"approve": "採用", "merge": "採用", "reject": "不採用"}


def _tail(text: Any, limit: int = _TEXT_MAX) -> str:
    s = str(text or "")
    return s if len(s) <= limit else "…" + s[-limit:]


def _verify_state(v: Mapping[str, Any] | None) -> str:
    """再検証の実行状態: ran（結果あり）/ error（実行できず）/ none（未実行）。"""
    if not v:
        return "none"
    if v.get("error"):
        return "error"
    return "ran"


def _failing_ids(v: Mapping[str, Any] | None) -> set[str]:
    return {str(f.get("test_id") or "") for f in (v or {}).get("failures") or [] if isinstance(f, Mapping)}


def _verify_text(v: Mapping[str, Any] | None) -> str:
    state = _verify_state(v)
    if state == "none":
        return "未実行"
    if state == "error":
        return "実行できませんでした"
    total, failed = int(v.get("total") or 0), int(v.get("failed") or 0)
    if total:
        return f"{total} 件中 {failed} 件失敗"
    return "失敗なし" if v.get("ok") else "失敗あり（件数を取得できません）"


def _reverify(defect: Mapping[str, Any], after: Mapping[str, Any] | None) -> dict[str, Any]:
    state = _verify_state(after)
    if state == "none":
        return {"result": "unverified", "label": "未検証", "detail": "再検証はまだ実行されていません。"}
    if state == "error":
        return {"result": "unverified", "label": "判定不能",
                "detail": "再検証を実行できませんでした。検証コマンドを確認してください。"}
    test_id = str(defect.get("test_id") or "")
    still = (test_id in _failing_ids(after)) if test_id else not after.get("ok")
    detail = f"再検証: {_verify_text(after)}"
    if still:
        return {"result": "failing", "label": "失敗のまま", "detail": detail}
    return {"result": "passed", "label": "再検証で通過", "detail": detail}


def _evidence(defect: Mapping[str, Any], before: Mapping[str, Any] | None) -> dict[str, Any]:
    test_id = str(defect.get("test_id") or "")
    trace = ""
    for f in (before or {}).get("failures") or []:
        if isinstance(f, Mapping) and str(f.get("test_id") or "") == test_id:
            trace = str(f.get("traceback_tail") or "")
            break
    return {
        "test_id": test_id,
        "message": _tail(defect.get("message"), 400),
        "log": _tail(trace or defect.get("evidence") or (before or {}).get("log_tail")),
        "files": list(defect.get("suspect_files") or []),
    }


def _fix(proposal: Mapping[str, Any] | None) -> dict[str, Any]:
    if not proposal:
        return {"has_diff": False, "status": "none", "summary": "修正案はありません。", "diff": "", "files": []}
    diff = str(proposal.get("diff") or "")
    return {
        "has_diff": bool(diff.strip()),
        "status": str(proposal.get("status") or ""),
        "summary": _tail(proposal.get("summary"), 400),
        "diff": diff if len(diff) <= _DIFF_MAX else diff[:_DIFF_MAX] + "\n…（以降は報告書で確認してください）",
        "files": list(proposal.get("files_changed") or []),
        "error": _tail(proposal.get("error"), 400),
    }


def _human_decision(decisions: list[Mapping[str, Any]]) -> dict[str, Any]:
    for d in reversed(decisions):
        label = _ADOPT.get(str(d.get("action") or ""))
        if label:
            return {"value": label, "actor": str(d.get("actor") or "利用者名の記録なし"),
                    "at": str(d.get("at") or ""), "note": str(d.get("note") or ""), "by_human": True}
    return {"value": "要確認", "actor": "", "at": "", "note": "人の判断がまだありません。", "by_human": False}


def _defects(run: Mapping[str, Any], decision: dict[str, Any]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for it in run.get("iterations") or []:
        proposals = {str(p.get("defect_id") or ""): p for p in it.get("proposals") or []}
        for d in it.get("defects") or []:
            did = str(d.get("defect_id") or "")
            p = proposals.get(did)
            fix = _fix(p)
            # 差分が無い修正案は再検証が通っても「この修正で直った」根拠にならない。
            rev = _reverify(d, it.get("verify_after"))
            latest[did] = {
                "defect_id": did,
                "iteration": int(it.get("index") or 0),
                "title": str(d.get("title") or did),
                "severity": _SEVERITY.get(str(d.get("severity") or "").lower(), "中"),
                "evidence": _evidence(d, it.get("verify_before")),
                "fix": fix,
                "reverify": rev,
                "decision": decision,
            }
    return list(latest.values())


def _step(key: str, label: str, state: str, detail: str) -> dict[str, str]:
    return {"key": key, "label": label, "state": state, "detail": detail}


def _steps(run: Mapping[str, Any], defects: list[dict[str, Any]], decision: dict[str, Any]) -> list[dict[str, str]]:
    its = run.get("iterations") or []
    running = str(run.get("status") or "") not in _SETTLED
    first = its[0] if its else {}
    last = its[-1] if its else {}
    before = first.get("verify_before")
    vb = _verify_state(before)
    aborted = str(run.get("status") or "") in ("failed", "cancelled") and vb == "none"
    s1 = _step("verify", "検証", {"ran": "done", "error": "failed"}.get(vb, "current" if running else ("failed" if aborted else "pending")),
               "検証の前に止まりました" if aborted else _verify_text(before))
    s2 = _step("defects", "欠陥", "done" if vb == "ran" else "pending",
               f"{len(defects)} 件" if vb == "ran" else "未抽出")
    with_diff = sum(1 for d in defects if d["fix"]["has_diff"])
    s3 = _step("fix", "修正案", ("done" if with_diff else "warn") if defects else "pending",
               f"差分あり {with_diff} / {len(defects)} 件" if defects else "対象なし")
    after = last.get("verify_after")
    va = _verify_state(after)
    s4_state = {"ran": "done" if after and after.get("ok") else "failed", "error": "failed"}.get(va, "pending")
    s4 = _step("reverify", "再検証", s4_state, _verify_text(after))
    pr = run.get("pull_request") or {}
    s5 = _step("pr", "PR", "done" if pr.get("url") or pr.get("number") else "pending",
               f"#{pr.get('number')}" if pr.get("number") else "未作成")
    if decision["by_human"]:
        s6 = _step("decision", "人の判断", "done" if decision["value"] == "採用" else "failed",
                   f"{decision['value']}（{decision['actor']}）")
    else:
        s6 = _step("decision", "人の判断",
                   "current" if str(run.get("status") or "") == "awaiting_human" else "pending", "判断待ち")
    return [s1, s2, s3, s4, s5, s6]


def _gate(run: Mapping[str, Any], defects: list[dict[str, Any]]) -> dict[str, Any]:
    its = run.get("iterations") or []
    last = its[-1] if its else {}
    v = last.get("verify_after") or last.get("verify_before")
    state = _verify_state(v)
    if state == "none" and str(run.get("status") or "") in ("failed", "cancelled"):
        overall, o_items = "判定不能", ["検証の前に実行が止まりました（理由は画面上部のエラー欄）"]
    elif state == "none":
        overall, o_items = "未判定", ["検証がまだ実行されていません"]
    elif state == "error":
        overall, o_items = "判定不能", ["検証を実行できませんでした"]
    else:
        fails = sorted(i for i in _failing_ids(v) if i)
        overall = "合格" if v.get("ok") else "不合格"
        o_items = [f"失敗: {i}" for i in fails[:5]] or ([] if v.get("ok") else ["失敗あり（ケース名を取得できません）"])
    if not defects:
        change, c_items = ("未判定" if state != "ran" else "合格"), []
    else:
        failing = [d for d in defects if d["reverify"]["result"] == "failing"]
        unver = [d for d in defects if d["reverify"]["result"] == "unverified"]
        no_diff = [d for d in defects if not d["fix"]["has_diff"] and d["reverify"]["result"] == "passed"]
        change = "不合格" if failing else ("判定不能" if unver else "合格")
        c_items = [f"未解消（重大度{d['severity']}）: {d['title']}" for d in failing if d["severity"] == "高"]
        c_items += [f"失敗のまま: {d['title']}" for d in failing if d["severity"] != "高"]
        c_items += [f"未検証: {d['title']}" for d in unver]
        c_items += [f"差分なしで通過（修正の根拠なし）: {d['title']}" for d in no_diff]
    c_items += [f"未検証: {u}" for u in run.get("unverified") or []]
    return {"overall": {"verdict": overall, "items": o_items}, "change": {"verdict": change, "items": c_items[:8]}}


def build_trace(run: Mapping[str, Any]) -> dict[str, Any]:
    """run_store.run_to_dict の結果から、工程・欠陥ごとの証跡・判定帯・判断の記録を作る。"""
    decisions = [d for d in run.get("decisions") or [] if isinstance(d, Mapping)]
    decision = _human_decision(decisions)
    defects = _defects(run, decision)
    return {
        "run_id": str(run.get("run_id") or ""),
        "status": str(run.get("status") or ""),
        "steps": _steps(run, defects, decision),
        "defects": defects,
        "gate": _gate(run, defects),
        "audit": [{"action": _ADOPT.get(str(d.get("action") or ""), "再検証" if d.get("action") == "rerun" else "記録"),
                   "actor": str(d.get("actor") or "利用者名の記録なし"), "at": str(d.get("at") or ""),
                   "note": str(d.get("note") or "")} for d in decisions],
    }
