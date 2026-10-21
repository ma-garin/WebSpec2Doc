"""System06 Document Assurance API（/api/docassure/*）。既存 /api/docverify/* は変えない。

権限は docverify.perm の表を使い、サーバ側で強制する。検査 ID はテナント境界つきの store 経由でのみ解決する。
"""
from __future__ import annotations

import logging
import re

from flask import Blueprint, jsonify, request

from web.services.docverify import perm as _perm

bp = Blueprint("doc_assure", __name__)
log = logging.getLogger(__name__)
_IID = re.compile(r"^[0-9a-f]{12}$")
_MAX_DOCS, _MAX_CHARS = 20, 2_000_000


def _err(message: str, status: int, code: str = "error"):
    return jsonify(error=message, code=code), status


def _insp(iid: str):
    from web.services.docverify import store
    if not _IID.match(iid or ""):
        return None, _err("検査が見つかりません。検査一覧から開き直してください。", 404, "not_found")
    try:
        return store.load(iid), None
    except KeyError:
        return None, _err("検査が見つかりません。検査一覧から開き直してください。", 404, "not_found")


def _documents_from(body: dict, insp: dict) -> list[dict]:
    docs = body.get("documents")
    if isinstance(docs, list) and docs:
        return [{"id": str(d.get("id") or f"D{i+1}"), "name": str(d.get("name") or ""),
                 "type": str(d.get("type") or "other"), "text": str(d.get("text") or "")}
                for i, d in enumerate(docs) if isinstance(d, dict)]
    passages = insp.get("passages") or []
    if not passages:
        return []
    doc = insp.get("document") or {}
    return [{"id": "D1", "name": str(doc.get("name") or insp.get("name") or ""), "type": "other",
             "text": "\n".join(str(p.get("text") or "") for p in passages)}]


@bp.route("/api/docassure/inspections/<iid>/analyze", methods=["POST"])
@_perm.require("import_doc")
def analyze(iid: str):
    from web.services.docassure import pipeline, store
    insp, err = _insp(iid)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    docs = _documents_from(body, insp)
    if not docs:
        return _err("分析する文書がありません。文書を取り込むか documents を渡してください。", 400, "no_document")
    if len(docs) > _MAX_DOCS or sum(len(d["text"]) for d in docs) > _MAX_CHARS:
        return _err("文書が大きすぎます。分けて分析してください。", 413, "too_large")
    try:
        result = pipeline.analyze(docs, profile=str(body.get("profile") or "default"))
        prev = store.load(iid) or {}
        saved = store.save(iid, {**result, "decisions": prev.get("decisions") or []})
    except Exception:
        log.exception("分析に失敗")
        return _err("分析できませんでした。もう一度お試しください。", 500)
    return jsonify(saved)


def _section(name: str):
    def view(iid: str):
        from web.services.docassure import store
        insp, err = _insp(iid)
        if err:
            return err
        r = store.load(iid)
        if r is None:
            return _err("まだ分析していません。先に分析を実行してください。", 404, "not_analyzed")
        return jsonify({name: r.get(name), "mode": r.get("mode"), "readiness": r.get("readiness")})
    view.__name__ = f"view_{name}"
    return view


for _n, _p in (("requirements", "requirements"), ("findings", "issues"), ("conflicts", "conflicts"),
               ("scores", "scores"), ("readiness", "readiness")):
    bp.add_url_rule(f"/api/docassure/inspections/<iid>/{_p}", f"get_{_n}", _section(_n), methods=["GET"])


@bp.route("/api/docassure/inspections/<iid>/decisions", methods=["POST"])
@_perm.require("finding_edit")
def decide(iid: str):
    from web.services.docassure import store
    insp, err = _insp(iid)
    if err:
        return err
    b = request.get_json(silent=True) or {}
    if b.get("decision") not in ("accepted", "rejected", "waived", "resolved", "conflict_decided"):
        return _err("判断の種類が不正です。", 400, "bad_decision")
    if not b.get("target"):
        return _err("対象の ID を指定してください。", 400, "no_target")
    if b["decision"] == "waived" and not (b.get("reason") and b.get("expiry")):
        return _err("waiver には理由と期限が必要です。", 400, "waiver_incomplete")
    from web.services.docverify.settings import current_user
    entry = {"target": str(b["target"]), "decision": b["decision"], "reason": str(b.get("reason") or ""),
             "expiry": b.get("expiry"), "by": current_user(), "source": "human"}
    store.add_decision(iid, entry)
    _perm.record("docassure_decision", f"{iid}:{entry['target']}", {"decision": entry["decision"]})
    return jsonify(ok=True, decision=entry), 201
