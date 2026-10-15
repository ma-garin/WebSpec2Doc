"""改修後レビュー（実際に影響した項目の記録と予測との突き合わせ）。DD-002 / BD-017。"""
from __future__ import annotations

from web.services.impact import db
from web.services.impact.repo import audit, crs
from web.services.impact.repo.errors import ImpactError

_OPEN_FOR = ("approved", "implemented", "verified")


def record(conn, sid, code, item_code, note, actor) -> dict:
    cr = crs._row(conn, sid, code)
    if cr["status"] not in _OPEN_FOR:
        raise ImpactError("承認済み以降の変更要求だけ記録できます。承認されてから記録してください。", 409)
    item_code = str(item_code or "").strip()
    item = conn.execute("SELECT id FROM items WHERE system_id=? AND code=?", (sid, item_code)).fetchone()
    known = conn.execute("SELECT item_id FROM impacts WHERE cr_id=? AND item_code=?", (cr["id"], item_code)).fetchone()
    if not item and not known:
        raise ImpactError("その項目 ID が見つかりません。文書の項目一覧から選び直してください。", 404)
    if conn.execute("SELECT 1 FROM actuals WHERE cr_id=? AND item_code=?", (cr["id"], item_code)).fetchone():
        raise ImpactError("この項目はすでに記録されています。", 409)
    aid, ts = db.new_id(), db.now()
    item_id = item["id"] if item else known["item_id"]
    conn.execute("INSERT INTO actuals(id, cr_id, item_id, item_code, note, recorded_by, recorded_at) "
                 "VALUES (?,?,?,?,?,?,?)", (aid, cr["id"], item_id, item_code, str(note or ""), actor, ts))
    audit.write(conn, sid, cr["id"], actor, "actual.record", item_code, None, {"note": str(note or "")})
    conn.commit()
    return {"id": aid, "cr_id": cr["id"], "item_id": item_id, "item_code": item_code, "note": str(note or ""),
            "recorded_by": actor, "recorded_at": ts}


def _review_of(conn, cr_id) -> dict:
    predicted = {r["item_code"] for r in conn.execute(
        "SELECT item_code FROM impacts WHERE cr_id=? AND state!='not_required' AND item_code IS NOT NULL", (cr_id,))}
    actual = [r["item_code"] for r in conn.execute("SELECT item_code FROM actuals WHERE cr_id=? ORDER BY recorded_at",
                                                    (cr_id,))]
    hit = sum(1 for c in actual if c in predicted)
    return {"hit": hit, "missed": [c for c in actual if c not in predicted],
            "false_alarm": len(predicted - set(actual)), "recall": round(hit / len(actual), 3) if actual else None,
            "actual": len(actual), "predicted": len(predicted)}


def review(conn, sid, code) -> dict:
    return _review_of(conn, crs._row(conn, sid, code)["id"])


def trend(conn, sid) -> list[dict]:
    out = []
    for cr in db.rows(conn.execute("SELECT id, code, title, updated_at FROM change_requests WHERE system_id=? "
                                   "AND EXISTS(SELECT 1 FROM actuals a WHERE a.cr_id=change_requests.id) "
                                   "ORDER BY code", (sid,))):
        r = _review_of(conn, cr["id"])
        decided = conn.execute("SELECT SUM(state='required'), SUM(state!='open') FROM impacts WHERE cr_id=?",
                               (cr["id"],)).fetchone()
        adopted = round(decided[0] / decided[1], 3) if decided[1] else None
        out.append({"code": cr["code"], "title": cr["title"], **r, "adoption_rate": adopted})
    return out
