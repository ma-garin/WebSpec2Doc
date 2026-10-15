"""影響度分析（System 09）の API v2: 対象システム・メンバー・文書・項目・ベースライン・つながり・監査。

変更要求・分析・影響・承認・レポートは impact_api_cr.py。契約は
docs/lifecycle/system09-impact/03-detailed-design.md の DD-006。
"""
from __future__ import annotations

import csv
import io
import logging
from contextlib import closing

from flask import Blueprint, Response, g, jsonify, request

from web.auth import effective_auth_mode
from web.services.impact import db, roles
from web.services.impact.repo import audit, baselines, documents, links, systems
from web.services.impact.repo.errors import ImpactError

bp = Blueprint("impact_api", __name__, url_prefix="/api/impact/v2")
log = logging.getLogger(__name__)
LOCAL_ACTOR = "local"


def actor() -> str:
    """操作した人。認証オフでは local（全対象システムで管理者として扱う。DD-003）。"""
    user = getattr(g, "auth_user", None)
    name = str(user.get("email") or user.get("name") or "") if isinstance(user, dict) else ""
    if not name and effective_auth_mode() == "off":
        return LOCAL_ACTOR
    return name or LOCAL_ACTOR


def body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@bp.errorhandler(ImpactError)
def _impact_error(exc: ImpactError):
    return jsonify(error=exc.message), exc.status


@bp.errorhandler(Exception)
def _unexpected(exc: Exception):
    if hasattr(exc, "code") and isinstance(getattr(exc, "code"), int):
        return jsonify(error="その操作はできません。画面を再読み込みしてください。"), exc.code
    log.exception("影響度分析 API で想定外の失敗")
    return jsonify(error="処理できませんでした。時間をおいてもう一度お試しください。"), 500


_RECOVERED: set[str] = set()


def open_db():
    """テナント別 DB を開く。プロセスで初めて開く DB は、中断した分析を復帰させる（REQ-N-006）。"""
    conn = db.connect()
    key = str(db.db_path())
    if key not in _RECOVERED:
        from web.services.impact import jobs
        jobs.recover(conn)
        _RECOVERED.add(key)
    return closing(conn)


def guard(conn, sid: str, action: str) -> str:
    who = actor()
    roles.require(conn, sid, who, action)
    return who


# ---- 対象システム ----
@bp.get("/systems")
def list_systems():
    with open_db() as conn:
        return jsonify(systems=systems.list_for(conn, actor()))


@bp.post("/systems")
def create_system():
    b = body()
    with open_db() as conn:
        s = systems.create(conn, str(b.get("name") or "").strip(), str(b.get("description") or "").strip(), actor())
        return jsonify(system=s), 201


@bp.get("/systems/<sid>")
def get_system(sid: str):
    with open_db() as conn:
        who = guard(conn, sid, "view")
        return jsonify(system=systems.get(conn, sid), my_role=systems.role_of(conn, sid, who) or "admin")


@bp.patch("/systems/<sid>")
def update_system(sid: str):
    with open_db() as conn:
        who = guard(conn, sid, "edit_system")
        return jsonify(system=systems.update(conn, sid, body(), who))


@bp.delete("/systems/<sid>")
def delete_system(sid: str):
    with open_db() as conn:
        who = guard(conn, sid, "edit_system")
        systems.delete(conn, sid, who)
        return jsonify(ok=True)


@bp.get("/systems/<sid>/members")
def list_members(sid: str):
    with open_db() as conn:
        guard(conn, sid, "view")
        return jsonify(members=systems.get(conn, sid).get("members", []))


@bp.put("/systems/<sid>/members/<path:target>")
def put_member(sid: str, target: str):
    with open_db() as conn:
        who = guard(conn, sid, "members")
        systems.set_member(conn, sid, target, str(body().get("role") or ""), who)
        return jsonify(members=systems.get(conn, sid).get("members", []))


@bp.delete("/systems/<sid>/members/<path:target>")
def delete_member(sid: str, target: str):
    with open_db() as conn:
        who = guard(conn, sid, "members")
        systems.remove_member(conn, sid, target, who)
        return jsonify(members=systems.get(conn, sid).get("members", []))


# ---- 文書・項目 ----
@bp.get("/systems/<sid>/documents")
def list_documents(sid: str):
    with open_db() as conn:
        guard(conn, sid, "view")
        return jsonify(documents=documents.list(conn, sid))


@bp.post("/systems/<sid>/documents")
def upload_documents(sid: str):
    files = request.files.getlist("files") + request.files.getlist("file")
    if not files:
        raise ImpactError("文書が選ばれていません。設計書・画面仕様書・テストケースを選んでください。", 400)
    added, failed = [], []
    with open_db() as conn:
        who = guard(conn, sid, "documents")
        work = db.db_path().parent / "work" / sid
        for f in files:
            try:
                added.append(documents.add(conn, sid, f.filename or "", f.read(), who, work))
            except ImpactError as exc:
                failed.append({"name": f.filename or "", "error": exc.message})
        if failed and not added:
            return jsonify(error=" / ".join(f"{x['name']}: {x['error']}" for x in failed), failed=failed,
                           documents=documents.list(conn, sid)), 400
        return jsonify(added=added, failed=failed, documents=documents.list(conn, sid))


