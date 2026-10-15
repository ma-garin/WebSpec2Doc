"""ベースライン（作成時の項目を固定コピー）と差分（DD-002 / BD-005）。"""
from __future__ import annotations

from web.services.docverify.diff import compare
from web.services.impact import db
from web.services.impact.repo import audit
from web.services.impact.repo.errors import ImpactError

_NOT_FOUND = "ベースラインが見つかりません。画面を再読み込みしてください。"


def create(conn, sid, name, note, actor) -> dict:
    if conn.execute("SELECT 1 FROM systems WHERE id=?", (sid,)).fetchone() is None:
        raise ImpactError("対象システムが見つかりません。一覧から選び直してください。", 404)
    label = str(name or "").strip()
    if not label or len(label) > 100:
        raise ImpactError("ベースラインの名前を 1〜100 文字で入力してください。", 400)
    if conn.execute("SELECT 1 FROM baselines WHERE system_id=? AND name=?", (sid, label)).fetchone():
        raise ImpactError("同じ名前のベースラインがあります。別の名前を付けてください。", 409)
    bid = db.new_id()
    conn.execute("INSERT INTO baselines(id, system_id, name, note, created_by, created_at) VALUES (?,?,?,?,?,?)",
                 (bid, sid, label, str(note or ""), actor, db.now()))
    conn.execute("INSERT INTO baseline_items(baseline_id, item_id, document_name, kind, code, text, location, "
                 "section, ord) SELECT ?, i.id, d.name, d.kind, i.code, i.text, i.location, i.section, i.ord "
                 "FROM items i JOIN documents d ON d.id=i.document_id WHERE i.system_id=?", (bid, sid))
    count = conn.execute("SELECT COUNT(*) FROM baseline_items WHERE baseline_id=?", (bid,)).fetchone()[0]
    audit.write(conn, sid, None, actor, "baseline.create", label, None, {"id": bid, "items": count})
    conn.commit()
    return {**get(conn, bid), "item_count": count}


def get(conn, bid) -> dict:
    b = db.row(conn.execute("SELECT * FROM baselines WHERE id=?", (bid,)).fetchone())
    if b is None:
        raise ImpactError(_NOT_FOUND, 404)
    return b


def list(conn, sid) -> list[dict]:  # noqa: A001 契約の名前
    return db.rows(conn.execute(
        "SELECT b.*, (SELECT COUNT(*) FROM baseline_items x WHERE x.baseline_id=b.id) AS item_count "
        "FROM baselines b WHERE b.system_id=? ORDER BY b.created_at, b.name", (sid,)))


def items(conn, bid) -> list[dict]:
    get(conn, bid)
    return db.rows(conn.execute(
        "SELECT * FROM baseline_items WHERE baseline_id=? ORDER BY document_name, ord", (bid,)))


def diff(conn, bid_old, bid_new) -> dict:
    old_b, new_b = get(conn, bid_old), get(conn, bid_new)
    if old_b["system_id"] != new_b["system_id"]:
        raise ImpactError("同じ対象システムのベースラインを 2 つ選んでください。", 400)
    old_items, new_items = items(conn, bid_old), items(conn, bid_new)

    def passages(rows):
        return [{"id": str(i), "text": r["text"], "location": r["location"]} for i, r in enumerate(rows)]

    d = compare(passages(old_items), passages(new_items))
    return {"added": [new_items[int(p["id"])] for p in d["added"]],
            "modified": [{"old": old_items[int(c["old"]["id"])], "new": new_items[int(c["new"]["id"])]}
                         for c in d["changed"]],
            "removed": [old_items[int(p["id"])] for p in d["removed"]]}
