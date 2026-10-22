"""人の判断（decisions）を分析結果へ適用する。人の判断が AI/ルールの結果で上書きされないための層。

- 確定できるのは人（source=human）の decision だけ。分析結果自体は CANDIDATE のまま。
- waiver は理由と期限が要る。期限切れは無効になり、指摘は CANDIDATE に戻って再浮上する。
"""
from __future__ import annotations

from datetime import date, datetime

_FINDING = {"accepted": "ACCEPTED", "rejected": "REJECTED", "resolved": "RESOLVED"}
_CONFLICT = {"conflict_decided": "DECIDED", "rejected": "REJECTED", "resolved": "RESOLVED"}


def _expired(expiry, today: date) -> bool:
    try:
        return datetime.fromisoformat(str(expiry)[:10]).date() < today
    except (TypeError, ValueError):
        return True   # 期限が読めない waiver は無効（安全側）


def _latest(decisions: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for d in decisions or []:
        if d.get("source") == "human" and d.get("target"):
            out[str(d["target"])] = d   # 後勝ち（時系列で追記される）
    return out


def apply(findings: list[dict], conflicts: list[dict], decisions: list[dict],
          today: date | None = None) -> tuple[list[dict], list[dict]]:
    today = today or date.today()
    by = _latest(decisions)
    fs = []
    for f in findings:
        d = by.get(str(f.get("finding_id")))
        if not d:
            fs.append(f)
        elif d["decision"] == "waived":
            if _expired(d.get("expiry"), today):
                fs.append({**f, "status": "CANDIDATE", "waiver_expired": True})
            else:
                fs.append({**f, "status": "WAIVED", "decided_by": d.get("by"), "waiver_expiry": d.get("expiry")})
        elif d["decision"] in _FINDING:
            fs.append({**f, "status": _FINDING[d["decision"]], "decided_by": d.get("by")})
        else:
            fs.append(f)
    cs = []
    for c in conflicts:
        d = by.get(str(c.get("conflict_id")))
        if d and d["decision"] in _CONFLICT:
            cs.append({**c, "status": _CONFLICT[d["decision"]], "decided_by": d.get("by"),
                       "decision_reason": d.get("reason")})   # 真実は UNKNOWN のまま（人の決定は記録であり事実の証明ではない）
        else:
            cs.append(c)
    return fs, cs


def unresolved(conflicts: list[dict]) -> list[dict]:
    return [c for c in conflicts if c.get("status") in (None, "UNRESOLVED")]
