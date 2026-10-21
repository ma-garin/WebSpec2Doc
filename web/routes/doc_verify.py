"""ドキュメント検証（System 06）。検査（インスペクション）を 1 件ずつ保存して進める。

契約: docs/process/docverify-contract.md の「API」。処理の中身は web/services/docverify/ にある。
"""
from __future__ import annotations

import hashlib
import logging
import re
import tempfile
from pathlib import Path

from flask import Blueprint, Response, jsonify, render_template, request

from web.services.docverify import perm as _perm

bp = Blueprint("doc_verify", __name__)
log = logging.getLogger(__name__)

_IID = re.compile(r"^[0-9a-f]{12}$")
_STATUSES = ("candidate", "adopted", "rejected", "fixed", "verified")
_SEVERITIES = ("critical", "major", "minor")
_PHASES = ("plan", "individual", "triage", "rework", "followup", "closed")
_ROLES = ("author", "moderator", "reviewer", "scribe", "approver")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _err(message: str, status: int):
    return jsonify(error=message), status


def _load(iid: str):
    """検査を読む。無い・形が違うときは (None, 404 応答)。"""
    from web.services.docverify import store
    if not _IID.match(iid or ""):
        return None, _err("検査が見つかりません。検査一覧から開き直してください。", 404)
    try:
        return store.load(iid), None
    except KeyError:
        return None, _err("検査が見つかりません。検査一覧から開き直してください。", 404)


def _respond(insp: dict, status: int = 200, **extra):
    from web.services.docverify import metrics
    # 画面が「押せない操作」を出し分けるための役割判定（サーバの権限表と同じ関数。押して 403 になる導線を作らない）
    user, is_admin, auth_on = _perm._context()
    roles = _perm.roles_of(insp, user, is_admin)
    can = {op: _perm.can(op, roles, auth_on) for op in ("finding_edit", "plan_edit", "mark_fixed", "mark_verified", "approve")}
    return jsonify(inspection=insp, summary=metrics.summary(insp), can=can, **extra), status


def _renumber(existing: list[dict], new: list[dict]) -> list[dict]:
    """新しい指摘に既存と重ならない F 番号を振る（元の dict は変えない）。"""
    nums = [int(f["id"][1:]) for f in existing if str(f.get("id", "")).startswith("F") and f["id"][1:].isdigit()]
    start = max(nums, default=0)
    from web.services.docverify.store import upgrade_finding
    return [upgrade_finding({**f, "id": f"F{start + i + 1}"}) for i, f in enumerate(new)]


def _denied(op: str, insp: dict | None = None):
    """役割×操作の表（perm.MATRIX）で拒否なら 403 応答、許可なら None。R4 と同じ判定を R1 の更新系にも掛ける。"""
    msg = _perm.check(op, insp)
    return (jsonify(error=msg, code="forbidden"), 403) if msg else None


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


@bp.route("/docverify")
def page() -> str:
    # 静的ファイルの更新が古い版の読み込みで隠れないよう、JS/CSS の更新時刻を URL に付ける
    static = Path(__file__).resolve().parents[2] / "static"
    files = ["js/docverify-core.js", "js/docverify-global.js", "js/docverify-review.js", "js/docverify-viewpoints.js", "css/docverify.css", "js/docverify-accuracy.js", "js/docverify-ai.js", "js/docverify-process.js", "css/docverify-process.css", "js/docverify-trace.js", "js/docverify-trace-docs.js", "js/docverify-trace-check.js", "js/docverify-trace-report.js", "css/docverify-trace.css", "css/docverify-trace-docs.css", "css/docverify-trace-check.css", "css/docverify-trace-report.css", "js/docassure.js", "css/docassure.css", "js/docassure-trace-panel.js", "js/docassure-diff-panel.js", "js/docassure-review-panel.js", "css/docassure-trace-panel.css", "css/docassure-panels.css", "js/docassure-links-panel.js", "css/docassure-links-panel.css"]
    dv_ver = max(int((static / f).stat().st_mtime) for f in files if (static / f).exists())
    return render_template("doc_verify.html", dv_ver=dv_ver)


@bp.route("/api/docverify/inspections", methods=["GET"])
def list_inspections():
    from web.services.docverify import store
    try:
        return jsonify(inspections=store.list_all())
    except Exception:
        log.exception("検査一覧の取得に失敗")
        return _err("検査一覧を読めませんでした。時間をおいて再読み込みしてください。", 500)


