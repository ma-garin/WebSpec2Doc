"""共通 I/F v1: リスク・判断・承認・取消・証跡（契約 A2 §3.2・§4）。

接頭 /api/common/v1/。応答は {"schema": "common.<名>/1", "data"|"error"}。
主体とテナントは auth_guard が入れた g から取り、要求本文の tenant は信用しない。
"""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from web.services.common import decisions, evidence, risks
from web.services.common.evidence import CommonError

bp = Blueprint("common_decisions_api", __name__, url_prefix="/api/common/v1")
log = logging.getLogger(__name__)


def _ok(name: str, data, status: int = 200):
    return jsonify({"schema": f"common.{name}/1", "data": data}), status


@bp.errorhandler(CommonError)
def _common_error(exc: CommonError):
    return jsonify({"schema": "common.error/1", "error": {"code": exc.code, "message": exc.message,
                                                          "detail": exc.detail, "retryable": False}}), exc.status


@bp.errorhandler(ValueError)
def _bad_value(exc: ValueError):
    log.warning("common api rejected input: %s", exc)
    return jsonify({"schema": "common.error/1", "error": {
        "code": "bad_request", "message": "入力を読み取れませんでした。内容を確認してやり直してください。",
        "detail": {}, "retryable": False}}), 400


def _body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise CommonError("bad_request", "送信内容を読み取れませんでした。画面を再読込してからやり直してください。")
    return data


def _idem() -> str:
    return request.headers.get("Idempotency-Key", "").strip()


@bp.get("/cases/<cid>/risks")
def list_risks(cid: str):
    return _ok("risks", risks.list_for(cid))


@bp.post("/cases/<cid>/risks")
def create_risk(cid: str):
    return _ok("risk", risks.create(cid, _body(), _idem()), 201)


@bp.patch("/cases/<cid>/risks/<rk>")
def update_risk(cid: str, rk: str):
    return _ok("risk", risks.update(cid, rk, _body()))


@bp.get("/cases/<cid>/decisions")
def list_decisions(cid: str):
    return _ok("decisions", decisions.list_for(cid))


@bp.post("/cases/<cid>/decisions")
def draft_decision(cid: str):
    return _ok("decision", decisions.draft(cid, _body(), _idem()), 201)


@bp.post("/cases/<cid>/decisions/<dc>/approve")
def approve_decision(cid: str, dc: str):
    return _ok("decision", decisions.approve(cid, dc, _body()))


@bp.post("/cases/<cid>/decisions/<dc>/revoke")
def revoke_decision(cid: str, dc: str):
    return _ok("decision", decisions.revoke(cid, dc, _body()))


@bp.get("/cases/<cid>/evidence")
def list_evidence(cid: str):
    evidence.require_case(cid)
    if evidence.current_actor()["user_id"] is None and _auth_on():
        raise CommonError("forbidden", "証跡の閲覧にはログインが必要です。ログインしてからやり直してください。")
    return _ok("evidence", {"rows": evidence.read(cid), "chain": evidence.verify()})


def _auth_on() -> bool:
    from web.auth import auth_enabled

    return auth_enabled()
