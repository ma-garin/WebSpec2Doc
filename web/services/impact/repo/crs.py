"""変更要求（DD-002 / DD-007 / BD-007）。"""
from __future__ import annotations

from web.services.impact import db
from web.services.impact.repo import audit, impacts
from web.services.impact.repo.errors import ImpactError

STATUSES = ("draft", "analyzing", "review", "approved", "returned", "rejected", "implemented", "verified")
NEXT = {"draft": {"analyzing", "rejected"}, "analyzing": {"draft", "review"}, "review": {"approved", "returned"},
        "returned": {"analyzing", "review", "rejected"}, "approved": {"implemented"}, "implemented": {"verified"}}
LABEL = {"draft": "起票", "analyzing": "分析中", "review": "レビュー待ち", "approved": "承認済み",
         "returned": "差し戻し", "rejected": "却下", "implemented": "実装済み", "verified": "検証済み"}
_EDITABLE = ("title", "reason", "change_text", "base_baseline", "target_baseline", "depth")


def _system(conn, sid) -> dict:
    s = db.row(conn.execute("SELECT * FROM systems WHERE id=?", (sid,)).fetchone())
    if s is None:
        raise ImpactError("対象システムが見つかりません。一覧から選び直してください。", 404)
    return s


def _clean(conn, sid, values: dict, depth_default: int) -> dict:
    title = str(values.get("title") or "").strip()
    if not title or len(title) > 200:
        raise ImpactError("件名を 1〜200 文字で入力してください。", 400)
    for key in ("base_baseline", "target_baseline"):
        bid = values.get(key) or None
        if bid and not conn.execute("SELECT 1 FROM baselines WHERE id=? AND system_id=?", (bid, sid)).fetchone():
            raise ImpactError("選んだベースラインが見つかりません。一覧から選び直してください。", 404)
    depth = values.get("depth")
    try:
        depth = int(depth) if depth not in (None, "") else int(depth_default)
    except (TypeError, ValueError):
        depth = 0
    if not 1 <= depth <= 3:
        raise ImpactError("波及の段数は 1〜3 から選んでください。", 400)
    return {"title": title, "reason": str(values.get("reason") or ""), "change_text": str(values.get("change_text") or ""),
            "base_baseline": values.get("base_baseline") or None,
            "target_baseline": values.get("target_baseline") or None, "depth": depth}


def _next_code(conn, sid) -> str:
    nums = [int(r["code"][3:]) for r in conn.execute("SELECT code FROM change_requests WHERE system_id=?", (sid,))
            if str(r["code"])[3:].isdigit()]
    return f"CR-{max(nums, default=0) + 1:03d}"


def create(conn, sid, title, reason, change_text, base_baseline, target_baseline, depth, actor) -> dict:
    s = _system(conn, sid)
    v = _clean(conn, sid, {"title": title, "reason": reason, "change_text": change_text,
                           "base_baseline": base_baseline, "target_baseline": target_baseline, "depth": depth},
               s["depth_default"])
    cid, code, ts = db.new_id(), _next_code(conn, sid), db.now()
    conn.execute("INSERT INTO change_requests(id, system_id, code, title, reason, status, base_baseline, "
                 "target_baseline, change_text, depth, created_by, created_at, updated_at) "
                 "VALUES (?,?,?,?,?,'draft',?,?,?,?,?,?,?)",
                 (cid, sid, code, v["title"], v["reason"], v["base_baseline"], v["target_baseline"],
                  v["change_text"], v["depth"], actor, ts, ts))
    audit.write(conn, sid, cid, actor, "cr.create", code, None, v)
    conn.commit()
    return get(conn, sid, code)


def _row(conn, sid, code) -> dict:
    r = db.row(conn.execute("SELECT * FROM change_requests WHERE system_id=? AND code=?", (sid, code)).fetchone())
    if r is None:
        raise ImpactError("変更要求が見つかりません。一覧から選び直してください。", 404)
    return r


