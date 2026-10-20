"""ドキュメント検証 R3: 複数文書の登録・集合の検査・追跡表・規則と語彙の設定（SCR-06-07）。

契約: docs/sdlc/20_design/WS2D-DD-006_詳細設計書_System06_R3.md 6 章。既存の doc_verify Blueprint は変えない。
"""
from __future__ import annotations

import logging
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, Response, jsonify, request

bp = Blueprint("doc_verify_setcheck", __name__)
log = logging.getLogger(__name__)

_IID = re.compile(r"^[0-9a-f]{12}$")
_DID = re.compile(r"^D[0-9a-f]{8}$")
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
NOT_FOUND = "検査が見つかりません。検査一覧から開き直してください。"
SAVE_ERR = "保存できませんでした。もう一度お試しください。"


def _err(message: str, status: int):
    return jsonify(error=message), status


def _load(iid: str):
    from web.services.docverify import store
    if not _IID.match(iid or ""):
        return None, _err(NOT_FOUND, 404)
    try:
        return store.load(iid), None
    except KeyError:
        return None, _err(NOT_FOUND, 404)


def _public_doc(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "passages"}


def _docs_for_check(insp: dict) -> list[dict]:
    """集合の検査の対象: 単一文書（main）＋R3 で登録した文書。"""
    main = []
    if insp.get("document"):
        main = [{"id": "main", "name": insp["document"].get("name", ""), "kind": None,
                 "passages": insp.get("passages") or [], "include_hidden": True}]
    return [*main, *(insp.get("documents") or [])]


def _state(insp: dict) -> dict:
    from web.services.docverify import setcheck, trace
    fmt = insp.get("trace_format") or trace.DEFAULT_FORMAT
    return {"documents": [_public_doc(d) for d in insp.get("documents") or []],
            "kinds": [{"id": k, "label": v} for k, v in trace.KINDS],
            "set_check": setcheck.view(insp.get("set_check")),
            "trace": trace.build(insp.get("documents") or [], fmt),
            "formats": list(trace.FORMATS), "trace_format": fmt,
            "findings": len(insp.get("findings") or []), "coverage": setcheck.COVERAGE}


def _save_respond(insp: dict, status: int = 200):
    from web.services.docverify import store
    try:
        store.save(insp)
    except Exception:
        log.exception("R3 の保存に失敗")
        return _err(SAVE_ERR, 500)
    return jsonify(**_state(insp)), status


@bp.route("/api/docverify/inspections/<iid>/r3", methods=["GET"])
def get_state(iid: str):
    insp, err = _load(iid)
    if err:
        return err
    return jsonify(**_state(insp))


def _detect(passages: list[dict], document: dict, include_hidden: bool) -> list[dict]:
    from web.services.docverify import checks, setcheck
    cfg = setcheck.load_settings()
    target = [p for p in passages if include_hidden or not p.get("hidden")]
    found = setcheck.apply_rules(checks.candidates(target), target, cfg)
    found = [*found, *setcheck.term_variants(target, cfg.get("synonyms")),
             *setcheck.missing_attributes(document.get("tables"))]
    return [{**f, "id": f"F{i}"} for i, f in enumerate(found, start=1)]


@bp.route("/api/docverify/inspections/<iid>/r3/documents", methods=["POST"])
def add_document(iid: str):
    from web.services.docverify import ingest, ingest_r3, trace
    insp, err = _load(iid)
    if err:
        return err
    kind = (request.form.get("kind") or "").strip()
    if kind not in trace.KIND_LABEL:
        return _err("文書の種別（要件・設計・テスト）を選んでください。", 400)
    file = request.files.get("file")
    if file is None or not file.filename:
        return _err("文書ファイルを選んでください。", 400)
    include_hidden = request.form.get("include_hidden", "1") != "0"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            document, passages = ingest_r3.ingest_r3(file.filename, file.read(), Path(tmp))
        candidates = _detect(passages, document, include_hidden)
    except ingest.IngestError as e:
        return _err(str(e), 400)
    except Exception:
        log.exception("R3 文書の取り込みに失敗")
        return _err("文書を読めませんでした。別の形式で保存し直してから取り込んでください。", 500)
    doc = {**document, "id": "D" + uuid.uuid4().hex[:8], "kind": kind, "kind_label": trace.KIND_LABEL[kind],
           "include_hidden": include_hidden, "uploaded_at": datetime.now(timezone.utc).isoformat(),
           "passages": passages, "candidates": candidates}
    return _save_respond({**insp, "documents": [*(insp.get("documents") or []), doc]}, 201)


