"""System06 → System09 の結線 API。要件の意味差分を影響度分析へ投入し、影響候補を返す。"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from web.routes.doc_assure import _err, _insp
from web.services.docverify import perm as _perm

bp = Blueprint("doc_assure_sys09", __name__)


@bp.route("/api/docassure/inspections/<iid>/system09/analyze", methods=["POST"])
@_perm.require("finding_edit")
def analyze(iid: str):
    from web.routes.impact_api import actor
    from web.services.docassure import links_sys09, semantic_diff, store
    insp, err = _insp(iid)
    if err:
        return err
    r = store.load(iid)
    if r is None or not r.get("previous_requirements"):
        return _err("比較できる前の版がありません。文書を更新して再分析してください。", 404, "no_previous")
    body = request.get_json(silent=True) or {}
    sid = body.get("system_id")
    if sid is not None and not isinstance(sid, str):
        return _err("対象システムの指定が正しくありません。一覧から選び直してください。", 400, "bad_system")
    d = semantic_diff.diff(r["previous_requirements"], r.get("requirements") or [])
    try:
        out = links_sys09.submit_changes(iid, d, r.get("requirements") or [], sid, actor())
    except links_sys09.Sys09Error as exc:
        return _err(exc.message, exc.status, exc.code)
    return jsonify(out)


@bp.route("/api/docassure/inspections/<iid>/system09/impact", methods=["GET"])
def impact(iid: str):
    from web.services.docassure import links_sys09
    insp, err = _insp(iid)
    if err:
        return err
    out = links_sys09.fetch_impact(iid)
    if out is None:
        return _err("まだ影響度分析を実行していません。先に実行してください。", 404, "not_analyzed")
    return jsonify(out)