def get(conn, sid, code) -> dict:
    cr = _row(conn, sid, code)
    changes = db.rows(conn.execute("SELECT id, code, kind, location, before, after, wording_only FROM changes "
                                   "WHERE cr_id=? ORDER BY code", (cr["id"],)))
    job = db.row(conn.execute("SELECT * FROM jobs WHERE cr_id=? ORDER BY started_at DESC LIMIT 1",
                              (cr["id"],)).fetchone())
    approvals = db.rows(conn.execute("SELECT * FROM approvals WHERE cr_id=? ORDER BY at", (cr["id"],)))
    return {**cr, "status_label": LABEL.get(cr["status"], cr["status"]), "changes": changes,
            "summary": impacts.summary(conn, cr["id"]), "last_job": job, "approvals": approvals}


def list(conn, sid, status=None) -> list[dict]:  # noqa: A001 契約の名前
    _system(conn, sid)
    sql, args = "SELECT * FROM change_requests WHERE system_id=?", [sid]
    if status:
        sql += " AND status=?"
        args.append(status)
    return [{**r, "status_label": LABEL.get(r["status"], r["status"]), "summary": impacts.summary(conn, r["id"])}
            for r in db.rows(conn.execute(sql + " ORDER BY code DESC", args))]


def _check_review(conn, cr) -> None:
    if not conn.execute("SELECT 1 FROM jobs WHERE cr_id=? AND status='done'", (cr["id"],)).fetchone():
        raise ImpactError("まだ分析していません。分析を実行してからレビュー待ちに進めてください。", 409)
    if impacts.summary(conn, cr["id"])["open"]:
        raise ImpactError("要確認の影響が残っています。すべて対応要か対応不要に解消してから進めてください。", 409)


def set_status(conn, cr, to, actor, reason="") -> dict:
    """遷移の検査を済ませた後の状態更新と監査（approvals からも使う）。"""
    conn.execute("UPDATE change_requests SET status=?, updated_at=? WHERE id=?", (to, db.now(), cr["id"]))
    audit.write(conn, cr["system_id"], cr["id"], actor, "cr.transition", cr["code"],
                {"status": cr["status"]}, {"status": to, "reason": reason})
    return {**cr, "status": to}


def transition(conn, sid, code, to, actor, reason="") -> dict:
    if to not in STATUSES:
        raise ImpactError("その状態には変更できません。画面を再読み込みしてください。", 400)
    if to in ("approved", "returned"):
        from web.services.impact.repo import approvals
        approvals.decide(conn, sid, code, to, reason, actor)
        return get(conn, sid, code)
    cr = _row(conn, sid, code)
    if to not in NEXT.get(cr["status"], set()):
        raise ImpactError(f"「{LABEL[cr['status']]}」から「{LABEL[to]}」へは進めません。画面を再読み込みしてください。", 409)
    if to == "rejected" and not str(reason or "").strip():
        raise ImpactError("却下の理由を入力してください。", 400)
    if to == "review":
        _check_review(conn, cr)
    set_status(conn, cr, to, actor, str(reason or ""))
    conn.commit()
    return get(conn, sid, code)


def update(conn, sid, code, fields, actor) -> dict:
    cr = _row(conn, sid, code)
    if cr["status"] not in ("draft", "returned"):
        raise ImpactError("起票か差し戻しの状態でのみ編集できます。差し戻されてから編集してください。", 409)
    before = {k: cr[k] for k in _EDITABLE}
    v = _clean(conn, sid, {**before, **{k: x for k, x in (fields or {}).items() if k in _EDITABLE}}, cr["depth"])
    conn.execute("UPDATE change_requests SET title=?, reason=?, change_text=?, base_baseline=?, target_baseline=?, "
                 "depth=?, updated_at=? WHERE id=?",
                 (v["title"], v["reason"], v["change_text"], v["base_baseline"], v["target_baseline"], v["depth"],
                  db.now(), cr["id"]))
    audit.write(conn, sid, cr["id"], actor, "cr.update", code, before, v)
    conn.commit()
    return get(conn, sid, code)