@bp.route("/api/docverify/inspections", methods=["POST"])
def create_inspection():
    from web.services.docverify import store
    body = request.get_json(silent=True) or {}
    name = str(body.get("name") or "").strip()
    if not name:
        return _err("検査の名前を入力してください。", 400)
    try:
        from web.services.docverify.settings import current_user
        # 作った人を進行役として参加者に入れる（入れないと「あなたの役割: 未登録」になる）
        insp = {**store.new(name), "goal": str(body.get("goal") or "").strip(),
                "participants": [{"name": current_user(), "role": "moderator", "done": False}]}
        store.save(insp)  # 目的が空でも必ず保存する（空のとき保存せず、直後の読み込みが 404 になっていた）
    except Exception:
        log.exception("検査の作成に失敗")
        return _err("検査を作れませんでした。もう一度お試しください。", 500)
    return _respond(insp, 201)


@bp.route("/api/docverify/inspections/<iid>", methods=["GET"])
def get_inspection(iid: str):
    insp, err = _load(iid)
    return err or _respond(insp)


@bp.route("/api/docverify/inspections/<iid>/document", methods=["POST"])
@_perm.require("import_doc")
def upload_document(iid: str):
    from web.services.docverify import checks, diff, ingest, setcheck, store
    insp, err = _load(iid)
    if err:
        return err
    file = request.files.get("file")
    if file is None or not file.filename:
        return _err("文書ファイルを選んでください。", 400)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            data = file.read()
            document, passages = ingest.ingest(file.filename, data, Path(tmp))
    except ingest.IngestError as e:
        return _err(str(e), 400)
    except Exception:
        log.exception("文書の取り込みに失敗")
        return _err("文書を読めませんでした。別の形式で保存し直してから取り込んでください。", 500)

    old_passages = insp.get("passages") or []
    old_findings = insp.get("findings") or []
    version = len(insp.get("versions") or []) + 1
    document = {**document, "version": version, "sha256": hashlib.sha256(data).hexdigest()}
    try:
        if insp.get("document") is None:
            findings = _renumber([], setcheck.apply_rules(checks.candidates(passages), passages, setcheck.load_settings()))
            changes = None
        else:
            changes = diff.compare(old_passages, passages)
            carried = diff.carry_findings(old_findings, old_passages, passages)
            old_texts = {_norm(p["text"]) for p in old_passages}
            fresh = [p for p in passages if _norm(p["text"]) not in old_texts]
            findings = carried + _renumber(carried, setcheck.apply_rules(checks.candidates(fresh), fresh, setcheck.load_settings()))
    except Exception:
        log.exception("指摘候補の生成に失敗")
        return _err("指摘の候補を作れませんでした。もう一度取り込んでください。", 500)

    from datetime import datetime, timezone

    from web.services.docverify import metrics
    versions = metrics.freeze_current(insp)  # 旧の断片・指摘で前の版のスコアを確定する
    # document は ingest の unread（読めなかった要素の数）をそのまま持つ
    base = {**insp, "document": document, "passages": passages, "findings": findings, "diff": changes,
            "status": "reviewing"}
    # 文書を取り込んだら個別レビューへ進める（計画のままだと工程表示が実態と合わない）。
    # R4 の種別が設定済みなら入口基準（FR-06-142）を満たすときだけ進める。旧形式は従来どおり進める。
    from web.services.docverify import process
    in_plan = insp.get("phase", "plan") == "plan"
    entry_errs = process.entry_errors(base, "individual") if in_plan and not process.type_info(insp)["legacy"] else []
    base = {**base, "phase": "individual" if in_plan and not entry_errs else insp.get("phase", "plan")}
    entry = {"version": version, "name": document.get("name"),
             "uploaded_at": datetime.now(timezone.utc).isoformat(), "passages": len(passages),
             "quality": metrics.quality_brief(base, False)}
    updated = {**base, "versions": [*versions, entry]}
    store.save(updated)
    return _respond(updated, **({"entry_errors": entry_errs} if entry_errs else {}))


