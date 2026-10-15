"""トレースのつながり（項目↔項目の無向リンク）と候補（DD-002 / BD-006）。"""
from __future__ import annotations

import re

from web.services.impact import db
from web.services.impact.repo import audit
from web.services.impact.repo.errors import ImpactError

SUGGEST_MIN = 0.35   # 意味検索の候補にする類似度の下限
SUGGEST_TOP = 3      # 1 項目あたりの意味検索の候補数
_CODE = re.compile(r"\b(?:REQ|DSN|SCR|TC|DOC)-\d{4}\b")


def _item(conn, sid, item_id) -> dict:
    r = db.row(conn.execute("SELECT * FROM items WHERE id=? AND system_id=?", (item_id, sid)).fetchone())
    if r is None:
        raise ImpactError("項目が見つかりません。画面を再読み込みしてください。", 404)
    return r


def _pair(a, b) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def add(conn, sid, a_item, b_item, actor, origin="manual") -> dict:
    a, b = _item(conn, sid, a_item), _item(conn, sid, b_item)
    if a["id"] == b["id"]:
        raise ImpactError("同じ項目どうしはつなげません。別の項目を選んでください。", 400)
    if origin not in ("manual", "suggested"):
        raise ImpactError("つながりの種別が正しくありません。画面を再読み込みしてください。", 400)
    x, y = _pair(a["id"], b["id"])
    if conn.execute("SELECT 1 FROM links WHERE system_id=? AND a_item=? AND b_item=?", (sid, x, y)).fetchone():
        raise ImpactError("この 2 項目はすでにつながっています。", 409)
    lid = db.new_id()
    conn.execute("INSERT INTO links(id, system_id, a_item, b_item, origin, created_by, created_at) "
                 "VALUES (?,?,?,?,?,?,?)", (lid, sid, x, y, origin, actor, db.now()))
    audit.write(conn, sid, None, actor, "link.add", lid, None,
                {"a": a["code"], "b": b["code"], "origin": origin})
    conn.commit()
    return _one(conn, sid, lid)


_LIST_SQL = ("SELECT l.*, a.code AS a_code, b.code AS b_code, a.text AS a_text, b.text AS b_text FROM links l "
             "JOIN items a ON a.id=l.a_item JOIN items b ON b.id=l.b_item WHERE l.system_id=?")


def _one(conn, sid, lid) -> dict:
    r = db.row(conn.execute(_LIST_SQL + " AND l.id=?", (sid, lid)).fetchone())
    if r is None:
        raise ImpactError("つながりが見つかりません。画面を再読み込みしてください。", 404)
    return r


def list(conn, sid) -> list[dict]:  # noqa: A001 契約の名前
    return db.rows(conn.execute(_LIST_SQL + " ORDER BY a.code, b.code", (sid,)))


def remove(conn, sid, link_id, actor) -> dict:
    cur = _one(conn, sid, link_id)
    audit.write(conn, sid, None, actor, "link.remove", link_id,
                {"a": cur["a_code"], "b": cur["b_code"], "origin": cur["origin"]}, None)
    conn.execute("DELETE FROM links WHERE id=?", (link_id,))
    conn.commit()
    return {"id": link_id, "removed": True}


def neighbors(conn, sid, item_id) -> list[dict]:
    _item(conn, sid, item_id)
    return db.rows(conn.execute(
        "SELECT i.*, d.name AS document_name, d.kind AS kind FROM links l "
        "JOIN items i ON i.id = CASE WHEN l.a_item=? THEN l.b_item ELSE l.a_item END "
        "JOIN documents d ON d.id=i.document_id WHERE l.system_id=? AND (l.a_item=? OR l.b_item=?) ORDER BY i.code",
        (item_id, sid, item_id, item_id)))


def _code_pairs(rows) -> dict:
    by_code = {r["code"]: r for r in rows}
    found = {}
    for r in rows:
        for code in set(_CODE.findall(r["text"] or "")):
            other = by_code.get(code)
            if other and other["id"] != r["id"]:
                found[_pair(r["id"], other["id"])] = (1.0, f"本文に {code} が書かれている")
    return found


def _semantic_pairs(rows, embedder) -> dict:
    if embedder is None or not getattr(embedder, "available", False) or len(rows) < 2:
        return {}
    vecs = embedder.vectors([r["text"] or "" for r in rows])
    found = {}
    for i, r in enumerate(rows):
        for j, score in embedder.similar(vecs[i], vecs, SUGGEST_TOP + 1):
            other = rows[j]
            if j == i or score < SUGGEST_MIN or other["document_id"] == r["document_id"]:
                continue
            key = _pair(r["id"], other["id"])
            if key not in found or found[key][0] < score:
                found[key] = (round(float(score), 3), f"本文が似ている（{getattr(embedder, 'mode', '')}）")
    return found


def suggest(conn, sid, embedder) -> int:
    rows = db.rows(conn.execute("SELECT id, document_id, code, text FROM items WHERE system_id=?", (sid,)))
    known = {(r["a_item"], r["b_item"]) for r in conn.execute(
        "SELECT a_item, b_item FROM links WHERE system_id=? UNION "
        "SELECT a_item, b_item FROM link_suggestions WHERE system_id=?", (sid, sid))}
    found = {**_semantic_pairs(rows, embedder), **_code_pairs(rows)}
    made = 0
    for (a, b), (score, reason) in sorted(found.items()):
        if (a, b) in known:
            continue
        conn.execute("INSERT INTO link_suggestions(id, system_id, a_item, b_item, score, reason, state) "
                     "VALUES (?,?,?,?,?,?,'open')", (db.new_id(), sid, a, b, score, reason))
        made += 1
    conn.commit()
    return made


def suggestions(conn, sid, state="open") -> list[dict]:
    sql = ("SELECT s.*, a.code AS a_code, b.code AS b_code, a.text AS a_text, b.text AS b_text "
           "FROM link_suggestions s JOIN items a ON a.id=s.a_item JOIN items b ON b.id=s.b_item WHERE s.system_id=?")
    args = [sid]
    if state:
        sql += " AND s.state=?"
        args.append(state)
    return db.rows(conn.execute(sql + " ORDER BY s.score DESC", args))


def decide(conn, sid, sug_id, accept: bool, actor) -> dict:
    s = db.row(conn.execute("SELECT * FROM link_suggestions WHERE id=? AND system_id=?", (sug_id, sid)).fetchone())
    if s is None:
        raise ImpactError("候補が見つかりません。画面を再読み込みしてください。", 404)
    if s["state"] != "open":
        raise ImpactError("この候補は判断済みです。画面を再読み込みしてください。", 409)
    state = "accepted" if accept else "rejected"
    if accept and not conn.execute("SELECT 1 FROM links WHERE system_id=? AND a_item=? AND b_item=?",
                                   (sid, s["a_item"], s["b_item"])).fetchone():
        add(conn, sid, s["a_item"], s["b_item"], actor, origin="suggested")
    conn.execute("UPDATE link_suggestions SET state=?, decided_by=?, decided_at=? WHERE id=?",
                 (state, actor, db.now(), sug_id))
    audit.write(conn, sid, None, actor, f"suggestion.{'accept' if accept else 'reject'}", sug_id,
                {"state": "open"}, {"state": state})
    conn.commit()
    return {**s, "state": state, "decided_by": actor}