@bp.route("/api/docverify/inspections/<iid>/r3/documents/<did>", methods=["DELETE"])
def remove_document(iid: str, did: str):
    insp, err = _load(iid)
    if err:
        return err
    docs = insp.get("documents") or []
    if not _DID.match(did or "") or not any(d.get("id") == did for d in docs):
        return _err("文書が見つかりません。画面を再読み込みしてください。", 404)
    return _save_respond({**insp, "documents": [d for d in docs if d.get("id") != did]})


@bp.route("/api/docverify/inspections/<iid>/r3/setcheck", methods=["POST"])
def run_setcheck(iid: str):
    from web.services.docverify import setcheck
    insp, err = _load(iid)
    if err:
        return err
    docs = _docs_for_check(insp)
    if not docs:
        return _err("検査する文書がありません。文書を登録してから実行してください。", 400)
    try:
        result = setcheck.run(docs, insp.get("set_check"))
    except Exception:
        log.exception("集合の検査に失敗")
        return _err("集合の検査を実行できませんでした。もう一度お試しください。", 500)
    return _save_respond({**insp, "set_check": result})


@bp.route("/api/docverify/inspections/<iid>/r3/setcheck/<pid>", methods=["POST"])
def decide_pair(iid: str, pid: str):
    from web.services.docverify import setcheck
    from web.services.docverify.settings import current_user
    insp, err = _load(iid)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    try:
        updated = setcheck.decide(insp, pid, str(body.get("decision") or ""), current_user())
    except ValueError as e:
        return _err(str(e), 400)
    except KeyError:
        return _err("候補の組が見つかりません。集合の検査をもう一度実行してください。", 404)
    return _save_respond(updated)


@bp.route("/api/docverify/inspections/<iid>/r3/trace", methods=["POST"])
def set_trace_format(iid: str):
    from web.services.docverify import trace
    insp, err = _load(iid)
    if err:
        return err
    fmt = str((request.get_json(silent=True) or {}).get("format") or "")
    try:
        trace.pattern(fmt)
    except ValueError as e:
        return _err(str(e), 400)
    return _save_respond({**insp, "trace_format": fmt})


@bp.route("/api/docverify/inspections/<iid>/r3/trace.xlsx")
def trace_xlsx(iid: str):
    from web.services.docverify import trace
    insp, err = _load(iid)
    if err:
        return err
    try:
        data = trace.to_xlsx(trace.build(insp.get("documents") or [], insp.get("trace_format") or trace.DEFAULT_FORMAT))
    except Exception:
        log.exception("追跡表の出力に失敗")
        return _err("追跡表を出力できませんでした。もう一度出力してください。", 500)
    return Response(data, mimetype=_XLSX, headers={"Content-Disposition": "attachment; filename=trace.xlsx"})


@bp.route("/api/docverify/r3/settings", methods=["GET", "PUT"])
def r3_settings():
    from web.services.docverify import setcheck
    if request.method == "GET":
        try:
            return jsonify(setcheck.load_settings())
        except Exception:
            log.exception("R3 設定の読み込みに失敗")
            return _err("設定を読めませんでした。時間をおいて再読み込みしてください。", 500)
    try:
        return jsonify(setcheck.save_settings(request.get_json(silent=True)))
    except ValueError as e:
        return _err(str(e), 400)
    except Exception:
        log.exception("R3 設定の保存に失敗")
        return _err(SAVE_ERR, 500)
