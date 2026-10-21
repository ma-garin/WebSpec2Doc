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


def _dv_dir(iid: str):
    from web.services.docverify import store as _dvs
    return _dvs.doc_dir(iid)


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


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
    if not docs:   # 画面の「分析を実行」は本文を送らない。前回分析した原文があれば、それで再分析する
        try:
            prev_texts = (store.load(iid) or {}).get("source_texts") or {}
        except Exception:
            log.exception("前回の原文を読めませんでした")
            prev_texts = {}
        docs = [{"id": str(k), "name": "", "type": "other", "text": str(v)} for k, v in prev_texts.items() if v]
    if any(len(d["id"]) > 64 or len(d["name"]) > 200 for d in docs):
        return _err("文書の ID・名前が長すぎます。短くしてからもう一度お試しください。", 400, "bad_document")
    if not docs:
        return _err("分析する文書がありません。レビューに文書を取り込んでから「分析を実行」を押してください。", 400, "no_document")
    if len(docs) > _MAX_DOCS or sum(len(d["text"]) for d in docs) > _MAX_CHARS:
        return _err("文書が大きすぎます。分けて分析してください。", 413, "too_large")
    try:
        prev = store.load(iid) or {}
        from web.services.docassure import policy as _policy
        try:
            extra = _policy.as_pack_extra(_policy.load(iid) or {})
        except Exception:
            log.exception("組織ポリシーを読めませんでした（既定の規則で分析します）")
            extra = None
        tests = execution = None
        try:   # System02 のテスト設計・実行結果（無い・読めないときは未評価のまま）
            from web.services.docassure import links_sys02
            tests = links_sys02.tests_for_graph(iid) or None
            execution = links_sys02.as_execution(iid) or None
        except Exception:
            log.exception("System02 の結果を読めませんでした（テスト実行は未評価で分析します）")
        result = pipeline.analyze(docs, profile=str(body.get("profile") or "default"), pack_extra=extra or None,
                                  decisions=prev.get("decisions") or [], design_tests=tests, execution=execution)
        saved = store.save(iid, {**result, "decisions": prev.get("decisions") or [],
                                 "source_texts": {d["id"]: d["text"] for d in docs},
                                 "previous_requirements": prev.get("requirements"),
                                 "review": prev.get("review")})
    except Exception:
        log.exception("分析に失敗")
        return _err("分析できませんでした。もう一度お試しください。", 500)
    _perm.record("docassure_analyze", iid, {"documents": len(docs), "requirements": result["counts"]["requirements"]})
    return jsonify({k: v for k, v in saved.items() if k != "source_texts"})


def _section(name: str):
    def view(iid: str):
        from web.services.docassure import store
        insp, err = _insp(iid)
        if err:
            return err
        r = store.load(iid)
        if r is None:
            return _err("まだ分析していません。先に分析を実行してください。", 404, "not_analyzed")
        extra = {"testability": r.get("testability")} if name == "requirements" else {}
        return jsonify({name: r.get(name), "mode": r.get("mode"), "readiness": r.get("readiness"), **extra})
    view.__name__ = f"view_{name}"
    return view