@bp.patch("/systems/<sid>/documents/<doc_id>")
def patch_document(sid: str, doc_id: str):
    with open_db() as conn:
        who = guard(conn, sid, "documents")
        documents.set_kind(conn, sid, doc_id, str(body().get("kind") or ""), who)
        return jsonify(documents=documents.list(conn, sid))


@bp.delete("/systems/<sid>/documents/<doc_id>")
def delete_document(sid: str, doc_id: str):
    with open_db() as conn:
        who = guard(conn, sid, "documents")
        documents.remove(conn, sid, doc_id, who)
        return jsonify(documents=documents.list(conn, sid))


@bp.get("/systems/<sid>/items")
def list_items(sid: str):
    a = request.args
    with open_db() as conn:
        guard(conn, sid, "view")
        offset = max(int(a.get("offset") or 0), 0) if str(a.get("offset") or "0").isdigit() else 0
        return jsonify(items=documents.items(conn, sid, a.get("doc") or None, a.get("q") or None, 200, offset))


# ---- ベースライン ----
@bp.get("/systems/<sid>/baselines")
def list_baselines(sid: str):
    with open_db() as conn:
        guard(conn, sid, "view")
        return jsonify(baselines=baselines.list(conn, sid))


@bp.post("/systems/<sid>/baselines")
def create_baseline(sid: str):
    b = body()
    with open_db() as conn:
        who = guard(conn, sid, "baselines")
        bl = baselines.create(conn, sid, str(b.get("name") or "").strip(), str(b.get("note") or "").strip(), who)
        return jsonify(baseline=bl, baselines=baselines.list(conn, sid)), 201


@bp.get("/systems/<sid>/baselines/diff")
def diff_baselines(sid: str):
    old, new = request.args.get("old") or "", request.args.get("new") or ""
    with open_db() as conn:
        guard(conn, sid, "view")
        ids = {x["id"] for x in baselines.list(conn, sid)}
        if old not in ids or new not in ids:
            raise ImpactError("比べるベースラインを 2 つ選び直してください。", 400)
        return jsonify(diff=baselines.diff(conn, old, new))


# ---- つながり ----
@bp.get("/systems/<sid>/links")
def list_links(sid: str):
    item = request.args.get("item") or ""
    with open_db() as conn:
        guard(conn, sid, "view")
        rows = links.neighbors(conn, sid, item) if item else links.list(conn, sid)
        return jsonify(links=rows)


@bp.post("/systems/<sid>/links")
def add_link(sid: str):
    b = body()
    with open_db() as conn:
        who = guard(conn, sid, "links")
        a_item, b_item = str(b.get("a") or b.get("a_item") or ""), str(b.get("b") or b.get("b_item") or "")
        return jsonify(link=links.add(conn, sid, a_item, b_item, who)), 201


@bp.delete("/systems/<sid>/links/<link_id>")
def delete_link(sid: str, link_id: str):
    with open_db() as conn:
        who = guard(conn, sid, "links")
        links.remove(conn, sid, link_id, who)
        return jsonify(ok=True)


@bp.post("/systems/<sid>/links/suggest")
def suggest_links(sid: str):
    from web.services.impact.engine.embed import make_embedder
    with open_db() as conn:
        guard(conn, sid, "links")
        made = links.suggest(conn, sid, make_embedder(systems.get(conn, sid)["policy"]))
        return jsonify(created=made, suggestions=links.suggestions(conn, sid))


@bp.get("/systems/<sid>/links/suggestions")
def list_suggestions(sid: str):
    with open_db() as conn:
        guard(conn, sid, "view")
        return jsonify(suggestions=links.suggestions(conn, sid))


@bp.post("/systems/<sid>/links/suggestions/<sug_id>")
def decide_suggestion(sid: str, sug_id: str):
    with open_db() as conn:
        who = guard(conn, sid, "links")
        links.decide(conn, sid, sug_id, bool(body().get("accept")), who)
        return jsonify(suggestions=links.suggestions(conn, sid))


# ---- 監査 ----
def _audit_rows(conn, sid: str) -> list[dict]:
    a = request.args
    return audit.query(conn, sid, a.get("since") or None, a.get("until") or None,
                       a.get("actor") or None, a.get("cr") or None, 500)


@bp.get("/systems/<sid>/audit")
def get_audit(sid: str):
    with open_db() as conn:
        guard(conn, sid, "audit_view")
        return jsonify(audit=_audit_rows(conn, sid))


@bp.get("/systems/<sid>/audit.csv")
def get_audit_csv(sid: str):
    with open_db() as conn:
        guard(conn, sid, "audit_view")
        rows = _audit_rows(conn, sid)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["日時", "操作者", "変更要求", "操作", "対象", "変更前", "変更後"])
    for r in rows:
        w.writerow([r.get("at"), r.get("actor"), r.get("cr_code") or r.get("cr_id") or "", r.get("action"),
                    r.get("target"), r.get("before") or "", r.get("after") or ""])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''impact-audit.csv"})
