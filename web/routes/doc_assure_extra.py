"""Document Assurance 追加 API（回帰・baseline・フィードバック・ポリシー）。権限は doc_assure と同じ流儀。"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from web.routes.doc_assure import _err, _insp
from web.services.docverify import perm as _perm

bp = Blueprint("doc_assure_extra", __name__)
_BASE = "/api/docassure/inspections/<iid>"


def _result(iid):
    from web.services.docassure import store
    insp, err = _insp(iid)
    if err:
        return None, err
    r = store.load(iid)
    if r is None:
        return None, _err("まだ分析していません。先に分析を実行してください。", 404, "not_analyzed")
    return r, None


@bp.route(f"{_BASE}/regression", methods=["GET"])
def regression_view(iid: str):
    from web.services.docassure import baseline, regression
    r, err = _result(iid)
    if err:
        return err
    prev = r.get("previous_requirements")
    if not prev:
        return _err("比較できる前版がありません。文書を更新して再分析してください。", 404, "no_previous")
    before = {"requirements": prev, **(baseline.get(iid) or {})}
    return jsonify(regression.review(before, r))


@bp.route(f"{_BASE}/baseline", methods=["POST"])
@_perm.require("finding_edit")
def baseline_set(iid: str):
    from web.services.docassure import baseline
    r, err = _result(iid)
    if err:
        return err
    snap = baseline.set(iid, r)
    return jsonify(ok=True, count=len(snap["findings"])), 201


@bp.route(f"{_BASE}/baseline/compare", methods=["GET"])
def baseline_compare(iid: str):
    from web.services.docassure import baseline
    r, err = _result(iid)
    if err:
        return err
    b = baseline.get(iid)
    if b is None:
        return _err("baseline が未登録です。先に現在の指摘を baseline に登録してください。", 404, "no_baseline")
    return jsonify(baseline.compare(b, r))


@bp.route(f"{_BASE}/feedback", methods=["POST"])
@_perm.require("finding_edit")
def feedback_add(iid: str):
    from web.services.docassure import feedback
    from web.services.docverify.settings import current_user
    r, err = _result(iid)
    if err:
        return err
    b = request.get_json(silent=True) or {}
    fid, kind = b.get("finding_id"), b.get("kind")
    if kind not in feedback.KINDS:
        return _err("kind は useful / false_positive / not_applicable のいずれかで指定してください。", 400, "bad_kind")
    if not isinstance(fid, str) or not fid or len(fid) > 200:
        return _err("finding_id を指定してください（200 字以内）。", 400, "bad_finding_id")
    if fid not in {f.get("finding_id") for f in r.get("findings") or []}:
        return _err("指摘が見つかりません。指摘一覧から選び直してください。", 404, "finding_not_found")
    return jsonify(ok=True, feedback=feedback.add(iid, fid, kind, current_user())), 201


@bp.route(f"{_BASE}/feedback/stats", methods=["GET"])
def feedback_stats(iid: str):
    from web.services.docassure import feedback
    r, err = _result(iid)
    if err:
        return err
    return jsonify(feedback.stats(iid, len(r.get("requirements") or []), len(r.get("findings") or [])))


@bp.route(f"{_BASE}/policy", methods=["GET"])
def policy_get(iid: str):
    from web.services.docassure import policy
    _, err = _insp(iid)
    if err:
        return err
    return jsonify(policy=policy.load(iid))


@bp.route(f"{_BASE}/policy", methods=["PUT"])
@_perm.require("plan_edit")
def policy_put(iid: str):
    from web.services.docassure import policy
    _, err = _insp(iid)
    if err:
        return err
    try:
        return jsonify(ok=True, policy=policy.save(iid, request.get_json(silent=True)))
    except ValueError as e:
        return _err(f"{e}。内容を直してからもう一度保存してください。", 400, "bad_policy")
