"""ドキュメント検証 R2（System 06）: AI の説明・送信前確認・採否・質問票へ送る・送信先設定・監査ログ。

契約: docs/sdlc/20_design/WS2D-DD-006_詳細設計書_System06_R2.md 5 章。処理の中身は web/services/docverify/ にある。
LLM が失敗しても規則の検出・仕分け・判定（既存の API）には影響しない（FR-06-115・NFR-06-13）。
"""
from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request

from web.services.docverify import audit, llm_assist, llm_settings

bp = Blueprint("doc_verify_ai", __name__)
log = logging.getLogger(__name__)

_IID = re.compile(r"^[0-9a-f]{12}$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CONSENT_TTL_SEC = 600

M_NONE = "AI の説明は使わない設定です。テナント管理者が設定で送信先を選ぶと使えます。"
M_NO_KEY = "OpenAI のキーが設定されていません。管理者にキーの設定を依頼してください。規則の指摘はそのまま使えます。"
M_FAIL = "AI の説明を作れませんでした。規則の指摘はそのまま使えます。時間をおいてもう一度試してください。"
M_TIMEOUT = ("AI の説明を作れませんでした（60 秒以内に返りませんでした）。規則の指摘はそのまま使えます。"
             "時間をおいてもう一度試してください。")
M_CANCEL = "AI の説明を取りやめました。規則の指摘はそのまま使えます。"
M_CONSENT = "送信の確認が切れました。「AI の説明を見る」からやり直してください。"
M_NOT_FOUND = "指摘が見つかりません。画面を再読み込みしてください。"
M_INSP = "検査が見つかりません。検査一覧から開き直してください。"
M_NO_AI = "AI の提案がまだありません。先に「AI の説明を見る」を押してください。"
M_DECISION = "採用か不採用を選んでください。"
M_PICK = "質問票に送る事項を選んでください。"
M_AUDIT_DENY = "監査ログを見る権限がありません。テナント管理者か承認者に依頼してください。"
M_SAVE_FAIL = "設定を保存できませんでした。もう一度保存してください。"

_consents: dict[str, dict] = {}
_running: dict[str, threading.Event] = {}
_lock = threading.Lock()


def _err(message: str, status: int):
    return jsonify(error=message), status


def _me() -> str:
    from web.services.docverify.settings import current_user
    return current_user()


def _auth_user():
    from web.tenancy import current_auth_user
    return current_auth_user()


def is_admin() -> bool:
    """認証オフ（ログイン利用者なし）は全操作を許可する（RD-006 8.2 注記）。"""
    u = _auth_user()
    return u is None or u.get("role") == "admin"


def is_approver() -> bool:
    from web.services.docverify import store
    me = _me()
    return any(p.get("role") == "approver" and p.get("name") == me
               for s in store.list_all() for p in (s.get("participants") or []))


def _load(iid: str):
    from web.services.docverify import store
    if not _IID.match(iid or ""):
        return None, _err(M_INSP, 404)
    try:
        return store.load(iid), None
    except KeyError:
        return None, _err(M_INSP, 404)


def _finding(insp: dict, fid: str):
    return next((f for f in insp.get("findings") or [] if f.get("id") == fid), None)


def _respond(insp: dict, status: int = 200, **extra):
    from web.services.docverify import metrics
    return jsonify(inspection=insp, summary=metrics.summary(insp), **extra), status


def _replace_finding(insp: dict, fid: str, fn) -> dict:
    return {**insp, "findings": [fn(f) if f.get("id") == fid else f for f in insp.get("findings") or []]}


def _destination(cfg: dict) -> dict:
    key = cfg["destination"]
    model = cfg.get(f"{key}_model") if key != "none" else None
    return {"key": key, "model": model, **llm_settings.disclosures()[key]}


@bp.route("/api/docverify/r2/llm-settings")
def get_settings():
    cfg = llm_settings.load()
    return jsonify(settings=cfg, destination=_destination(cfg), disclosures=llm_settings.disclosures(),
                   can_edit=is_admin())


@bp.route("/api/docverify/r2/llm-settings", methods=["POST"])
def post_settings():
    if not is_admin():
        return _err(llm_settings.NOT_ADMIN, 403)
    try:
        cfg = llm_settings.save(request.get_json(silent=True) or {})
    except (ValueError, ConnectionError) as exc:
        return _err(str(exc), 400)
    except OSError:
        log.exception("llm settings save failed")
        return _err(M_SAVE_FAIL, 500)
    audit.append("llm_settings", _me(), "設定", {"destination": cfg["destination"]})
    return jsonify(settings=cfg, destination=_destination(cfg), disclosures=llm_settings.disclosures(),
                   can_edit=True)


def _sweep(now: float) -> None:
    for k in [k for k, v in _consents.items() if v["expires"] < now]:
        _consents.pop(k, None)


@bp.route("/api/docverify/r2/inspections/<iid>/findings/<fid>/ai/preview", methods=["POST"])
def preview(iid: str, fid: str):
    """送信前確認（SCR-06-11・FR-06-112）。ここでは送らない。承諾の印として同意トークンを返す。"""
    insp, err = _load(iid)
    if err:
        return err
    finding = _finding(insp, fid)
    if finding is None:
        return _err(M_NOT_FOUND, 404)
    cfg = llm_settings.load()
    if cfg["destination"] == "none":
        return _err(M_NONE, 409)
    body = request.get_json(silent=True) or {}
    original = llm_assist.source_text(insp, finding)
    try:
        extra = [*(body.get("extra_masks") or []), *llm_assist.word_ranges(original, body.get("extra_words"))]
        masked = llm_assist.mask(original, extra)
    except ValueError as exc:
        return _err(str(exc), 400)
    with_wobble = bool(body.get("with_wobble"))
    token = secrets.token_urlsafe(24)
    now = time.time()
    with _lock:
        _sweep(now)
        _consents[token] = {"iid": iid, "fid": fid, "masked": masked["text"], "destination": cfg["destination"],
                            "with_wobble": with_wobble, "user": _me(), "expires": now + CONSENT_TTL_SEC}
    return jsonify(destination=_destination(cfg), masked=masked, sends=llm_assist.sends_for(with_wobble),
                   with_wobble=with_wobble, consent_token=token, expires_in=CONSENT_TTL_SEC,
                   timeout_sec=int(llm_assist.TIMEOUT_SEC))


def _take_consent(token: str, iid: str, fid: str, cfg: dict):
    with _lock:
        _sweep(time.time())
        c = _consents.pop(str(token or ""), None)
    ok = c and c["iid"] == iid and c["fid"] == fid and c["destination"] == cfg["destination"] and c["user"] == _me()
    return c if ok else None


def _run_explain(client, consent: dict, token: str):
    event = threading.Event()
    with _lock:
        _running[token] = event
    try:
        return llm_assist.explain(client, consent["masked"], with_wobble=consent["with_wobble"], cancel=event), None
    except llm_assist.AssistCancelled:
        return None, ("cancelled", M_CANCEL, 409)
    except llm_assist.AssistTimeout:
        return None, ("timeout", M_TIMEOUT, 504)
    except llm_assist.AssistError as exc:
        log.warning("docverify explain failed: %s", exc)
        return None, ("failed", M_FAIL, 503)
    finally:
        with _lock:
            _running.pop(token, None)


@bp.route("/api/docverify/r2/inspections/<iid>/findings/<fid>/ai/explain", methods=["POST"])
def explain(iid: str, fid: str):
    """承諾済みの同意トークンで 1 回だけ送る（FR-06-110・112・115、NFR-06-11）。"""
    from web.services.docverify import store
    insp, err = _load(iid)
    if err:
        return err
    if _finding(insp, fid) is None:
        return _err(M_NOT_FOUND, 404)
    cfg = llm_settings.load()
    if cfg["destination"] == "none":
        return _err(M_NONE, 409)
    token = (request.get_json(silent=True) or {}).get("consent_token")
    consent = _take_consent(token, iid, fid, cfg)
    if consent is None:
        return _err(M_CONSENT, 400)
    client = llm_settings.client_for(cfg)
    if client is None:
        return _err(M_NO_KEY, 503)
    ai, failure = _run_explain(client, consent, token)
    detail = {"provider": client.name, "model": client.model, "chars": len(consent["masked"]),
              "masked": consent["masked"].count("］"), "sends": llm_assist.sends_for(consent["with_wobble"])}
    if failure:
        audit.append("llm_send_failed", _me(), f"{iid}/{fid}", {**detail, "outcome": failure[0]})
        return _err(failure[1], failure[2])
    audit.append("llm_send", _me(), f"{iid}/{fid}", {**detail, "outcome": "ok"})
    fresh, err = _load(iid)  # 待っている間の他の更新を消さないよう読み直す
    if err:
        return err
    updated = _replace_finding(fresh, fid, lambda f: {**f, "ai": ai})
    store.save(updated)
    return _respond(updated, 200, ai=ai)


@bp.route("/api/docverify/r2/ai/cancel", methods=["POST"])
def cancel():
    token = str((request.get_json(silent=True) or {}).get("consent_token") or "")
    with _lock:
        event = _running.get(token)
        pending = _consents.pop(token, None)
    if event is not None:
        event.set()
    return jsonify(cancelled=bool(event is not None or pending))


@bp.route("/api/docverify/r2/inspections/<iid>/findings/<fid>/ai/decision", methods=["POST"])
def decision(iid: str, fid: str):
    """採否（FR-06-114）。採用は対応結果に案を入れるだけで、元の文書・断片は変えない（FR-06-118）。"""
    from web.services.docverify import store
    insp, err = _load(iid)
    if err:
        return err
    finding = _finding(insp, fid)
    if finding is None:
        return _err(M_NOT_FOUND, 404)
    if not isinstance(finding.get("ai"), dict):
        return _err(M_NO_AI, 400)
    choice = (request.get_json(silent=True) or {}).get("decision")
    if choice not in ("adopt", "reject"):
        return _err(M_DECISION, 400)
    stamp = {"adopted": choice == "adopt", "decided_by": _me(),
             "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    def apply(f: dict) -> dict:
        out = {**f, "ai": {**f["ai"], **stamp}}
        return {**out, "disposition": f"AI 提案を採用: {f['ai'].get('rewrite') or ''}"} if choice == "adopt" else out
    updated = _replace_finding(insp, fid, apply)
    store.save(updated)
    audit.append("ai_adopt" if choice == "adopt" else "ai_reject", _me(), f"{iid}/{fid}",
                 {"provider": finding["ai"].get("provider"), "model": finding["ai"].get("model")})
    return _respond(updated)


def _question_findings(insp: dict, finding: dict, picked: list[str]) -> list[dict]:
    from web.services.docverify.store import upgrade_finding
    nums = [int(f["id"][1:]) for f in insp.get("findings") or [] if str(f.get("id", ""))[1:].isdigit()]
    start = max(nums, default=0)
    return [upgrade_finding({
        "id": f"F{start + i + 1}", "rule": "AI_QUESTION", "severity": "minor", "viewpoint": "未決定事項",
        "message": q, "location": finding.get("location"), "passage_id": finding.get("passage_id"),
        "quote": finding.get("quote") or "", "certainty": "要確認", "status": "candidate", "answer": None,
        "origin": "ai", "raised_by": f"AI の提案（選んだ人: {_me()}）", "source_finding": finding.get("id"),
        "checklist_item": None, "disposition": None}) for i, q in enumerate(picked)]


@bp.route("/api/docverify/r2/inspections/<iid>/findings/<fid>/ai/questions", methods=["POST"])
def to_questions(iid: str, fid: str):
    """人が選んだ未決定事項を、要確認の候補として足す（質問票に載る。FR-06-117）。"""
    from web.services.docverify import store
    insp, err = _load(iid)
    if err:
        return err
    finding = _finding(insp, fid)
    if finding is None:
        return _err(M_NOT_FOUND, 404)
    ai = finding.get("ai")
    if not isinstance(ai, dict):
        return _err(M_NO_AI, 400)
    qs, sent = ai.get("open_questions") or [], set(ai.get("sent_questions") or [])
    idx = (request.get_json(silent=True) or {}).get("indexes")
    if not isinstance(idx, list) or not idx or not all(isinstance(i, int) and 0 <= i < len(qs) for i in idx):
        return _err(M_PICK, 400)
    new_idx = sorted({i for i in idx if i not in sent})
    added = _question_findings(insp, finding, [qs[i] for i in new_idx])
    marked = _replace_finding(insp, fid, lambda f: {**f, "ai": {**f["ai"], "sent_questions": sorted(sent | set(new_idx))}})
    updated = {**marked, "findings": [*marked["findings"], *added]}
    store.save(updated)
    for f in added:
        audit.append("ai_question", _me(), f"{iid}/{f['id']}", {"question": f["message"][:80]})
    return _respond(updated, 201, added=[f["id"] for f in added])


def _audit_rows():
    args = request.args
    since, until = args.get("since", ""), args.get("until", "")
    if (since and not _DATE.match(since)) or (until and not _DATE.match(until)):
        return None, _err("期間は年-月-日の形で入力してください。", 400)
    action = args.get("action", "")
    if action and action not in audit.ACTIONS:
        return None, _err("操作を一覧から選んでください。", 400)
    return audit.query(since, until, args.get("user", "").strip(), action), None


@bp.route("/api/docverify/r2/audit")
def audit_list():
    if not (is_admin() or is_approver()):
        return _err(M_AUDIT_DENY, 403)
    rows, err = _audit_rows()
    if err:
        return err
    everyone = audit.read_all()
    return jsonify(rows=[{**r, "action_label": audit.ACTIONS.get(r.get("action"), r.get("action")),
                          "summary": audit.describe(r)} for r in rows],
                   users=sorted({r.get("user", "") for r in everyone}), actions=audit.ACTIONS)


@bp.route("/api/docverify/r2/audit.csv")
def audit_csv():
    if not (is_admin() or is_approver()):
        return _err(M_AUDIT_DENY, 403)
    rows, err = _audit_rows()
    if err:
        return err
    return Response(audit.to_csv(rows), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=audit.csv"})