for _n, _p in (("trace", "trace"), ("analyzers", "analyzers"), ("requirements", "requirements"), ("findings", "issues"), ("conflicts", "conflicts"),
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
    if len(str(b.get("target") or "")) > 200 or len(str(b.get("reason") or "")) > 2000:
        return _err("対象・理由が長すぎます。短くしてからもう一度お試しください。", 400, "too_long")
    if not b.get("target"):
        return _err("対象の ID を指定してください。", 400, "no_target")
    if b["decision"] == "waived" and not (b.get("reason") and b.get("expiry")):
        return _err("waiver には理由と期限が必要です。", 400, "waiver_incomplete")
    r0 = store.load(iid) or {}
    known = {str(f.get("finding_id")) for f in r0.get("findings") or []} | \
        {str(c.get("conflict_id")) for c in r0.get("conflicts") or []}
    if str(b["target"]) not in known:   # 存在しない対象への判断を記録しない
        return _err("対象の指摘・矛盾が見つかりません。再分析した後なら一覧から選び直してください。", 404, "unknown_target")
    from web.services.docverify.settings import current_user
    entry = {"target": str(b["target"]), "decision": b["decision"], "reason": str(b.get("reason") or ""),
             "expiry": b.get("expiry"), "by": current_user(), "source": "human"}
    from web.services.docassure import pipeline
    from web.services.docverify import perm as _p
    with _p.locked(_dv_dir(iid)):   # 判断の追記と再判定を 1 つの排他区間にする（M-3）
        r = store.load(iid) or {}
        decs = [*(r.get("decisions") or []), {**entry, "at": _now()}]
        # 再分析せず、保存済みの結果へ判断だけを適用し直す（ポリシー・System02 の結果を保つ。B-1・M-5）
        store.save(iid, {**pipeline.rejudge(r, decs), "decisions": decs})
    _perm.record("docassure_decision", f"{iid}:{entry['target']}", {"decision": entry["decision"]})
    return jsonify(ok=True, decision=entry), 201


@bp.route("/api/docassure/inspections/<iid>/diff", methods=["GET"])
def semantic_diff_view(iid: str):
    from web.services.docassure import semantic_diff, store
    insp, err = _insp(iid)
    if err:
        return err
    r = store.load(iid)
    if r is None:
        return _err("まだ分析していません。先に分析を実行してください。", 404, "not_analyzed")
    before = r.get("previous_requirements")
    if not before:
        return _err("比較できる前の版がありません。文書を更新して再分析すると差分を表示します。", 404, "no_previous")
    return jsonify(diff=semantic_diff.diff(before, r.get("requirements") or []))


@bp.route("/api/docassure/inspections/<iid>/review", methods=["POST"])
@_perm.require("finding_edit")
def review(iid: str):
    """AI Review Board。LLM が使えない・未設定なら DEGRADED を返す（決定論の結果は変えない）。"""
    from web.services.docassure import review_board, store
    from web.services.docverify import llm_settings
    insp, err = _insp(iid)
    if err:
        return err
    r = store.load(iid)
    if r is None:
        return _err("まだ分析していません。先に分析を実行してください。", 404, "not_analyzed")
    try:
        client = llm_settings.client_for(llm_settings.load())
    except Exception:
        log.exception("LLM 設定を読めませんでした")
        client = None
    cfg = llm_settings.load()
    body = request.get_json(silent=True) or {}
    if client is not None and cfg.get("destination") == "openai" and body.get("confirm_send") is not True:
        return jsonify(error="外部の AI へ文書の一部を送ります。送信してよければ確認してからもう一度実行してください。",
                       code="consent_required", destination="openai"), 409
    # 根拠の検証は保存済みの原文だけで行う（クライアントが渡した本文は使わない）
    docs = [{"id": k, "text": v} for k, v in (r.get("source_texts") or {}).items()]
    out = review_board.run(r.get("requirements") or [], docs, client)
    store.save(iid, {**r, "review": out})
    from web.services.docverify import audit
    from web.services.docverify.settings import current_user
    audit.append("docassure_review", current_user(), iid,
                 {"destination": cfg.get("destination") if client is not None else "none", "mode": out.get("mode")})
    return jsonify(out)


@bp.route("/api/docassure/inspections/<iid>/report.<fmt>", methods=["GET"])
def report(iid: str, fmt: str):
    from flask import Response
    from web.services.docassure import report as rp, store
    insp, err = _insp(iid)
    if err:
        return err
    r = store.load(iid)
    if r is None:
        return _err("まだ分析していません。先に分析を実行してください。", 404, "not_analyzed")
    kinds = {"md": (rp.markdown, "text/markdown"), "csv": (rp.issues_csv, "text/csv"), "json": (rp.as_json, "application/json")}
    if fmt not in kinds:
        return _err("出力形式は md・csv・json のいずれかです。", 400, "bad_format")
    fn, mime = kinds[fmt]
    return Response(fn(r), mimetype=f"{mime}; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename=document-assurance.{fmt}"})


@bp.route("/api/docassure/inspections/<iid>/tests", methods=["GET"])
def test_candidates(iid: str):
    """System02 へ渡せるテスト候補（GENERATED / NOT_EXECUTED / NOT_VERIFIED）。連携先への取り込みは未結線。"""
    from web.services.docassure import integrations, store
    insp, err = _insp(iid)
    if err:
        return err
    r = store.load(iid)
    if r is None:
        return _err("まだ分析していません。先に分析を実行してください。", 404, "not_analyzed")
    return jsonify(candidates=integrations.test_candidates(r.get("requirements") or []), wired=False)


@bp.route("/api/docassure/inspections/<iid>/impact", methods=["GET"])
def impact(iid: str):
    """System09 へ渡せる変更ペイロード。前の版が無い間は作らない。"""
    from web.services.docassure import integrations, semantic_diff, store
    insp, err = _insp(iid)
    if err:
        return err
    r = store.load(iid)
    if r is None or not r.get("previous_requirements"):
        return _err("比較できる前の版がありません。文書を更新して再分析してください。", 404, "no_previous")
    d = semantic_diff.diff(r["previous_requirements"], r.get("requirements") or [])
    return jsonify(integrations.impact_payload(d, r.get("requirements") or []))


@bp.route("/api/docassure/inspections/<iid>/alignment", methods=["POST"])
def alignment(iid: str):
    """System01 の観測 Evidence と仕様の突き合わせ。観測できなかったことは欠陥にしない。"""
    from web.services.docassure import integrations, store
    insp, err = _insp(iid)
    if err:
        return err
    r = store.load(iid)
    if r is None:
        return _err("まだ分析していません。先に分析を実行してください。", 404, "not_analyzed")
    obs = (request.get_json(silent=True) or {}).get("observed")
    if not isinstance(obs, list) or len(obs) > 2000:
        return _err("観測結果を一覧で渡してください（2000 件まで）。", 400, "bad_observed")
    return jsonify(alignment=integrations.alignment(r.get("requirements") or [], obs), wired=False)


@bp.route("/api/docassure/inspections/<iid>/rewrite/<rid>", methods=["GET"])
def rewrite_view(iid: str, rid: str):
    from web.services.docassure import rewrite, store
    insp, err = _insp(iid)
    if err:
        return err
    r = store.load(iid) or {}
    unit = next((u for u in r.get("requirements") or [] if u.get("requirement_id") == rid), None)
    if unit is None:
        return _err("その要件が見つかりません。要件一覧から選び直してください。", 404, "not_found")
    return jsonify(rewrite.propose(unit))
