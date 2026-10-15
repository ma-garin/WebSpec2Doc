"""監査ログ（追記のみ）。DD-002 / BD-014。"""
from __future__ import annotations

from web.services.impact import db


def write(conn, system_id, cr_id, actor, action, target, before=None, after=None) -> int:
    cur = conn.execute(
        "INSERT INTO audit(system_id, cr_id, actor, action, target, before, after, at) VALUES (?,?,?,?,?,?,?,?)",
        (system_id, cr_id, actor, action, str(target or ""),
         None if before is None else db.dumps(before), None if after is None else db.dumps(after), db.now()))
    return cur.lastrowid


def query(conn, sid, since=None, until=None, actor=None, cr_code=None, limit=500) -> list[dict]:
    sql = ("SELECT a.*, COALESCE(c.code, '') AS cr_code FROM audit a "
           "LEFT JOIN change_requests c ON c.id = a.cr_id WHERE a.system_id = ?")
    args: list = [sid]
    if since:
        sql += " AND a.at >= ?"
        args.append(since)
    if until:
        sql += " AND a.at <= ?"
        args.append(until)
    if actor:
        sql += " AND a.actor = ?"
        args.append(actor)
    if cr_code:
        sql += " AND c.code = ?"
        args.append(cr_code)
    sql += " ORDER BY a.id DESC LIMIT ?"
    args.append(max(1, min(int(limit or 500), 5000)))
    return [{**r, "before": db.loads(r["before"]), "after": db.loads(r["after"])}
            for r in db.rows(conn.execute(sql, args))]
