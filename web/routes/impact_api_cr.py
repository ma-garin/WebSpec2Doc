"""影響度分析（System 09）の API v2: 変更要求・分析ジョブ・影響・関係図・承認・改修後レビュー・レポート・見本・移行。

契約は docs/lifecycle/system09-impact/03-detailed-design.md の DD-006・DD-007。
"""
from __future__ import annotations

from pathlib import Path

from flask import Response, jsonify, request

from web.routes.impact_api import body, bp, guard, open_db, actor
from web.services.impact import db, jobs
from web.services.impact.repo import actuals, approvals, baselines, crs, documents, impacts, links, systems
from web.services.impact.repo.errors import ImpactError

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "services" / "impact" / "sample"


def _cr(conn, sid: str, code: str) -> dict:
    return crs.get(conn, sid, code)


# ---- 変更要求 ----
@bp.get("/systems/<sid>/crs")
def list_crs(sid: str):
    with open_db() as conn:
        guard(conn, sid, "view")
        return jsonify(crs=crs.list(conn, sid, request.args.get("status") or None))


@bp.post("/systems/<sid>/crs")
def create_cr(sid: str):
    b = body()
    with open_db() as conn:
        who = guard(conn, sid, "cr_write")
        depth = b.get("depth") or systems.get(conn, sid)["depth_default"]
        cr = crs.create(conn, sid, str(b.get("title") or "").strip(), str(b.get("reason") or "").strip(),
                        str(b.get("change_text") or "").strip(), b.get("base_baseline") or None,
                        b.get("target_baseline") or None, int(depth), who)
        return jsonify(cr=cr), 201


@bp.get("/systems/<sid>/crs/<code>")
def get_cr(sid: str, code: str):
    with open_db() as conn:
        guard(conn, sid, "view")
        cr = _cr(conn, sid, code)
        return jsonify(cr=_with_status(conn, cr), summary=impacts.summary(conn, cr["id"]))


def _with_status(conn, cr: dict) -> dict:
    """画面が 1 回で描けるよう、集計・直近の分析・判定方式・承認の履歴を足す。"""
    import json as _json
    job = conn.execute("SELECT id, status, stage, progress, message, engine FROM jobs WHERE cr_id=? "
                       "ORDER BY started_at DESC LIMIT 1", (cr["id"],)).fetchone()
    last_done = conn.execute("SELECT engine FROM jobs WHERE cr_id=? AND status='done' ORDER BY started_at DESC LIMIT 1",
                             (cr["id"],)).fetchone()
    approvals_ = [dict(r) for r in conn.execute("SELECT decision, reason, actor, at FROM approvals WHERE cr_id=? "
                                                "ORDER BY at", (cr["id"],))]
    engine = _json.loads(last_done["engine"]) if last_done and last_done["engine"] else None
    return {**cr, "summary": impacts.summary(conn, cr["id"]), "engine": engine, "approvals": approvals_,
            "job": ({k: job[k] for k in ("id", "status", "stage", "progress", "message")} if job else None)}


@bp.patch("/systems/<sid>/crs/<code>")
def patch_cr(sid: str, code: str):
    with open_db() as conn:
        who = guard(conn, sid, "cr_write")
        return jsonify(cr=crs.update(conn, sid, code, body(), who))


@bp.post("/systems/<sid>/crs/<code>/transition")
def transition_cr(sid: str, code: str):
    b = body()
    to = str(b.get("to") or "")
    with open_db() as conn:
        who = guard(conn, sid, "approve" if to in ("approved", "returned") else "cr_write")
        if to in ("approved", "returned"):
            approvals.decide(conn, sid, code, to, str(b.get("reason") or ""), who)
            return jsonify(cr=_cr(conn, sid, code))
        return jsonify(cr=crs.transition(conn, sid, code, to, who, str(b.get("reason") or "")))


# ---- 分析 ----
def _prepare(conn, sid: str, cr: dict, policy: str):
    from web.services.impact.engine import candidates, changes
    from web.services.impact.engine.embed import make_embedder
    if cr.get("base_baseline") and cr.get("target_baseline"):
        found = changes.from_baselines(baselines.diff(conn, cr["base_baseline"], cr["target_baseline"]))
    else:
        found = changes.from_text(cr.get("change_text") or "")
    return found, candidates.collect(conn, cr, found, int(cr.get("depth") or 2), make_embedder(policy))


