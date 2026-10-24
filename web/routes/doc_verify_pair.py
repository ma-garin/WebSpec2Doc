"""System 06 対検査レビュー API（prefix /api/docverify/<iid>/pair）。契約: docs/s06/CONTRACT.md。

登録: web/__init__.py は編集禁止のため、暫定で web/routes/doc_verify.py の既存 Blueprint に register(bp) で載せる。
本来の登録（app.register_blueprint(doc_verify_pair.bp)）は docs/change-requests/S06-1.md。
"""
from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from web.services.docverify import pair_review as pr

bp = Blueprint("doc_verify_pair", __name__)
log = logging.getLogger(__name__)
_P = "/api/docverify/<iid>/pair"


def _err(status: int, code: str, message: str):
    return jsonify(error={"code": code, "message": message}), status


def _call(fn, *args, status: int = 200):
    try:
        return jsonify(fn(*args)), status
    except pr.PairError as e:
        return _err(e.status, e.code, e.message)
    except Exception:
        log.exception("対検査レビューの処理に失敗")
        return _err(500, "internal", "処理に失敗しました。時間をおいて再読み込みしてください。")


def _body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def findings(iid):
    return _call(lambda: pr.listing(iid, pr.current_user()))


def gate(iid):
    return _call(pr.gate, iid)


def trail(iid):
    return _call(pr.trail, iid)


def docs(iid):
    return _call(pr.docs, iid)


def decide(iid, fid):
    b = _body()
    return _call(lambda: pr.decide(iid, fid, b.get("status"), b.get("reason", ""), pr.current_user(), b.get("rev")))


def revoke(iid, fid):
    b = _body()
    return _call(lambda: pr.revoke(iid, fid, pr.current_user(), b.get("reason", ""), b.get("rev")))


def approve(iid):
    b = _body()
    return _call(lambda: pr.approve(iid, b.get("reason", ""), pr.current_user(), b.get("rev")))


def analyze(iid):
    return _call(lambda: pr.analyze(iid, pr.current_user()))


_RULES = (
    ("/findings", findings, ["GET"]),
    ("/findings/<fid>/decide", decide, ["POST"]),
    ("/findings/<fid>/revoke", revoke, ["POST"]),
    ("/gate", gate, ["GET"]),
    ("/trail", trail, ["GET"]),
    ("/approve", approve, ["POST"]),
    ("/docs", docs, ["GET"]),
    ("/analyze", analyze, ["POST"]),
)


def register(target: Blueprint) -> None:
    for path, fn, methods in _RULES:
        target.add_url_rule(_P + path, f"pair_{fn.__name__}", fn, methods=methods)


register(bp)
