"""System06 → System01 の観測 Evidence 連携（/api/docassure/inspections/<iid>/system01/*）。

検査 ID の解決は doc_assure と同じ（docverify.store.load。テナント境界つき）。観測元も
テナント分離済みの出力ディレクトリ内に限る。candidate は確定した追跡ではない。
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from web.routes.doc_assure import _err, _insp

bp = Blueprint("doc_assure_sys01", __name__)
log = logging.getLogger(__name__)


@bp.route("/api/docassure/inspections/<iid>/system01/sources", methods=["GET"])
def sources(iid: str):
    from web.services.docassure import links_sys01
    _, err = _insp(iid)
    if err:
        return err
    return jsonify(sources=links_sys01.list_sources())


@bp.route("/api/docassure/inspections/<iid>/system01/candidates", methods=["GET"])
def candidates(iid: str):
    from web.services.docassure import links_sys01, store
    _, err = _insp(iid)
    if err:
        return err
    sid = (request.args.get("source") or "").strip()
    if not sid:
        return _err("観測元（source）を指定してください。", 400, "no_source")
    observed = links_sys01.fetch_observed(sid)
    if observed is None:
        return _err("観測元が見つかりません。一覧から選び直してください。", 404, "source_not_found")
    r = store.load(iid)
    if r is None:
        return _err("まだ分析していません。先に分析を実行してください。", 404, "not_analyzed")
    rep = links_sys01._report(sid) or {}
    cands = links_sys01.link(r.get("requirements") or [], observed, sid, rep.get("meta"))
    return jsonify(source=sid, observed_count=len(observed), candidates=cands, confirmed=False,
                   notice="候補は確定した追跡ではありません。観測できなかったことは存在しないことを意味しません。")
