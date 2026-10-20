"""対象システムとメンバー（DD-002 / BD-002・BD-003）。"""
from __future__ import annotations

from web.services.impact import db, roles
from web.services.impact.repo import audit
from web.services.impact.repo.errors import ImpactError

_FIELDS = ("name", "description", "policy", "p1_min", "p2_min", "depth_default", "code_site")
_NOT_FOUND = "対象システムが見つかりません。一覧から選び直してください。"


def _counts(conn, sid: str) -> dict:
    def n(sql):
        return conn.execute(sql, (sid,)).fetchone()[0]
    return {"documents": n("SELECT COUNT(*) FROM documents WHERE system_id=?"),
            "items": n("SELECT COUNT(*) FROM items WHERE system_id=?"),
            "baselines": n("SELECT COUNT(*) FROM baselines WHERE system_id=?"),
            "links": n("SELECT COUNT(*) FROM links WHERE system_id=?"),
            "crs": n("SELECT COUNT(*) FROM change_requests WHERE system_id=?")}


def _clean_name(name) -> str:
    text = str(name or "").strip()
    if not text or len(text) > 100:
        raise ImpactError("名前は 1〜100 文字で入力してください。", 400)
    return text


# 縮退時（規則のみ）の精度。改善に使っていない最終評価用データ（quality/commercial_eval/holdout_final/system09、
# 2 ドメイン・変更 25 件）の実測値（2026-10-20）。調整に使った評価データの値は甘く出るので使わない。
DEGRADED_RECALL = 0.819
DEGRADED_PRECISION = 0.391


def create(conn, name, description, actor) -> dict:
    sid, ts = db.new_id(), db.now()
    conn.execute("INSERT INTO systems(id, name, description, degraded_recall, degraded_precision, created_by, created_at, "
                 "updated_at) VALUES (?,?,?,?,?,?,?,?)",
                 (sid, _clean_name(name), str(description or "").strip(), DEGRADED_RECALL, DEGRADED_PRECISION, actor, ts, ts))
    conn.execute("INSERT INTO members(system_id, actor, role) VALUES (?,?,?)", (sid, actor, "admin"))
    audit.write(conn, sid, None, actor, "system.create", sid, None, {"name": name})
    conn.commit()
    return get(conn, sid)


def get(conn, sid) -> dict:
    s = db.row(conn.execute("SELECT * FROM systems WHERE id = ?", (sid,)).fetchone())
    if s is None:
        raise ImpactError(_NOT_FOUND, 404)
    members = db.rows(conn.execute("SELECT actor, role FROM members WHERE system_id=? ORDER BY actor", (sid,)))
    return {**s, "members": members, "counts": _counts(conn, sid)}


def list_for(conn, actor) -> list[dict]:
    if roles.is_local(actor):
        found = [(r["id"], "admin") for r in conn.execute("SELECT id FROM systems ORDER BY created_at DESC")]
    else:
        found = [(r["id"], r["role"]) for r in conn.execute(
            "SELECT s.id, m.role FROM systems s JOIN members m ON m.system_id=s.id WHERE m.actor=? "
            "ORDER BY s.created_at DESC", (actor,))]
    return [{**get(conn, sid), "role": role} for sid, role in found]


def _validate(merged: dict) -> dict:
    out = {**merged, "name": _clean_name(merged["name"])}
    if out["policy"] not in ("none", "local", "external"):
        raise ImpactError("送信方針は「送らない・ローカルのみ・外部へ送る」から選んでください。", 400)
    try:
        p1, p2, depth = int(out["p1_min"]), int(out["p2_min"]), int(out["depth_default"])
    except (TypeError, ValueError):
        raise ImpactError("閾値と段数は数字で入力してください。", 400) from None
    if not (1 <= p2 < p1 <= 12):
        raise ImpactError("P1 の下限は P2 の下限より大きく、1〜12 の範囲で入力してください。", 400)
    if not 1 <= depth <= 3:
        raise ImpactError("波及の段数は 1〜3 から選んでください。", 400)
    site = str(out.get("code_site") or "").strip()
    if site:
        from web.validation import _valid_domain
        if len(site) > 253 or not _valid_domain(site):
            raise ImpactError("関連付けるサイトの指定が正しくありません。一覧から選び直してください。", 400)
    return {**out, "p1_min": p1, "p2_min": p2, "depth_default": depth, "code_site": site}


def update(conn, sid, fields, actor) -> dict:
    cur = get(conn, sid)
    before = {k: cur[k] for k in _FIELDS}
    merged = _validate({**before, **{k: v for k, v in (fields or {}).items() if k in _FIELDS}})
    sets = ", ".join(f"{k}=?" for k in _FIELDS)
    conn.execute(f"UPDATE systems SET {sets}, updated_at=? WHERE id=?",
                 [merged[k] for k in _FIELDS] + [db.now(), sid])
    audit.write(conn, sid, None, actor, "system.update", sid, before, {k: merged[k] for k in _FIELDS})
    conn.commit()
    return get(conn, sid)


def delete(conn, sid, actor) -> dict:
    cur = get(conn, sid)
    audit.write(conn, sid, None, actor, "system.delete", sid, {"name": cur["name"]}, None)
    conn.execute("DELETE FROM systems WHERE id = ?", (sid,))
    conn.commit()
    return {"id": sid, "deleted": True}


def _admins(conn, sid) -> int:
    return conn.execute("SELECT COUNT(*) FROM members WHERE system_id=? AND role='admin'", (sid,)).fetchone()[0]


def set_member(conn, sid, target_actor, role, actor) -> dict:
    get(conn, sid)
    target = str(target_actor or "").strip()
    if not target or role not in roles.ROLES:
        raise ImpactError("メンバー名と役割（管理者・分析担当・承認者・閲覧者）を選んでください。", 400)
    before = role_of(conn, sid, target)
    if before == "admin" and role != "admin" and _admins(conn, sid) <= 1:
        raise ImpactError("管理者が 1 人もいなくなります。先に別の管理者を追加してください。", 409)
    conn.execute("INSERT INTO members(system_id, actor, role) VALUES (?,?,?) "
                 "ON CONFLICT(system_id, actor) DO UPDATE SET role=excluded.role", (sid, target, role))
    audit.write(conn, sid, None, actor, "member.set", target, {"role": before}, {"role": role})
    conn.commit()
    return {"actor": target, "role": role}


def remove_member(conn, sid, target_actor, actor) -> dict:
    get(conn, sid)
    before = role_of(conn, sid, target_actor)
    if before is None:
        raise ImpactError("そのメンバーは見つかりません。画面を再読み込みしてください。", 404)
    if before == "admin" and _admins(conn, sid) <= 1:
        raise ImpactError("最後の管理者は外せません。先に別の管理者を追加してください。", 409)
    conn.execute("DELETE FROM members WHERE system_id=? AND actor=?", (sid, target_actor))
    audit.write(conn, sid, None, actor, "member.remove", target_actor, {"role": before}, None)
    conn.commit()
    return {"actor": target_actor, "removed": True}


def role_of(conn, sid, actor) -> str | None:
    r = conn.execute("SELECT role FROM members WHERE system_id=? AND actor=?", (sid, actor)).fetchone()
    return r["role"] if r else None
