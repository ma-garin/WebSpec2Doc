"""System 06 対検査レビュー API（prefix /api/docverify/<iid>/pair）。契約: docs/s06/CONTRACT.md。

登録: web/__init__.py は編集禁止のため、暫定で web/routes/doc_verify.py の既存 Blueprint に register(bp) で載せる。
本来の登録（app.register_blueprint(doc_verify_pair.bp)）は docs/change-requests/S06-1.md。
"""
from __future__ import annotations

import logging

from flask import Blueprint, Response, jsonify, request

from web.services.docverify import pair_cases as pc
from web.services.docverify import pair_report as prep
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


def cases_list():
    return _call(lambda: {"cases": pc.cases()})


def cases_create():
    fs = request.files
    req, design = fs.get("requirements"), fs.get("design")
    if not req or not design:
        return _err(400, "files_required", "要件定義書と基本設計書の 2 つのファイルを選んでください。")
    f = request.form
    return _call(lambda: pc.create(f.get("name", ""), req.read(), design.read(), f.get("due", ""), pr.current_user()), status=201)


def summary(iid):
    return _call(pc.summary, iid)


def report_md(iid):
    try:
        md = pc.report_md(iid)
    except pr.PairError as e:
        return _err(e.status, e.code, e.message)
    except Exception:
        log.exception("指摘書の出力に失敗")
        return _err(500, "internal", "指摘書を作れませんでした。時間をおいてもう一度出力してください。")
    return Response(md, content_type="text/markdown; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=findings-{pr.resolve_iid(iid)}.md"})


_MIME = {"docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
         "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def _binary(iid, ext: str, build):
    try:
        data = build(iid)
    except pr.PairError as e:
        return _err(e.status, e.code, e.message)
    except Exception:
        log.exception("指摘書（%s）の出力に失敗", ext)
        return _err(500, "internal", "指摘書を作れませんでした。時間をおいてもう一度出力してください。")
    return Response(data, content_type=_MIME[ext],
                    headers={"Content-Disposition": f"attachment; filename=findings-{pr.resolve_iid(iid)}.{ext}"})


def report_docx(iid):
    return _binary(iid, "docx", prep.to_docx)


def report_xlsx(iid):
    return _binary(iid, "xlsx", prep.to_xlsx)


_RULES = (
    ("/summary", summary, ["GET"]),
    ("/report.md", report_md, ["GET"]),
    ("/report.docx", report_docx, ["GET"]),
    ("/report.xlsx", report_xlsx, ["GET"]),
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
    target.add_url_rule("/api/docverify/pair/cases", "pair_cases_list", cases_list, methods=["GET"])
    target.add_url_rule("/api/docverify/pair/cases", "pair_cases_create", cases_create, methods=["POST"])


register(bp)