@bp.route("/api/docverify/inspections/<iid>/findings/<fid>", methods=["POST"])
def update_finding(iid: str, fid: str):
    from web.services.docverify import store
    insp, err = _load(iid)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    op = {"fixed": "mark_fixed", "verified": "mark_verified"}.get(str(body.get("status") or ""), "finding_edit")
    denied = _denied(op, insp)
    if denied:
        return denied
    changes = {}
    if "status" in body:
        if body["status"] not in _STATUSES:
            return _err("指摘の状態が正しくありません。画面を再読み込みしてやり直してください。", 400)
        changes["status"] = body["status"]
    if "severity" in body:
        from web.services.docverify.settings import normalize_severity
        sev = normalize_severity(body["severity"])
        if sev not in _SEVERITIES:
            return _err("重大度を選び直してください。", 400)
        changes["severity"] = sev
    if "certainty" in body:  # 「作成者に質問」で要確認にする（質問票に載る）
        if body["certainty"] not in ("事実", "推定", "要確認"):
            return _err("確度を選び直してください。", 400)
        changes["certainty"] = body["certainty"]
    for key in ("checklist_item", "disposition"):
        if key in body:
            v = body[key]
            if v is not None and not isinstance(v, str):
                return _err("入力の形が正しくありません。画面を再読み込みしてやり直してください。", 400)
            changes[key] = (v.strip() or None) if isinstance(v, str) else None
    if not changes:
        return _err("変更する項目がありません。画面を再読み込みしてやり直してください。", 400)
    if not any(f.get("id") == fid for f in insp.get("findings") or []):
        return _err("指摘が見つかりません。画面を再読み込みしてください。", 404)
    findings = [{**f, **changes} if f.get("id") == fid else f for f in insp["findings"]]
    updated = {**insp, "findings": findings}
    store.save(updated)
    _perm.record("finding_update", f"{iid}/{fid}", changes)
    return _respond(updated)


@bp.route("/api/docverify/inspections/<iid>/findings", methods=["POST"])
@_perm.require("finding_edit")
def add_finding(iid: str):
    from web.services.docverify import store
    insp, err = _load(iid)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    pid = body.get("passage_id")
    passage = next((p for p in insp.get("passages") or [] if p.get("id") == pid), None)
    if passage is None:
        return _err("指摘する箇所を選んでください。", 400)
    from web.services.docverify.settings import current_user, normalize_severity
    severity = normalize_severity(body.get("severity"))
    if severity not in _SEVERITIES:
        return _err("重大度を選んでください。", 400)
    message = str(body.get("message") or "").strip()
    viewpoint = str(body.get("viewpoint") or "").strip()
    if not message or not viewpoint:
        return _err("観点と指摘の文を入力してください。", 400)
    new = _renumber(insp.get("findings") or [], [{
        "rule": "HUMAN", "severity": severity, "viewpoint": viewpoint, "message": message,
        "location": passage.get("location"), "passage_id": pid, "quote": passage.get("text", "")[:200],
        "certainty": "事実", "status": "adopted", "answer": None, "origin": "human",
        "raised_by": current_user(), "checklist_item": (str(body.get("checklist_item")).strip() or None)
        if body.get("checklist_item") else None, "disposition": None}])
    updated = {**insp, "findings": [*(insp.get("findings") or []), *new]}
    store.save(updated)
    _perm.record("finding", f"{iid}/{new[0]['id']}", {"status": new[0].get("status")})
    return _respond(updated, 201)