@bp.post("/systems/<sid>/crs/<code>/estimate")
def estimate(sid: str, code: str):
    from web.services.impact.engine import llm_judge
    with open_db() as conn:
        guard(conn, sid, "analyze")
        policy = systems.get(conn, sid)["policy"]
        found, cands = _prepare(conn, sid, _cr(conn, sid, code), "none")
        est = llm_judge.estimate(cands) if policy != "none" else {"count": 0, "chars": 0}
        return jsonify(policy=policy, changes=len(found), candidates=len(cands), send=est)


@bp.post("/systems/<sid>/crs/<code>/analyze")
def analyze(sid: str, code: str):
    with open_db() as conn:
        who = guard(conn, sid, "analyze")
        cr = _cr(conn, sid, code)
        if cr["status"] not in ("draft", "returned", "analyzing"):
            raise ImpactError("この状態の変更要求は分析できません。差し戻されたものか起票中のものを選んでください。", 409)
    job = jobs.start(sid, code, who, db.db_path(), bool(body().get("confirm_send")))
    return jsonify(job=job), 202


@bp.get("/jobs/<job_id>")
def job_status(job_id: str):
    return jsonify(job=jobs.status(db.db_path(), job_id))


@bp.post("/jobs/<job_id>/cancel")
def job_cancel(job_id: str):
    with open_db() as conn:
        row = conn.execute("SELECT c.system_id FROM jobs j JOIN change_requests c ON c.id=j.cr_id WHERE j.id=?",
                           (job_id,)).fetchone()
        if row is None:
            raise ImpactError("分析の処理が見つかりません。画面を再読み込みしてください。", 404)
        guard(conn, row["system_id"], "analyze")
    return jsonify(job=jobs.cancel(db.db_path(), job_id))


# ---- 影響 ----
@bp.get("/systems/<sid>/crs/<code>/impacts")
def list_impacts(sid: str, code: str):
    a = request.args
    with open_db() as conn:
        guard(conn, sid, "view")
        cr = _cr(conn, sid, code)
        pri = int(a["priority"]) if str(a.get("priority") or "").isdigit() else None
        return jsonify(impacts=impacts.list(conn, cr["id"], pri, a.get("state") or None),
                       summary=impacts.summary(conn, cr["id"]))


def _impact_guard(conn, impact_id: str, action: str) -> tuple[dict, str]:
    imp = impacts.get(conn, impact_id)
    row = conn.execute("SELECT system_id FROM change_requests WHERE id=?", (imp["cr_id"],)).fetchone()
    return imp, guard(conn, row["system_id"], action)


@bp.get("/impacts/<impact_id>")
def get_impact(impact_id: str):
    with open_db() as conn:
        imp, _ = _impact_guard(conn, impact_id, "view")
        return jsonify(impact=imp)


@bp.post("/impacts/<impact_id>/resolve")
def resolve_impact(impact_id: str):
    b = body()
    with open_db() as conn:
        _, who = _impact_guard(conn, impact_id, "resolve")
        return jsonify(impact=impacts.resolve(conn, impact_id, str(b.get("state") or ""), str(b.get("reason") or ""), who))


@bp.post("/impacts/<impact_id>/override")
def override_impact(impact_id: str):
    b = body()
    with open_db() as conn:
        _, who = _impact_guard(conn, impact_id, "override")
        try:
            lv, lk = int(b.get("impact_level")), int(b.get("likelihood"))
        except (TypeError, ValueError):
            raise ImpactError("影響度は 1〜4、発生可能性は 1〜3 から選んでください。", 400) from None
        return jsonify(impact=impacts.override(conn, impact_id, lv, lk, str(b.get("reason") or ""), who))


@bp.get("/systems/<sid>/crs/<code>/graph")
def graph(sid: str, code: str):
    with open_db() as conn:
        guard(conn, sid, "view")
        cr = _cr(conn, sid, code)
        rows = impacts.list(conn, cr["id"], None, None)
    nodes = [{"id": "c:" + c["id"], "kind": "change", "code": c["code"], "label": c["code"],
              "text": c.get("after") or c.get("before") or "", "change_id": c["id"], "depth": 0}
             for c in cr.get("changes", [])]
    edges = []
    by_code = {c["code"]: c["id"] for c in cr.get("changes", [])}
    for r in rows:
        nodes.append({"id": "i:" + r["id"], "kind": "item", "code": r["item_code"], "label": r["item_code"],
                      "text": (r.get("text") or "")[:80], "impact_id": r["id"], "depth": max(int(r.get("depth") or 1), 1),
                      "priority": r["priority"], "state": r["state"]})
        etype = (r.get("evidence") or [{}])[0].get("type", "keyword")
        if r.get("method") == "llm":
            etype = "llm"
        for ref in r.get("change_ids") or []:
            cid = by_code.get(ref, ref)  # 影響は変更箇所を code（C1）で持つ。点の ID は変更箇所の id
            edges.append({"source": "c:" + cid, "target": "i:" + r["id"], "from": "c:" + cid, "to": "i:" + r["id"],
                          "type": etype})
    return jsonify(nodes=nodes, edges=edges)


