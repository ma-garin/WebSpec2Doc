"""現行データ（data/impact/*/job.json）の移行。DD-010 / BD-019。冪等。"""
from __future__ import annotations

import tempfile
from pathlib import Path

from web.services.impact import db, store
from web.services.impact.repo import audit, crs, documents, systems
from web.services.impact.repo.errors import ImpactError

SYSTEM_NAME = "移行データ"
_KIND = {"変更": "modify", "追加": "add", "削除": "delete", "指示": "text"}
_STATE = {"accepted": "required", "rejected": "not_required"}
_ACTION = "migrate.job"


def _system_id(conn, actor) -> tuple[str, bool]:
    r = conn.execute("SELECT id FROM systems WHERE name=? ORDER BY created_at LIMIT 1", (SYSTEM_NAME,)).fetchone()
    if r:
        return r["id"], False
    return systems.create(conn, SYSTEM_NAME, "旧版の影響度分析から移行したデータ", actor)["id"], True


def _done(conn, jid) -> bool:
    return conn.execute("SELECT 1 FROM audit WHERE action=? AND target=?", (_ACTION, jid)).fetchone() is not None


def _import_docs(conn, sid, job, actor) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        for d in job.get("docs") or []:
            path = store.file_path(job, d["name"])
            if not Path(path).is_file():
                continue
            try:
                documents.add(conn, sid, d["name"], Path(path).read_bytes(), actor, Path(tmp) / "work")
            except ImpactError:
                continue   # 読めない文書は飛ばし、他の文書と影響は移す


def _item_for(conn, sid, r) -> dict | None:
    return db.row(conn.execute(
        "SELECT i.id, i.code, i.section, d.kind FROM items i JOIN documents d ON d.id=i.document_id "
        "WHERE i.system_id=? AND d.name=? AND i.location=? LIMIT 1",
        (sid, r.get("doc") or "", r.get("location") or "")).fetchone())


def _insert_impact(conn, sid, cr_id, r, p1, p2, actor) -> None:
    rv = r.get("review") or {}
    item = _item_for(conn, sid, r)
    level = max(1, min(4, int(r.get("level") or 1)))
    risk = level * 2
    state = _STATE.get(rv.get("status") or "", "open")
    resolved = state != "open"
    conn.execute(
        "INSERT INTO impacts(id, cr_id, change_ids, item_id, item_code, document_name, doc_kind, location, section, "
        "text, depth, evidence, confidence, impact_level, impact_reason, likelihood, likelihood_reason, risk, priority, "
        "state, resolve_reason, resolved_by, resolved_at, tests, test_gap, test_idea, method) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (db.new_id(), cr_id, db.dumps(r.get("changes") or []), item["id"] if item else None,
         item["code"] if item else None, r.get("doc") or "", item["kind"] if item else None,
         r.get("location") or "", item["section"] if item else "", r.get("quote") or "", 1,
         db.dumps([{"type": "keyword", "detail": r.get("why") or "", "score": r.get("score") or 0}]), None,
         level, r.get("why") or "", 2, "旧版に発生可能性が無いため中央値で移行", risk,
         int(rv.get("priority") or r.get("priority") or (1 if risk >= p1 else 2 if risk >= p2 else 3)),
         state, rv.get("note") or ("移行データ" if resolved else None), actor if resolved else None,
         db.now() if resolved else None, db.dumps([]), 0, r.get("test") or "",
         "llm" if r.get("method") == "llm" else "rule"))


def _import_job(conn, sid, job, actor) -> int:
    _import_docs(conn, sid, job, actor)
    cr = crs.create(conn, sid, job.get("name") or "移行した分析", "旧版から移行", job.get("order") or "",
                    None, None, None, actor)
    for c in job.get("changes") or []:
        conn.execute("INSERT INTO changes(id, cr_id, code, kind, location, before, after, wording_only) "
                     "VALUES (?,?,?,?,?,?,?,0)", (db.new_id(), cr["id"], c.get("id"), _KIND.get(c.get("kind"), "text"),
                                                  c.get("location"), c.get("before"), c.get("after")))
    s = systems.get(conn, sid)
    rows = job.get("impacts") or []
    for r in rows:
        _insert_impact(conn, sid, cr["id"], r, s["p1_min"], s["p2_min"], actor)
    if rows:
        ts = job.get("analyzed_at") or db.now()
        conn.execute("INSERT INTO jobs(id, cr_id, status, stage, progress, message, started_at, finished_at, engine) "
                     "VALUES (?,?,'done','save',100,'移行',?,?,?)",
                     (db.new_id(), cr["id"], ts, ts, db.dumps(job.get("engine") or {"mode": "rule"})))
        crs.set_status(conn, {**cr, "status": "draft"}, "analyzing", actor, "移行")
    audit.write(conn, sid, cr["id"], actor, _ACTION, job["id"], None, {"cr": cr["code"], "impacts": len(rows)})
    conn.commit()
    return len(rows)


def run(conn, actor) -> dict:
    result = {"systems": 0, "crs": 0, "impacts": 0}
    pending = [s["id"] for s in store.list_all() if not _done(conn, s["id"])]
    if not pending:
        return result
    sid, created = _system_id(conn, actor)
    result["systems"] = int(created)
    for jid in pending:
        try:
            job = store.load(jid)
        except (KeyError, ValueError, OSError):
            continue
        result["impacts"] += _import_job(conn, sid, job, actor)
        result["crs"] += 1
    return result
