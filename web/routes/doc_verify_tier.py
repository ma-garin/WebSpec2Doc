"""System 06 トレーサビリティ（格ベース）API。契約: work/tier-contract.md。"""
from __future__ import annotations

import logging
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, jsonify, request

log = logging.getLogger(__name__)
bp = Blueprint("doc_verify_tier", __name__)

_IID = re.compile(r"^[0-9a-f]{12}$")
_P = "/api/docverify/inspections/<iid>/tier"
NOT_FOUND = "検査が見つかりません。検査を選び直してください。"
SAVE_ERR = "保存できませんでした。もう一度お試しください。"
LOW = 0.6
_EXTS = (".md", ".docx", ".xlsx")


def _err(message: str, status: int):
    return jsonify(error=message), status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(iid: str):
    from web.services.docverify import store
    if not _IID.match(iid or ""):
        return None, _err(NOT_FOUND, 404)
    try:
        return store.load(iid), None
    except KeyError:
        return None, _err(NOT_FOUND, 404)


def _tier(insp: dict) -> dict:
    t = insp.get("tier") or {}
    return {"documents": list(t.get("documents") or []), "approved": t.get("approved"),
            "findings": list(t.get("findings") or []), "reports": dict(t.get("reports") or {}),
            "conclusion": t.get("conclusion")}


def _step(t: dict):
    if t["conclusion"]:
        return "done"
    return 2 if t["approved"] else 1


def _state(insp: dict) -> dict:
    from web.services.docverify.tierflow import links, rules, tiers
    t = _tier(insp)
    step = _step(t)
    s2 = step == 2 or step == "done"
    state = {
        "step": step,
        "documents": [{k: v for k, v in d.items() if k not in ("passages", "prev_passages")} for d in t["documents"]],
        "documents_text": ({d["id"]: [{"id": p.get("id"), "text": p.get("text", "")} for p in d.get("passages") or []]
                            for d in t["documents"]} if s2 else {}),
        "tiers": [{"id": i, "label": lb, "hint": tiers.TIER_HINT[i]} for i, lb in tiers.TIERS],
        "low": LOW, "approved": t["approved"], "findings": t["findings"], "reports": t["reports"],
        "rules": [{"id": i, "label": lb} for i, lb in rules.RULES],
        "conclusion": t["conclusion"],
    }
    if s2:
        auto = links.conclude(t["findings"], t["reports"])
        state.update(links=links.build(t["documents"], t["findings"], t["reports"]), auto_level=auto,
                     auto_note=links.note(t["documents"]), level_label=links.LEVEL_LABEL)
    else:
        state["level_label"] = links.LEVEL_LABEL
    return state


def _save(insp: dict, t: dict, status: int = 200):
    from web.services.docverify import store
    try:
        store.save({**insp, "tier": t})
        return jsonify(**_state({**insp, "tier": t})), status
    except Exception:
        log.exception("トレーサビリティの保存または状態の作成に失敗")
        return _err(SAVE_ERR, 500)


def _body() -> dict:
    return request.get_json(silent=True) or {}


@bp.route(_P, methods=["GET"])
def get_state(iid: str):
    insp, err = _load(iid)
    if err:
        return err
    try:
        return jsonify(**_state(insp))
    except Exception:
        log.exception("トレーサビリティの状態作成に失敗")
        return _err("状態を読み込めませんでした。画面を開き直してください。", 500)


@bp.route(f"{_P}/documents", methods=["POST"])
def add_documents(iid: str):
    from web.services.docverify import ingest, ingest_r3
    from web.services.docverify.tierflow import tiers
    insp, err = _load(iid)
    if err:
        return err
    files = [f for f in request.files.getlist("file") if f and f.filename]
    if not files:
        return _err("文書ファイルを選んでください。", 400)
    t = _tier(insp)
    docs = list(t["documents"])
    rejected, replaced, added = [], [], 0
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if ext not in _EXTS:
            rejected.append({"name": f.filename, "reason": "この形式は登録できません。md・docx・xlsx のどれかで保存し直してください。"})
            continue
        try:
            with tempfile.TemporaryDirectory() as tmp:
                document, passages = ingest_r3.ingest_r3(f.filename, f.read(), Path(tmp))
        except ingest.IngestError as e:
            rejected.append({"name": f.filename, "reason": str(e)})
            continue
        except Exception:
            log.exception("文書の取り込みに失敗")
            rejected.append({"name": f.filename, "reason": "読めませんでした。別の形式で保存し直してから登録してください。"})
            continue
        name = document.get("name") or f.filename
        old = next((d for d in docs if d.get("name") == name), None)
        try:
            est = tiers.estimate(name, passages)
        except Exception:
            log.exception("格の推定に失敗")
            est = {"tier": 3, "confidence": 0.0, "reason": "格を推定できませんでした。手で選んでください。"}
        doc = {"id": "T" + uuid.uuid4().hex[:8], "name": name, "format": document.get("format", ""),
               "tier": est["tier"], "tier_source": "ai", "confidence": est["confidence"],
               "reason": est["reason"], "uploaded_at": _now(), "passages": passages,
               "prev_passages": (old.get("passages") if old else None)}
        docs = [d for d in docs if d is not old] + [doc] if old else [*docs, doc]
        added += 1
        if old:
            replaced.append(name)
    if not added:
        names = "、".join(f"「{r['name']}」" for r in rejected)
        return jsonify(error=f"{names}を登録できませんでした。形式と内容を確かめてから、もう一度選んでください。",
                       rejected=rejected), 400
    t = {**t, "documents": docs}
    if t["approved"]:
        t = {**t, "approved": None, "findings": [], "conclusion": None, "reports": {}}
    resp, status = _save(insp, t, 201)
    if status == 201:
        resp = jsonify(**{**resp.get_json(), "upload_report": {"added": added, "rejected": rejected, "replaced": replaced}})
    return resp, status