@bp.route("/api/docverify/inspections/<iid>/questions.csv")
def questions_csv(iid: str):
    from web.services.docverify import questions
    insp, err = _load(iid)
    if err:
        return err
    text = questions.to_csv(questions.build(insp.get("findings") or []))
    return Response(text, mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=questions-{iid}.csv"})


@bp.route("/api/docverify/inspections/<iid>/questions.xlsx")
def questions_xlsx(iid: str):
    from web.services.docverify import questions
    insp, err = _load(iid)
    if err:
        return err
    data = questions.to_xlsx(questions.build(insp.get("findings") or []))
    return Response(data, mimetype=_XLSX,
                    headers={"Content-Disposition": f"attachment; filename=questions-{iid}.xlsx"})


@bp.route("/api/docverify/inspections/<iid>/answers", methods=["POST"])
@_perm.require("finding_edit")
def import_answers(iid: str):
    from web.services.docverify import questions, store
    insp, err = _load(iid)
    if err:
        return err
    file = request.files.get("file")
    if file is None or not file.filename:
        return _err("回答を書き込んだ CSV ファイルを選んでください。", 400)
    try:
        text = file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        return _err("CSV を読めませんでした。UTF-8 で保存し直してから取り込んでください。", 400)
    updated = {**insp, "findings": [dict(f) for f in insp.get("findings") or []]}
    try:
        applied = questions.import_answers(updated, text)
    except ValueError as e:
        return _err(str(e) or "CSV の形が違います。出力した質問票に回答を書き込んで取り込んでください。", 400)
    except Exception:
        log.exception("回答の取り込みに失敗")
        return _err("回答を取り込めませんでした。出力した質問票に回答を書き込んで取り込んでください。", 400)
    store.save(updated)
    return _respond(updated, applied=applied)


@bp.route("/api/docverify/domains")
def domains():
    from web.services.docverify import match
    try:
        return jsonify(domains=match.domains())
    except Exception:
        log.exception("巡回済みサイトの取得に失敗")
        return _err("巡回済みのサイトを読めませんでした。時間をおいて再読み込みしてください。", 500)


@bp.route("/api/docverify/inspections/<iid>/match", methods=["POST"])
def match_screens(iid: str):
    from web.services.docverify import match, store
    insp, err = _load(iid)
    if err:
        return err
    denied = _denied("finding_edit", insp)
    if denied:
        return denied
    domain = str((request.get_json(silent=True) or {}).get("domain") or "").strip()
    if not domain:
        return _err("照合するサイトを選んでください。", 400)
    try:
        found = match.match(insp.get("passages") or [], domain)
    except ValueError:
        return _err("まず System 01 で対象サイトを巡回してください。", 400)
    except Exception:
        log.exception("実画面との照合に失敗")
        return _err("照合できませんでした。もう一度お試しください。", 500)
    viewpoints = {f.get("viewpoint") for f in found}
    kept = [f for f in insp.get("findings") or []
            if not (f.get("status") == "candidate" and f.get("viewpoint") in viewpoints)]
    updated = {**insp, "findings": kept + _renumber(insp.get("findings") or [], found)}
    store.save(updated)
    return _respond(updated)


@bp.route("/api/docverify/inspections/<iid>/close", methods=["POST"])
@_perm.require("plan_edit")
def close(iid: str):
    from web.services.docverify import metrics, store
    insp, err = _load(iid)
    if err:
        return err
    summary = metrics.summary(insp)
    if not summary.get("exit_ok"):
        return jsonify(error="終了条件を満たしていません。理由を確認して対応してください。",
                       reasons=summary.get("reasons", [])), 409
    updated = {**insp, "status": "closed", "versions": metrics.freeze_current(insp)}
    store.save(updated)
    return _respond(updated)


@bp.route("/api/docverify/inspections/<iid>/report.xlsx")
def report_xlsx(iid: str):
    from web.services.docverify import metrics
    insp, err = _load(iid)
    if err:
        return err
    try:
        data = metrics.to_xlsx(insp)
    except Exception:
        log.exception("報告の作成に失敗")
        return _err("報告を作れませんでした。もう一度出力してください。", 500)
    return Response(data, mimetype=_XLSX,
                    headers={"Content-Disposition": f"attachment; filename=inspection-{iid}.xlsx"})


# ---- v2 追補 ----------------------------------------------------------------

def _all_full() -> list[dict]:
    """全レビューを指摘・断片込みで読む（壊れたものは飛ばす）。"""
    from web.services.docverify import store
    out = []
    for item in store.list_all():
        try:
            out.append(store.load(item["id"]))
        except (KeyError, ValueError, OSError):
            continue
    return out


@bp.route("/api/docverify/home")
def home():
    from web.services.docverify import home as home_svc
    from web.services.docverify.settings import current_user
    try:
        return jsonify(home_svc.build(_all_full(), current_user()))
    except Exception:
        log.exception("ホームの取得に失敗")
        return _err("ホームを読めませんでした。時間をおいて再読み込みしてください。", 500)


@bp.route("/api/docverify/findings")
def all_findings():
    status, severity, review = (request.args.get(k) or "" for k in ("status", "severity", "review"))
    from web.services.docverify.settings import normalize_severity
    severity = normalize_severity(severity)
    try:
        reviews = _all_full()
    except Exception:
        log.exception("指摘一覧の取得に失敗")
        return _err("指摘一覧を読めませんでした。時間をおいて再読み込みしてください。", 500)
    rows = [{**f, "review_id": r["id"], "review_name": r.get("name")}
            for r in reviews if not review or r["id"] == review
            for f in r.get("findings") or []
            if (not status or f.get("status") == status) and (not severity or f.get("severity") == severity)]
    return jsonify(findings=rows)


def _valid_participants(value):
    if not isinstance(value, list):
        return None
    out = []
    for p in value:
        if not isinstance(p, dict) or not str(p.get("name") or "").strip() or p.get("role") not in _ROLES:
            return None
        out.append({"name": str(p["name"]).strip(), "role": p["role"], "done": bool(p.get("done"))})
    return out


@bp.route("/api/docverify/inspections/<iid>", methods=["PATCH"])
def patch_inspection(iid: str):
    from web.services.docverify import store
    insp, err = _load(iid)
    if err:
        return err
    body = request.get_json(silent=True)
    if isinstance(body, dict):
        ops = (["approve"] if "approval" in body else []) + (["plan_edit"] if set(body) - {"approval"} else [])
        for op in ops:
            denied = _denied(op, insp)
            if denied:
                return denied
    if not isinstance(body, dict):
        return _err("入力の形が正しくありません。画面を再読み込みしてやり直してください。", 400)
    changes = {}
    for key in ("name", "goal"):
        if key in body:
            v = str(body[key] or "").strip()
            if key == "name" and not v:
                return _err("レビューの名前を入力してください。", 400)
            changes[key] = v
    if "due" in body:
        due = body["due"] or None
        if due is not None and not (isinstance(due, str) and _DATE.match(due)):
            return _err("期限は年-月-日の形で入力してください。", 400)
        changes["due"] = due
    if "participants" in body:
        ps = _valid_participants(body["participants"])
        if ps is None:
            return _err("参加者の名前と役割を入力してください。", 400)
        changes["participants"] = ps
    if "checklist_id" in body:
        cid = body["checklist_id"] or None
        if cid is not None:
            from web.services.docverify.settings import load_checklists
            if cid not in {c.get("id") for c in load_checklists()}:
                return _err("観点チェックリストを選び直してください。", 400)
        changes["checklist_id"] = cid
    if "checks" in body:
        if not isinstance(body["checks"], dict):
            return _err("チェックの形が正しくありません。画面を再読み込みしてやり直してください。", 400)
        changes["checks"] = {str(k): bool(v) for k, v in body["checks"].items()}
    if "exit_criteria" in body:
        ec = body["exit_criteria"]
        if not isinstance(ec, dict) or not all(isinstance(v, int) and v >= 0 for v in ec.values()):
            return _err("終了条件の件数は 0 以上の整数で入力してください。", 400)
        changes["exit_criteria"] = {**(insp.get("exit_criteria") or {}), **ec}
    if "phase" in body:
        if body["phase"] not in _PHASES:
            return _err("工程が正しくありません。画面を再読み込みしてやり直してください。", 400)
        changes["phase"] = body["phase"]
        if body["phase"] == "closed":
            changes["status"] = "closed"
    if "approval" in body:
        # 承認欄は人が入れた値を保存するだけ。サーバは自動で埋めない。
        ap = body["approval"]
        if not isinstance(ap, dict) or not all(v is None or isinstance(v, str) for v in ap.values()):
            return _err("承認者の名前と日時を入力してください。", 400)
        changes["approval"] = {"approver": (ap.get("approver") or "").strip() or None,
                               "decided_at": (ap.get("decided_at") or "").strip() or None,
                               "doc_version": (insp.get("document") or {}).get("version")}
    if not changes:
        return _err("変更する項目がありません。画面を再読み込みしてやり直してください。", 400)
    updated = {**insp, **changes}
    store.save(updated)
    if "approval" in changes:
        _perm.record("approval", iid, {"status": "approved" if changes["approval"]["approver"] else None,
                                       **changes["approval"]})
    return _respond(updated)


@bp.route("/api/docverify/inspections/<iid>/participants/me/done", methods=["POST"])
def participant_done(iid: str):
    from web.services.docverify import store
    from web.services.docverify.settings import current_user
    insp, err = _load(iid)
    if err:
        return err
    me = current_user()
    ps = insp.get("participants") or []
    if not any(p.get("name") == me for p in ps):
        return _err("このレビューの参加者に入っていません。計画の画面で参加者に追加してください。", 403)
    updated = {**insp, "participants": [{**p, "done": True} if p.get("name") == me else p for p in ps]}
    store.save(updated)
    return _respond(updated)


@bp.route("/api/docverify/viewpoints", methods=["GET", "PUT"])
def viewpoints():
    if request.method != "GET":
        denied = _denied("tenant_settings")
        if denied:
            return denied
    from web.services.docverify import viewpoints as vp
    try:
        if request.method == "PUT":
            vp.update(request.get_json(silent=True))
        return jsonify(viewpoints=vp.load(), scopes=[
            {"id": i, "name": n, "test": t, "desc": d} for i, n, t, d in vp.SCOPES],
            accuracy_note=vp.ACCURACY_NOTE)
    except ValueError as e:
        return _err(str(e), 400)
    except Exception:
        log.exception("検証観点の読み書きに失敗")
        return _err("検証観点を読み書きできませんでした。時間をおいてやり直してください。", 500)


@bp.route("/api/docverify/viewpoints/export", methods=["GET"])
def viewpoints_export():
    from web.services.docverify import viewpoints as vp
    try:
        resp = Response(vp.export_csv(), mimetype="text/csv")
        resp.headers["Content-Disposition"] = (
            "attachment; filename=\"viewpoints.csv\"; filename*=UTF-8''%E6%A4%9C%E8%A8%BC%E8%A6%B3%E7%82%B9.csv")
        return resp
    except Exception:
        log.exception("検証観点の書き出しに失敗")
        return _err("書き出せませんでした。時間をおいてやり直してください。", 500)


@bp.route("/api/docverify/viewpoints/import", methods=["POST"])
def viewpoints_import():
    if request.method != "GET":
        denied = _denied("tenant_settings")
        if denied:
            return denied
    from web.services.docverify import viewpoints as vp
    f = request.files.get("file")
    if not f or not f.filename:
        return _err("ファイルが選ばれていません。Excel か CSV を選んでください。", 400)
    try:
        data = f.read(vp.MAX_BYTES + 1)
        if request.form.get("commit") == "1":
            return jsonify(vp.commit(f.filename, data, request.form.get("overwrite") == "1"))
        res = vp.parse(f.filename, data)
        res.pop("items")
        res["file"] = f.filename
        return jsonify(res)
    except ValueError as e:
        return _err(str(e), 400)
    except Exception:
        log.exception("検証観点の取り込みに失敗")
        return _err("取り込めませんでした。ファイルを確かめてやり直してください。", 500)


@bp.route("/api/docverify/checklists", methods=["GET", "PUT"])
def checklists():
    if request.method != "GET":
        denied = _denied("tenant_settings")
        if denied:
            return denied
    from web.services.docverify import settings
    try:
        if request.method == "GET":
            return jsonify(checklists=settings.load_checklists())
        return jsonify(checklists=settings.save_checklists(request.get_json(silent=True)))
    except ValueError as e:
        return _err(str(e), 400)
    except Exception:
        log.exception("チェックリストの読み書きに失敗")
        return _err("チェックリストを保存できませんでした。もう一度お試しください。", 500)


@bp.route("/api/docverify/settings", methods=["GET", "PUT"])
def settings_api():
    if request.method != "GET":
        denied = _denied("tenant_settings")
        if denied:
            return denied
    from web.services.docverify import settings
    try:
        if request.method == "GET":
            return jsonify(settings=settings.load_settings())
        return jsonify(settings=settings.save_settings(request.get_json(silent=True)))
    except ValueError as e:
        return _err(str(e), 400)
    except Exception:
        log.exception("設定の読み書きに失敗")
        return _err("設定を保存できませんでした。もう一度お試しください。", 500)


@bp.route("/api/docverify/metrics")
def metrics_api():
    from web.services.docverify import metrics
    try:
        return jsonify(metrics=metrics.overall(_all_full()))
    except Exception:
        log.exception("メトリクスの集計に失敗")
        return _err("メトリクスを集計できませんでした。時間をおいて再読み込みしてください。", 500)
