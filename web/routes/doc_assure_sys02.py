"""System06 ⇔ System02 連携 API。テスト設計案の登録と、System02 側の実行状態の読み戻し。"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify

from web.routes.doc_assure import _err, _insp
from web.services.docverify import perm as _perm

bp = Blueprint("doc_assure_sys02", __name__)
log = logging.getLogger(__name__)


@bp.route("/api/docassure/inspections/<iid>/system02/push", methods=["POST"])
@_perm.require("finding_edit")
def push(iid: str):
    from web.services.docassure import integrations, links_sys02, store
    insp, err = _insp(iid)
    if err:
        return err
    r = store.load(iid)
    if r is None:
        return _err("まだ分析していません。先に分析を実行してください。", 404, "not_analyzed")
    try:
        res = links_sys02.push_candidates(iid, integrations.test_candidates(r.get("requirements") or []))
    except Exception:
        log.exception("System02 への登録に失敗")
        return _err("System02 へ登録できませんでした。もう一度お試しください。", 500)
    _perm.record("docassure_sys02_push", iid, {"created": len(res["created"])})
    return jsonify(res)


@bp.route("/api/docassure/inspections/<iid>/system02/status", methods=["GET"])
def status(iid: str):
    from web.services.docassure import links_sys02
    insp, err = _insp(iid)
    if err:
        return err
    return jsonify(status=links_sys02.pull_status(iid), execution=links_sys02.as_execution(iid))
