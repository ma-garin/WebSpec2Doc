"""影響度分析（System 09）。処理の中身は web/services/impact/ にある。"""
from __future__ import annotations

import csv
import io
import logging

from flask import Blueprint, Response, jsonify, render_template, request

from web.services.impact import analyze, store

bp = Blueprint("impact", __name__)
log = logging.getLogger(__name__)


def _err(message: str, status: int):
    return jsonify(error=message), status


def _load(jid: str):
    try:
        return store.load(jid), None
    except KeyError:
        return None, _err("分析が見つかりません。一覧から選び直してください。", 404)
    except (ValueError, OSError):
        log.exception("分析の読み込みに失敗 %s", jid)
        return None, _err("分析を読めませんでした。時間をおいて再読み込みしてください。", 500)


@bp.route("/impact")
def page() -> str:
    return render_template("impact_analysis.html")


@bp.route("/api/impact/jobs", methods=["GET"])
def list_jobs():
    try:
        return jsonify(jobs=store.list_all())
    except OSError:
        log.exception("分析一覧の取得に失敗")
        return _err("分析の一覧を読めませんでした。時間をおいて再読み込みしてください。", 500)


@bp.route("/api/impact/jobs", methods=["POST"])
def create_job():
    name = str((request.get_json(silent=True) or {}).get("name") or "").strip()
    if not name or len(name) > 100:
        return _err("分析の名前を 1〜100 文字で入れてください。", 400)
    return jsonify(job=store.save(store.new(name))), 201


@bp.route("/api/impact/jobs/<jid>", methods=["GET", "PATCH", "DELETE"])
def job(jid: str):
    job, err = _load(jid)
    if err:
        return err
    if request.method == "GET":
        return jsonify(job=job)
    if request.method == "DELETE":
        store.delete(job)
        return jsonify(ok=True)
    body = request.get_json(silent=True) or {}
    if "name" in body:
        name = str(body["name"] or "").strip()
        if not name or len(name) > 100:
            return _err("分析の名前を 1〜100 文字で入れてください。", 400)
        job = {**job, "name": name}
    if "order" in body:
        job = {**job, "order": str(body["order"] or "")[:2000]}
    return jsonify(job=store.save(job))


@bp.route("/api/impact/jobs/<jid>/docs", methods=["POST"])
def upload(jid: str):
    job, err = _load(jid)
    if err:
        return err
    uploads = request.files.getlist("files")
    if not uploads:
        return _err("文書が選ばれていません。設計書か画面仕様書を選んでください。", 400)
    notes = []
    for f in uploads:
        try:
            job = store.add_doc(job, f.filename or "", f.read())
        except store.StoreError as exc:
            notes.append(str(exc))
    job = store.save(job)
    if notes and len(notes) == len(uploads):
        return _err(" / ".join(notes), 400)
    return jsonify(job=job, notes=notes)


@bp.route("/api/impact/jobs/<jid>/docs/<path:name>", methods=["PATCH", "DELETE"])
def change_doc(jid: str, name: str):
    job, err = _load(jid)
    if err:
        return err
    try:
        if request.method == "DELETE":
            return jsonify(job=store.save(store.remove_doc(job, name)))
    except KeyError:
        return _err("その文書は取り込まれていません。一覧を再読み込みしてください。", 404)
    body = request.get_json(silent=True) or {}
    if not any(d["name"] == name for d in job["docs"]):
        return _err("その文書は取り込まれていません。一覧を再読み込みしてください。", 404)
    if ("role" in body and body["role"] not in store.ROLES) or ("store" in body and body["store"] not in store.STORES):
        return _err("選べない値です。一覧から選び直してください。", 400)
    docs = [{**d, **{k: body[k] for k in ("role", "store") if k in body}} if d["name"] == name else d for d in job["docs"]]
    return jsonify(job=store.save({**job, "docs": docs}))


@bp.route("/api/impact/jobs/<jid>/analyze", methods=["POST"])
def run_analysis(jid: str):
    job, err = _load(jid)
    if err:
        return err
    body = request.get_json(silent=True) or {}
    if "order" in body:
        job = {**job, "order": str(body["order"] or "")[:2000]}
    if not job["order"].strip() and not job["docs"]:
        return _err("変更の内容を書くか、変更後の仕様書を取り込んでください。", 400)
    try:
        result = analyze.run(job["order"], job["docs"], lambda n: store.read_passages(job, n))
    except (OSError, ValueError):
        log.exception("影響度分析に失敗 %s", jid)
        return _err("分析できませんでした。文書を取り込み直してからもう一度お試しください。", 500)
    return jsonify(job=store.save({**job, **result, "analyzed_at": store.now()}))


@bp.route("/api/impact/jobs/<jid>/export.csv")
def export_csv(jid: str):
    job, err = _load(jid)
    if err:
        return err
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ID", "優先度", "影響度", "影響を受ける箇所", "元の変更", "判断", "根拠の文書", "根拠の記述", "確かめるテスト"])
    for r in job["impacts"]:
        w.writerow([r["id"], f"P{r['priority']}", r["level_name"], r["where"], "・".join(r["changes"]),
                    r["why"], f"{r['doc']} {r['location']}".strip(), r["quote"], r["test"]])
    body = "﻿" + buf.getvalue()
    return Response(body, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''impact.csv"})
