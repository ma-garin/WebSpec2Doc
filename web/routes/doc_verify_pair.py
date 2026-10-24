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
from web.services.docverify import pair_versions as pv

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


def revoke_approval(iid):
    b = _body()
    return _call(lambda: pr.revoke_approval(iid, b.get("reason", ""), pr.current_user(), b.get("rev")))


def analyze(iid):
    return _call(lambda: pr.analyze(iid, pr.current_user()))


def cases_list():
    return _call(lambda: {"cases": pc.cases()})


def cases_create():
    fs = request.files
    req, design = fs.get("requirements"), fs.get("design")
    if not req or not design:
        return _err(400, "files_required", "基準文書と確認文書を選んでください。")
    f = request.form
    return _call(lambda: pc.create(f.get("name", ""), req.read(), design.read(), f.get("due", ""), pr.current_user(),
        purpose=f.get("purpose"), baseline_role=f.get("baseline_role"), target_role=f.get("target_role"),
        baseline_name=f.get("baseline_name") or req.filename, target_name=f.get("target_name") or design.filename,
        baseline_version=f.get("baseline_version"), target_version=f.get("target_version")), status=201)


def versions(iid):
    fs = request.files
    files = {k: fs[k].read() for k in ("requirements", "design") if fs.get(k) and fs[k].filename}
    return _call(lambda: pv.upload(iid, files, pr.current_user(), request.form.get("rev") or None))


def diff(iid):
    a = request.args
    return _call(lambda: pv.diff(iid, a.get("from"), a.get("to")))


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
    ("/approve/revoke", revoke_approval, ["POST"]),
    ("/docs", docs, ["GET"]),
    ("/analyze", analyze, ["POST"]),
    ("/versions", versions, ["POST"]),
    ("/diff", diff, ["GET"]),
)


# ---- r3: 文書を読む（手で起こす指摘）・質問票 ----
_QSTATES = ("未回答", "回答済み", "解消")


def add_finding(iid):
    b = _body()

    def run():
        d = pr._existing(iid)
        quote, title = str(b.get("quote") or "").strip()[:300], str(b.get("title") or "").strip()[:80]
        side = b.get("side")
        if side not in ("req", "design") or not quote or not title:
            raise pr.PairError(400, "invalid", "本文を選び、指摘の内容を書いてから保存してください。")
        ref, none = {"section": str(b.get("section") or "") or None, "quote": quote}, {"section": None, "quote": ""}
        with pr._lock(d):
            fs = pr._findings(d)
            meta = pr._read(d / "docs" / "meta.json", {})
            meta = {**meta, "changed_sections": meta.get("changed_sections") or {"requirements": [], "design": []}}
            n = sum(1 for x in fs if str(x.get("id", "")).startswith("M-")) + 1
            f = {"id": f"M-{n:03d}", "type": b.get("type") if b.get("type") in pr.TYPES else "曖昧",
                 "severity": b.get("severity") if b.get("severity") in pr.SEVERITIES else "警告", "source": "human",
                 "title": title, "description": str(b.get("description") or title)[:1000],
                 "req_ref": ref if side == "req" else none, "design_ref": ref if side == "design" else none,
                 "status": None, "decided_by": None, "decided_at": None}
            f["changed_in_current"] = pr._is_changed(f, meta)
            pr._write(d / "findings.json", fs + [f])
        pr._trail(d, pr.current_user(), "finding_added", f["id"], title)
        return {"finding": f}
    return _call(run, status=201)


def questions(iid):
    return _call(lambda: {"questions": pr._read(pr._existing(iid) / "questions.json", [])})


def save_question(iid):
    b = _body()

    def run():
        d = pr._existing(iid)
        text = str(b.get("question") or "").strip()[:500]
        if not text:
            raise pr.PairError(400, "invalid", "質問の文を書いてから保存してください。")
        with pr._lock(d):
            qs = pr._read(d / "questions.json", [])
            qid = str(b.get("id") or "")
            known = any(q["id"] == qid for q in qs)
            row = {"id": qid if known else f"Q-{len(qs) + 1:03d}", "finding_id": str(b.get("finding_id") or "")[:40],
                   "question": text, "to": str(b.get("to") or "").strip()[:60], "due": str(b.get("due") or "")[:10],
                   "answer": str(b.get("answer") or "").strip()[:1000],
                   "state": b.get("state") if b.get("state") in _QSTATES else "未回答"}
            qs = [row if q["id"] == qid else q for q in qs] if known else qs + [row]
            pr._write(d / "questions.json", qs)
        return {"questions": qs}
    return _call(run)


_RULES = _RULES + (
    ("/findings", add_finding, ["POST"]),
    ("/questions", questions, ["GET"]),
    ("/questions", save_question, ["POST"]),
)



def register(target: Blueprint) -> None:
    for path, fn, methods in _RULES:
        target.add_url_rule(_P + path, f"pair_{fn.__name__}", fn, methods=methods)
    target.add_url_rule("/api/docverify/pair/cases", "pair_cases_list", cases_list, methods=["GET"])
    target.add_url_rule("/api/docverify/pair/cases", "pair_cases_create", cases_create, methods=["POST"])


register(bp)
