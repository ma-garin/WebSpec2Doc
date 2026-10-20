"""System 06 R4 の API（レビュー工程・権限・楽観ロック・プリセット・指標）。WS2D-DD-006 R4 5 章。

更新系はすべて「権限 → 排他 → 版番号の照合 → 変更 → 版番号 +1 → 保存」の順で行う。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request

from web.services.docverify import perm, presets, process

bp = Blueprint("doc_verify_process", __name__)
log = logging.getLogger(__name__)

_IID = re.compile(r"^[0-9a-f]{12}$")
_P = "/api/docverify/r4"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
M_404 = "検査が見つかりません。検査一覧から開き直してください。"
M_BODY = "入力の形が正しくありません。画面を再読み込みしてやり直してください。"
M_FINDING = "指摘が見つかりません。画面を再読み込みしてやり直してください。"
M_MAX_BYTES = 20 * 1024 * 1024


class _Stop(Exception):
    def __init__(self, message: str, status: int, **extra):
        super().__init__(message)
        self.message, self.status, self.extra = message, status, extra


def _err(message: str, status: int, **extra):
    return jsonify(error=message, **extra), status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(iid: str) -> dict:
    from web.services.docverify import store
    if not _IID.match(iid or ""):
        raise _Stop(M_404, 404)
    try:
        return store.load(iid)
    except (KeyError, ValueError):
        raise _Stop(M_404, 404)


def _items(insp: dict) -> list[dict]:
    pid = process.r4(insp).get("preset_id")
    if pid:
        try:
            return presets.get(pid)["items"]
        except KeyError:
            return []
    from web.services.docverify.settings import load_checklists
    cl = next((c for c in load_checklists() if c.get("id") == insp.get("checklist_id")), None)
    return (cl or {}).get("items") or []


def view(insp: dict) -> dict:
    """画面が使う R4 の状態一式。指摘は個別レビューの独立（FR-06-034）を適用した後のもの。"""
    user = perm._context()[0]
    nxt = process.next_phase(insp)
    return {
        "rev": perm.rev_of(insp), "phase": insp.get("phase"), "type": process.type_info(insp),
        "participants": insp.get("participants") or [], "r4": process.r4(insp),
        "exit_options": process.exit_options(insp), "next_phase": nxt,
        "entry_errors": process.entry_errors(insp, nxt) if nxt else [],
        "phase_log": process.r4(insp).get("phase_log") or [], "effort": process.effort(insp),
        "indicators": process.indicators(insp, presets.load_reference()),
        "approval": process.approval_state(insp),
        "unchecked": process.unchecked(_items(insp), insp.get("checks") or {}),
        "findings": process.visible_findings(insp, user), "record": process.record_rows(insp),
    }


def _mutate(iid: str, op: str, change, rev=None):
    """権限・排他・版番号を確かめて change(insp) -> 新しい insp を保存する。"""
    from web.services.docverify import store
    try:
        insp = _load(iid)
        msg = perm.check(op, insp)
        if msg:
            return _err(msg, 403, code="forbidden")
        body = request.get_json(silent=True) if request.is_json else None
        given = rev if rev is not None else (body or {}).get("rev")
        with perm.locked(store.doc_dir(iid)):
            insp = _load(iid)
            conflict = perm.check_rev(insp, given)
            if conflict:
                return _err(conflict, 409, code="conflict", rev=perm.rev_of(insp))
            updated = perm.bump(change(insp))
            store.save(updated)
    except _Stop as s:
        return _err(s.message, s.status, **s.extra)
    return jsonify(view(updated)), 200


def _body() -> dict:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise _Stop(M_BODY, 400)
    return body


def _participants(value) -> list[dict]:
    if not isinstance(value, list):
        raise _Stop("参加者の名前と役割を入力してください。", 400)
    out = []
    for p in value:
        if not isinstance(p, dict) or not str(p.get("name") or "").strip() or p.get("role") not in process.ROLES:
            raise _Stop("参加者の名前と役割を入力してください。", 400)
        out.append({"name": str(p["name"]).strip()[:80], "role": p["role"], "done": bool(p.get("done"))})
    return out


def _guard(fn):
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except _Stop as s:
            return _err(s.message, s.status, **s.extra)
    return wrapper


@bp.route(f"{_P}/meta")
def meta():
    return jsonify(
        types=[{"id": k, "label": v["label"], "required": list(v["required"])} for k, v in process.REVIEW_TYPES.items()],
        roles=[{"id": r, "label": process.ROLE_LABEL[r]} for r in process.ROLES],
        kinds=[{"id": k, "label": v} for k, v in process.KINDS.items()],
        verdicts=[{"id": k, "label": v} for k, v in process.VERDICTS.items()],
        standards=list(process.STANDARDS), standards_note=process.STANDARDS_NOTE,
        reference=process.REFERENCE, reference_limit=process.REFERENCE_LIMIT,
        reference_override=presets.load_reference())


@bp.route(f"{_P}/inspections", methods=["POST"])
@_guard
def create():
    """種別を必須にした作成（FR-06-140）。"""
    from web.services.docverify import store
    body = _body()
    name = str(body.get("name") or "").strip()
    if not name:
        raise _Stop("レビューの名前を入力してください。", 400)
    if body.get("review_type") not in process.REVIEW_TYPES:
        raise _Stop("レビューの種別を選んでください。", 400)
    # 作った人を参加者に入れる。種別が作成者を必須にするなら作成者、それ以外は進行役（入れないと認証ありで取り込めない）
    me = perm._context()[0]
    role = "author" if "author" in process.REVIEW_TYPES[body["review_type"]]["required"] else "moderator"
    insp = {**store.new(name[:200]), "goal": str(body.get("goal") or "").strip(), "rev": 0,
            "participants": [{"name": me, "role": role, "done": False}]}
    insp = process.with_r4(insp, review_type=body["review_type"], phase_log=[
        {"phase": "plan", "started_at": _now(), "started_by": perm._context()[0], "ended_at": None, "ended_by": None}])
    store.save(insp)
    return jsonify(id=insp["id"], **view(insp)), 201


@bp.route(f"{_P}/inspections/<iid>")
@_guard
def get_state(iid: str):
    return jsonify(view(_load(iid)))


@bp.route(f"{_P}/inspections/<iid>/plan", methods=["PUT"])
@_guard
def save_plan(iid: str):
    body = _body()
    rtype = body.get("review_type")
    ps = _participants(body.get("participants", []))
    errs = process.plan_errors(rtype, ps)
    if errs:
        raise _Stop(errs[0], 400, errors=errs)
    opts = body.get("exit_options") or {}
    if not isinstance(opts, dict):
        raise _Stop(M_BODY, 400)
    clean = {k: bool(opts[k]) for k in ("require_all_verified", "require_all_individual_done") if k in opts}

    def change(insp):
        return process.with_r4({**insp, "participants": ps}, review_type=rtype,
                               independent=bool(body.get("independent")), exit_options=clean)
    return _mutate(iid, "plan_edit", change)


@bp.route(f"{_P}/inspections/<iid>/advance", methods=["POST"])
@_guard
def advance(iid: str):
    body = _body()

    def change(insp):
        target = body.get("phase") or process.next_phase(insp)
        if target not in process.type_info(insp)["phases"]:
            raise _Stop("この種別では進められない工程です。画面を再読み込みしてやり直してください。", 400)
        errs = process.entry_errors(insp, target)
        if target == "closed":
            from web.services.docverify import metrics
            s = metrics.summary(insp)
            errs = errs + ([] if s.get("exit_ok") else list(s.get("reasons") or []))
        if errs:
            raise _Stop(errs[0], 409, errors=errs)
        return process.advance(insp, target, perm._context()[0], _now())
    return _mutate(iid, "plan_edit", change)


@bp.route(f"{_P}/inspections/<iid>/effort", methods=["PUT"])
@_guard
def save_effort(iid: str):
    body = _body()
    prep, meeting = body.get("prep") or {}, body.get("meeting_minutes", 0)
    errs = process.effort_errors(prep, meeting)
    pages, kind = body.get("pages"), body.get("doc_kind")
    if pages is not None and not (isinstance(pages, (int, float)) and not isinstance(pages, bool) and pages > 0):
        errs.append("頁数は 1 以上の数で入力してください。")
    if kind not in (None, "basic", "detail"):
        errs.append("文書の種類を選び直してください。")
    if errs:
        raise _Stop(errs[0], 400, errors=errs)

    def change(insp):
        return process.with_r4(insp, effort={"prep": dict(prep), "meeting_minutes": meeting}, pages=pages, doc_kind=kind)
    return _mutate(iid, "plan_edit", change)


@bp.route(f"{_P}/inspections/<iid>/findings/<fid>/kind", methods=["POST"])
@_guard
def set_kind(iid: str, fid: str):
    kind = _body().get("kind")
    if kind not in process.KINDS:
        raise _Stop("指摘の種別を選んでください。", 400)

    def change(insp):
        if not any(f.get("id") == fid for f in insp.get("findings") or []):
            raise _Stop(M_FINDING, 404)
        perm.record("finding_kind", f"{iid}/{fid}", {"kind": kind})
        return {**insp, "findings": [{**f, "kind": kind} if f.get("id") == fid else f for f in insp["findings"]]}
    return _mutate(iid, "finding_edit", change)


@bp.route(f"{_P}/inspections/<iid>/verdict", methods=["POST"])
@_guard
def set_verdict(iid: str):
    """判定と承認欄。承認者名と日時は人が入れた値だけを保存する（D-3）。"""
    body = _body()
    verdict = body.get("verdict")
    approver = str(body.get("approver") or "").strip()
    decided = str(body.get("decided_at") or "").strip()
    if verdict not in process.VERDICTS:
        raise _Stop("判定（承認・条件付き承認・再レビュー）を選んでください。", 400)
    if not approver or not decided:
        raise _Stop("承認者の名前と日時を入力してください。", 400)

    def change(insp):
        ver = (insp.get("document") or {}).get("version")
        perm.record("approval", iid, {"verdict": verdict, "approver": approver, "doc_version": ver})
        return process.with_r4({**insp, "approval": {"approver": approver[:80], "decided_at": decided[:40],
                                                     "doc_version": ver}}, verdict=verdict)
    return _mutate(iid, "approve", change)


@bp.route(f"{_P}/inspections/<iid>/answers", methods=["POST"])
@_guard
def import_answers(iid: str):
    """質問票の回答を CSV か xlsx で取り込む（FR-06-043・044）。"""
    file = request.files.get("file")
    if file is None or not file.filename:
        raise _Stop("回答を書き込んだ質問票（CSV か Excel）を選んでください。", 400)
    data = file.read(M_MAX_BYTES + 1)
    if len(data) > M_MAX_BYTES:
        raise _Stop("ファイルが大きすぎます。20MB 以下にしてから取り込んでください。", 400)
    try:
        if file.filename.lower().endswith(".xlsx"):
            rows = process.answer_rows_xlsx(data)
        else:
            rows = process.answer_rows_csv(data.decode("utf-8-sig"))
    except ValueError as e:
        raise _Stop(str(e) if str(e) == process.M_ANSWER_HEADER else "質問票を読めませんでした。出力した質問票に回答を書いて取り込んでください。", 400)
    except Exception:
        log.exception("回答ファイルの読み取りに失敗")
        raise _Stop("質問票を読めませんでした。出力した質問票に回答を書いて取り込んでください。", 400)
    result = {}

    def change(insp):
        updated, applied, skipped = process.apply_answers(insp, rows)
        result.update(applied=applied, skipped=skipped, message=process.skipped_message(skipped))
        return updated
    resp, status = _mutate(iid, "finding_edit", change, rev=request.form.get("rev"))
    if status != 200:
        return resp, status
    return jsonify({**resp.get_json(), **result}), 200


@bp.route(f"{_P}/inspections/<iid>/preset", methods=["POST"])
@_guard
def use_preset(iid: str):
    pid = _body().get("preset_id")
    try:
        presets.get(pid)
    except KeyError as e:
        raise _Stop(str(e.args[0]), 404)
    return _mutate(iid, "plan_edit", lambda insp: process.with_r4(insp, preset_id=pid))


@bp.route(f"{_P}/inspections/<iid>/record.xlsx")
@_guard
def record_xlsx(iid: str):
    insp = _load(iid)
    try:
        data = process.record_xlsx(insp)
    except Exception:
        log.exception("レビュー記録の出力に失敗")
        raise _Stop("レビュー記録を作れませんでした。もう一度出力してください。", 500)
    return Response(data, mimetype=_XLSX,
                    headers={"Content-Disposition": f"attachment; filename=review-record-{iid}.xlsx"})


@bp.route(f"{_P}/presets")
def list_presets():
    return jsonify(presets=presets.list_presets())


def _in_use(pid: str) -> bool:
    from web.services.docverify import store
    return any((i.get("r4") or {}).get("preset_id") == pid for i in store.list_all())


@bp.route(f"{_P}/presets/<pid>/copy", methods=["POST"])
@perm.require("tenant_settings")
@_guard
def copy_preset(pid: str):
    if not presets.valid_pid(pid):
        raise _Stop(presets.M_NOT_FOUND, 404)
    try:
        return jsonify(preset=presets.duplicate(pid, (request.get_json(silent=True) or {}).get("name"))), 201
    except KeyError as e:
        raise _Stop(str(e.args[0]), 404)


@bp.route(f"{_P}/presets/<pid>", methods=["PUT", "DELETE"])
@perm.require("tenant_settings")
@_guard
def edit_preset(pid: str):
    if not presets.valid_pid(pid):
        raise _Stop(presets.M_NOT_FOUND, 404)
    try:
        if request.method == "DELETE":
            presets.delete(pid, _in_use(pid))
            return jsonify(presets=presets.list_presets())
        body = _body()
        return jsonify(preset=presets.update(pid, body.get("name"), body.get("items")))
    except KeyError as e:
        raise _Stop(str(e.args[0]), 404)
    except PermissionError as e:
        raise _Stop(str(e), 409)
    except ValueError as e:
        raise _Stop(str(e), 400)


@bp.route(f"{_P}/reference", methods=["GET", "PUT"])
@_guard
def reference():
    if request.method == "PUT":
        msg = perm.check("tenant_settings")
        if msg:
            raise _Stop(msg, 403, code="forbidden")
        try:
            presets.save_reference(_body())
        except ValueError as e:
            raise _Stop(str(e), 400)
    return jsonify(reference=process.REFERENCE, override=presets.load_reference(), limit=process.REFERENCE_LIMIT)


@bp.route(f"{_P}/audit/verify")
@perm.require("audit_view")
def audit_verify():
    return jsonify(perm.verify_log())