@bp.route(f"{_P}/documents/<did>", methods=["PATCH"])
def set_tier(iid: str, did: str):
    insp, err = _load(iid)
    if err:
        return err
    tier = _body().get("tier")
    if not isinstance(tier, int) or isinstance(tier, bool) or tier not in (1, 2, 3, 4):
        return _err("格は 1〜4 から選んでください。", 400)
    t = _tier(insp)
    if not any(d["id"] == did for d in t["documents"]):
        return _err("文書が見つかりません。一覧を開き直してください。", 404)
    t = {**t, "documents": [{**d, "tier": tier, "tier_source": "human"} if d["id"] == did else d
                            for d in t["documents"]]}
    return _save(insp, t)


@bp.route(f"{_P}/documents/<did>", methods=["DELETE"])
def remove_document(iid: str, did: str):
    insp, err = _load(iid)
    if err:
        return err
    t = _tier(insp)
    if not any(d["id"] == did for d in t["documents"]):
        return _err("文書が見つかりません。一覧を開き直してください。", 404)
    t = {**t, "documents": [d for d in t["documents"] if d["id"] != did]}
    if t["approved"]:
        t = {**t, "approved": None, "findings": [], "conclusion": None, "reports": {}}
    return _save(insp, t)


@bp.route(f"{_P}/approve", methods=["POST"])
def approve(iid: str):
    from web.services.docverify.tierflow import rules
    insp, err = _load(iid)
    if err:
        return err
    t = _tier(insp)
    if not t["documents"]:
        return _err("文書がありません。先に文書を登録してください。", 400)
    by = str(_body().get("by") or "").strip()[:80] or "担当者"
    try:
        findings = rules.run(t["documents"])
    except Exception:
        log.exception("検査の実行に失敗")
        return _err("検査を実行できませんでした。もう一度お試しください。", 500)
    t = {**t, "approved": {"by": by, "at": _now()}, "findings": findings, "reports": {}, "conclusion": None}
    return _save(insp, t)


@bp.route(f"{_P}/findings/<fid>/report", methods=["POST"])
def report(iid: str, fid: str):
    insp, err = _load(iid)
    if err:
        return err
    reason = str(_body().get("reason") or "").strip()
    if not reason:
        return _err("誤検知の理由を書いてください。", 400)
    t = _tier(insp)
    if not any(f.get("id") == fid for f in t["findings"]):
        return _err("指摘が見つかりません。画面を開き直してください。", 404)
    by = str(_body().get("by") or "").strip()[:80] or "担当者"
    t = {**t, "reports": {**t["reports"], fid: {"reason": reason[:500], "by": by, "at": _now()}}}
    return _save(insp, t)


@bp.route(f"{_P}/confirm", methods=["POST"])
def confirm(iid: str):
    from web.services.docverify.tierflow import links
    insp, err = _load(iid)
    if err:
        return err
    t = _tier(insp)
    if not t["approved"]:
        return _err("先に登録内容を承認してください。", 400)
    body = _body()
    auto = links.conclude(t["findings"], t["reports"])
    level = body.get("level") or auto
    if level not in ("pass", "conditional", "fail"):
        return _err("結論は合格・条件付き・不合格から選んでください。", 400)
    by = str(body.get("by") or "").strip()[:80]
    if not by:
        return _err("確定者の名前を入れてください。", 400)
    conclusion = {"level": level, "auto": auto, "confirmed_by": by,
                  "comment": str(body.get("comment") or "")[:1000], "confirmed_at": _now()}
    return _save(insp, {**t, "conclusion": conclusion})


@bp.route(f"{_P}/reset", methods=["POST"])
def reset(iid: str):
    insp, err = _load(iid)
    if err:
        return err
    to = _body().get("to")
    t = _tier(insp)
    if to == 1:
        t = {**t, "approved": None, "findings": [], "reports": {}, "conclusion": None}
    elif to == 2:
        t = {**t, "conclusion": None}
    else:
        return _err("戻り先は 1 か 2 で指定してください。", 400)
    return _save(insp, t)
