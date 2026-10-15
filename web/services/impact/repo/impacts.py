"""影響（解消・人の修正・集計）。DD-002 / BD-011・BD-013。"""
from __future__ import annotations

from web.services.impact import db
from web.services.impact.repo import audit
from web.services.impact.repo.errors import ImpactError

LOCKED = ("review", "approved", "implemented", "verified", "rejected")
_JSON = {"change_ids": [], "evidence": [], "tests": []}


def _decode(r: dict) -> dict:
    out = {**r, **{k: db.loads(r.get(k), d) for k, d in _JSON.items()}}
    return {**out,
            "effective_impact": r["override_impact"] if r.get("override_impact") is not None else r.get("impact_level"),
            "effective_likelihood": (r["override_likelihood"] if r.get("override_likelihood") is not None
                                     else r.get("likelihood"))}


def priority_of(risk: int, p1_min: int, p2_min: int) -> int:
    return 1 if risk >= p1_min else 2 if risk >= p2_min else 3


def list(conn, cr_id, priority=None, state=None) -> list[dict]:  # noqa: A001 契約の名前
    sql, args = "SELECT * FROM impacts WHERE cr_id=?", [cr_id]
    if priority not in (None, ""):
        sql += " AND priority=?"
        args.append(int(priority))
    if state:
        sql += " AND state=?"
        args.append(state)
    return [_decode(r) for r in db.rows(conn.execute(sql + " ORDER BY priority, risk DESC, item_code", args))]


def get(conn, impact_id) -> dict:
    r = db.row(conn.execute("SELECT * FROM impacts WHERE id=?", (impact_id,)).fetchone())
    if r is None:
        raise ImpactError("その影響は見つかりません。画面を再読み込みしてください。", 404)
    return _decode(r)


def _context(conn, impact_id) -> tuple[dict, dict]:
    imp = get(conn, impact_id)
    cr = db.row(conn.execute(
        "SELECT c.id, c.system_id, c.status, s.p1_min, s.p2_min FROM change_requests c "
        "JOIN systems s ON s.id=c.system_id WHERE c.id=?", (imp["cr_id"],)).fetchone())
    if cr["status"] in LOCKED:
        raise ImpactError("この変更要求はレビュー待ち以降のため影響を変更できません。差し戻してから操作してください。", 409)
    return imp, cr


def resolve(conn, impact_id, state, reason, actor) -> dict:
    imp, cr = _context(conn, impact_id)
    if state not in ("required", "not_required"):
        raise ImpactError("「対応要」か「対応不要」を選んでください。", 400)
    text = str(reason or "").strip()
    if not text:
        raise ImpactError("判断の理由を入力してください。", 400)
    conn.execute("UPDATE impacts SET state=?, resolve_reason=?, resolved_by=?, resolved_at=? WHERE id=?",
                 (state, text, actor, db.now(), impact_id))
    audit.write(conn, cr["system_id"], cr["id"], actor, "impact.resolve", imp["item_code"] or impact_id,
                {"state": imp["state"], "reason": imp["resolve_reason"]}, {"state": state, "reason": text})
    conn.commit()
    return get(conn, impact_id)


def _int_in(value, low, high, label) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = None
    if n is None or not low <= n <= high:
        raise ImpactError(f"{label}は {low}〜{high} から選んでください。", 400)
    return n


def override(conn, impact_id, impact_level, likelihood, reason, actor) -> dict:
    imp, cr = _context(conn, impact_id)
    level = _int_in(impact_level, 1, 4, "影響度")
    like = _int_in(likelihood, 1, 3, "発生可能性")
    text = str(reason or "").strip()
    if not text:
        raise ImpactError("修正の理由を入力してください。", 400)
    risk = level * like
    pri = priority_of(risk, cr["p1_min"], cr["p2_min"])
    conn.execute("UPDATE impacts SET override_impact=?, override_likelihood=?, override_reason=?, override_by=?, "
                 "override_at=?, risk=?, priority=? WHERE id=?",
                 (level, like, text, actor, db.now(), risk, pri, impact_id))
    audit.write(conn, cr["system_id"], cr["id"], actor, "impact.override", imp["item_code"] or impact_id,
                {"impact": imp["effective_impact"], "likelihood": imp["effective_likelihood"],
                 "risk": imp["risk"], "priority": imp["priority"]},
                {"impact": level, "likelihood": like, "risk": risk, "priority": pri, "reason": text})
    conn.commit()
    return get(conn, impact_id)


def summary(conn, cr_id) -> dict:
    rows = [_decode(r) for r in db.rows(conn.execute("SELECT * FROM impacts WHERE cr_id=?", (cr_id,)))]
    live = [r for r in rows if r["state"] != "not_required"]
    return {"total": len(rows),
            "p1": sum(1 for r in rows if r["priority"] == 1),
            "p2": sum(1 for r in rows if r["priority"] == 2),
            "p3": sum(1 for r in rows if r["priority"] == 3),
            "open": sum(1 for r in rows if r["state"] == "open"),
            "test_gap": sum(1 for r in live if r.get("test_gap")),
            "retest": sum(1 for r in live if r["tests"])}
