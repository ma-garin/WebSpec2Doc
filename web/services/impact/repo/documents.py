"""文書と項目（DD-002 / BD-004）。"""
from __future__ import annotations

import hashlib
import re
import unicodedata

from web.services.impact import db
from web.services.impact.repo import audit
from web.services.impact.repo.errors import ImpactError

KINDS = ("requirement", "design", "screen", "testcase", "other")
PREFIX = {"requirement": "REQ", "design": "DSN", "screen": "SCR", "testcase": "TC", "other": "DOC"}
_NOT_FOUND = "文書が見つかりません。画面を再読み込みしてください。"
_ITEM_SQL = ("SELECT i.*, d.name AS document_name, d.kind AS kind FROM items i "
             "JOIN documents d ON d.id = i.document_id")


def guess_kind(name) -> str:
    n = unicodedata.normalize("NFKC", str(name or "")).lower()
    for kind, words in (("testcase", ("テスト", "test")), ("screen", ("画面", "screen", "ui")),
                        ("requirement", ("要件", "要求", "requirement")), ("design", ("設計", "design"))):
        if any(w in n for w in words):
            return kind
    return "other"


def _norm(text) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def _next_no(conn, sid, prefix) -> int:
    best = 0
    for r in conn.execute("SELECT code FROM items WHERE system_id=? AND code LIKE ?", (sid, prefix + "-%")):
        tail = r["code"].split("-", 1)[1]
        best = max(best, int(tail) if tail.isdigit() else 0)
    return best + 1


def _get(conn, sid, doc_id) -> dict:
    d = db.row(conn.execute("SELECT * FROM documents WHERE id=? AND system_id=?", (doc_id, sid)).fetchone())
    if d is None:
        raise ImpactError(_NOT_FOUND, 404)
    return d


def _store_items(conn, sid, doc_id, kind, passages) -> None:
    """同じ本文の項目は ID と項目コードを引き継ぎ（つながりを残す）、それ以外は新しく採番する。"""
    old = {}
    for r in conn.execute("SELECT id, code, text FROM items WHERE document_id=?", (doc_id,)):
        old.setdefault(_norm(r["text"]), []).append(dict(r))
    keep, no = set(), _next_no(conn, sid, PREFIX[kind])
    for ord_, p in enumerate(passages, start=1):
        bucket = old.get(_norm(p.get("text")))
        prev = bucket.pop(0) if bucket else None
        if prev:
            keep.add(prev["id"])
            conn.execute("UPDATE items SET location=?, ord=? WHERE id=?", (p.get("location", ""), ord_, prev["id"]))
            continue
        code = f"{PREFIX[kind]}-{no:04d}"
        no += 1
        conn.execute("INSERT INTO items(id, system_id, document_id, code, text, location, section, ord) "
                     "VALUES (?,?,?,?,?,?,?,?)",
                     (db.new_id(), sid, doc_id, code, p.get("text", ""), p.get("location", ""),
                      p.get("section", ""), ord_))
    for group in old.values():
        for r in group:
            if r["id"] not in keep:
                conn.execute("DELETE FROM items WHERE id=?", (r["id"],))


def add(conn, sid, filename, data, actor, work_dir) -> dict:
    from web.services.docverify.ingest import IngestError, ingest
    if conn.execute("SELECT 1 FROM systems WHERE id=?", (sid,)).fetchone() is None:
        raise ImpactError("対象システムが見つかりません。一覧から選び直してください。", 404)
    try:
        doc, passages = ingest(filename, data, work_dir)
    except IngestError as exc:
        raise ImpactError(f"{filename}: {exc}", 400) from exc
    name, ts = doc["name"], db.now()
    prev = db.row(conn.execute("SELECT * FROM documents WHERE system_id=? AND name=?", (sid, name)).fetchone())
    kind = prev["kind"] if prev else guess_kind(name)
    doc_id = prev["id"] if prev else db.new_id()
    sha = hashlib.sha256(data).hexdigest()
    if prev:
        conn.execute("UPDATE documents SET size=?, item_count=?, sha256=?, created_by=?, created_at=? WHERE id=?",
                     (len(data), len(passages), sha, actor, ts, doc_id))
    else:
        conn.execute("INSERT INTO documents(id, system_id, name, kind, size, item_count, sha256, created_by, "
                     "created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                     (doc_id, sid, name, kind, len(data), len(passages), sha, actor, ts))
    _store_items(conn, sid, doc_id, kind, passages)
    audit.write(conn, sid, None, actor, "document.replace" if prev else "document.add", name,
                {"sha256": prev["sha256"], "items": prev["item_count"]} if prev else None,
                {"sha256": sha, "items": len(passages), "kind": kind})
    conn.commit()
    return _get(conn, sid, doc_id)


def list(conn, sid) -> list[dict]:  # noqa: A001 契約の名前
    return db.rows(conn.execute("SELECT * FROM documents WHERE system_id=? ORDER BY name", (sid,)))


def set_kind(conn, sid, doc_id, kind, actor) -> dict:
    d = _get(conn, sid, doc_id)
    if kind not in KINDS:
        raise ImpactError("文書の種類は「要件・設計・画面・テストケース・その他」から選んでください。", 400)
    if kind != d["kind"]:
        no = _next_no(conn, sid, PREFIX[kind])
        for i, r in enumerate(conn.execute("SELECT id FROM items WHERE document_id=? ORDER BY ord",
                                           (doc_id,)).fetchall()):
            conn.execute("UPDATE items SET code=? WHERE id=?", (f"{PREFIX[kind]}-{no + i:04d}", r["id"]))
        conn.execute("UPDATE documents SET kind=? WHERE id=?", (kind, doc_id))
        audit.write(conn, sid, None, actor, "document.kind", d["name"], {"kind": d["kind"]}, {"kind": kind})
        conn.commit()
    return _get(conn, sid, doc_id)


def remove(conn, sid, doc_id, actor) -> dict:
    d = _get(conn, sid, doc_id)
    audit.write(conn, sid, None, actor, "document.remove", d["name"], {"items": d["item_count"]}, None)
    conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    conn.commit()
    return {"id": doc_id, "removed": True}


def items(conn, sid, doc_id=None, q=None, limit=200, offset=0) -> list[dict]:
    sql, args = _ITEM_SQL + " WHERE i.system_id=?", [sid]
    if doc_id:
        sql += " AND i.document_id=?"
        args.append(doc_id)
    if q:
        sql += " AND (i.text LIKE ? OR i.code LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY d.name, i.ord LIMIT ? OFFSET ?"
    args += [max(1, min(int(limit or 200), 1000)), max(0, int(offset or 0))]
    return db.rows(conn.execute(sql, args))


def item(conn, sid, item_id) -> dict:
    r = db.row(conn.execute(_ITEM_SQL + " WHERE i.system_id=? AND i.id=?", (sid, item_id)).fetchone())
    if r is None:
        raise ImpactError("項目が見つかりません。画面を再読み込みしてください。", 404)
    return r
