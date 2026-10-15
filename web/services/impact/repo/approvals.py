"""承認・差し戻し（DD-002 / BD-013）。"""
from __future__ import annotations

from web.services.impact import db, roles
from web.services.impact.repo import audit, crs
from web.services.impact.repo.errors import ImpactError


def decide(conn, sid, code, decision, reason, actor) -> dict:
    roles.require(conn, sid, actor, "approve")
    if decision not in ("approved", "returned"):
        raise ImpactError("「承認」か「差し戻し」を選んでください。", 400)
    text = str(reason or "").strip()
    if decision == "returned" and not text:
        raise ImpactError("差し戻しの理由を入力してください。", 400)
    cr = crs._row(conn, sid, code)
    if cr["status"] != "review":
        raise ImpactError("レビュー待ちの変更要求だけ承認・差し戻しできます。画面を再読み込みしてください。", 409)
    solo = roles.is_local(actor)  # 認証オフは利用者が 1 人。本人承認を許し、監査に明記する
    if actor == cr["created_by"] and not solo:
        raise ImpactError("起票した本人は承認・差し戻しできません。別の承認者に依頼してください。", 403)
    if not solo and conn.execute("SELECT 1 FROM impacts WHERE cr_id=? AND resolved_by=?", (cr["id"], actor)).fetchone():
        raise ImpactError("この変更要求の影響を解消した本人は承認・差し戻しできません。別の承認者に依頼してください。", 403)
    aid, ts = db.new_id(), db.now()
    conn.execute("INSERT INTO approvals(id, cr_id, decision, reason, actor, at) VALUES (?,?,?,?,?,?)",
                 (aid, cr["id"], decision, text, actor, ts))
    audit.write(conn, sid, cr["id"], actor, f"cr.{'approve' if decision == 'approved' else 'return'}", code,
                None, {"decision": decision, "reason": text, **({"note": "認証オフのため本人承認"} if solo else {})})
    crs.set_status(conn, cr, decision, actor, text)
    conn.commit()
    return {"id": aid, "cr_id": cr["id"], "decision": decision, "reason": text, "actor": actor, "at": ts,
            "status": decision}