# ---- 承認・改修後レビュー・レポート ----
@bp.post("/systems/<sid>/crs/<code>/approval")
def approval(sid: str, code: str):
    b = body()
    with open_db() as conn:
        who = guard(conn, sid, "approve")
        approvals.decide(conn, sid, code, str(b.get("decision") or ""), str(b.get("reason") or ""), who)
        return jsonify(cr=_cr(conn, sid, code))


@bp.get("/systems/<sid>/crs/<code>/actuals")
def list_actuals(sid: str, code: str):
    with open_db() as conn:
        guard(conn, sid, "view")
        return jsonify(review=actuals.review(conn, sid, code))


@bp.post("/systems/<sid>/crs/<code>/actuals")
def add_actual(sid: str, code: str):
    b = body()
    with open_db() as conn:
        who = guard(conn, sid, "actuals")
        actuals.record(conn, sid, code, str(b.get("item_code") or "").strip(), str(b.get("note") or ""), who)
        return jsonify(review=actuals.review(conn, sid, code)), 201


@bp.get("/systems/<sid>/trend")
def trend(sid: str):
    with open_db() as conn:
        guard(conn, sid, "view")
        return jsonify(trend=actuals.trend(conn, sid))


@bp.get("/systems/<sid>/crs/<code>/report.xlsx")
def report(sid: str, code: str):
    from web.services.impact import report as rpt
    with open_db() as conn:
        guard(conn, sid, "view")
        data = rpt.build_xlsx(conn, sid, code)
    return Response(data, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''impact-{code}.xlsx"})


# ---- 見本・移行 ----
def _sample_bytes(name: str) -> bytes:
    return (SAMPLE_DIR / name).read_bytes()


@bp.post("/sample")
def sample():
    """見本の対象システム: 旧版でベースライン v1 → 新版に差し替えて v2 → つながり → 変更要求 → 分析（規則）。"""
    who = actor()
    with open_db() as conn:
        s = systems.create(conn, "見本: 会員管理システム", "影響度分析を試すための見本です。", who)
        sid, work = s["id"], db.db_path().parent / "work" / s["id"]
        for name in ("基本設計書_会員管理.md", "テストケース_会員登録.md"):
            documents.add(conn, sid, name, _sample_bytes(name), who, work)
        documents.add(conn, sid, "画面仕様書_会員登録.md", _sample_bytes("画面仕様書_会員登録_旧.md"), who, work)
        v1 = baselines.create(conn, sid, "v1.0", "変更前", who)
        documents.add(conn, sid, "画面仕様書_会員登録.md", _sample_bytes("画面仕様書_会員登録_新.md"), who, work)
        v2 = baselines.create(conn, sid, "v1.1", "電話番号を必須に", who)
        _sample_links(conn, sid, who)
        cr = crs.create(conn, sid, "電話番号を必須にする", "本人確認の強化（見本）",
                        "会員登録の電話番号を任意から必須にし、桁数を 10〜11 桁にする。", v1["id"], v2["id"], 2, who)
    job = jobs.start(sid, cr["code"], who, db.db_path(), False)
    return jsonify(system=s, cr=cr, job=job), 201


def _sample_links(conn, sid: str, who: str) -> None:
    rows = documents.items(conn, sid, None, "電話番号", 200, 0)
    screen = [r for r in rows if "画面仕様書" in (r.get("document_name") or "")]
    tests = [r for r in rows if "テストケース" in (r.get("document_name") or "")]
    for s_item in screen[:1]:
        for t_item in tests:
            links.add(conn, sid, s_item["id"], t_item["id"], who)


@bp.post("/migrate")
def migrate_old():
    from web.services.impact import migrate
    with open_db() as conn:
        return jsonify(result=migrate.run(conn, actor()))

