"""分析の実行（DD-004 run.py）。段階: changes → candidates → llm → risk → save。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from . import candidates as cand_mod
from . import changes as changes_mod
from . import embed, llm_judge, risk, tests
from .text import clip

CARRY = ("state", "resolve_reason", "resolved_by", "resolved_at",
         "override_impact", "override_likelihood", "override_reason", "override_by", "override_at")
STAGES = {"changes": 10, "candidates": 40, "llm": 70, "risk": 85, "save": 95}


class AnalyzeError(Exception):
    """分析を始められない（対象が無い等）。message は利用者向け。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id() -> str:
    return uuid.uuid4().hex[:12]


def baseline_diff(conn, bid_old: str, bid_new: str) -> dict:
    """ベースラインの差分。repo.baselines.diff（本文の類似で書き換えを「変更」に対応づける）に合わせる。
    文書の差し替えで書き換えた項目は code が変わるため、code の突き合わせだと追加＋削除に分かれてしまう。"""
    from web.services.impact.repo import baselines
    return baselines.diff(conn, bid_old, bid_new)


def extract(conn, cr: dict) -> list[dict]:
    if cr.get("base_baseline") and cr.get("target_baseline"):
        found = changes_mod.from_baselines(baseline_diff(conn, cr["base_baseline"], cr["target_baseline"]))
        if found:
            return found
    return changes_mod.from_text(cr.get("change_text") or "")


def _llm_input(cands: list[dict]) -> list[dict]:
    out = []
    for c in cands:
        it = c["item"]
        place = f"{it['section']}（{it['location']}）" if it.get("section") else (it.get("location") or it["code"])
        out.append({"key": it["id"], "doc": it["document_name"], "place": place, "text": it["text"]})
    return out


def _engine(policy: str, allow_send: bool, verdicts, embedder, system: dict) -> dict:
    if verdicts is not None:
        return {"mode": "llm", "reason": "", "embedding": embedder.mode}
    if policy == "none":
        reason = "外部へ送信しない設定のため、つながり・語の一致・文字の近さによる規則で判定しました。"
    elif not allow_send:
        reason = "送信の確認が無かったため、規則で判定しました。"
    else:
        reason = "LLM に接続できないため、つながり・語の一致・文字の近さによる規則で判定しました。"
    eng = {"mode": "rule", "reason": reason, "embedding": embedder.mode}
    if system.get("degraded_recall") is not None:
        eng["recall"] = system["degraded_recall"]
    if system.get("degraded_precision") is not None:
        eng["precision"] = system["degraded_precision"]
    return eng


def score(conn, sid: str, system: dict, c: dict, by_code: dict, verdict: dict | None, override: dict | None = None) -> dict:
    """候補 1 件を impacts の行（保存前）にする。"""
    it = c["item"]
    is_tc = it["doc_kind"] == "testcase"
    sel = [it["code"]] if is_tc else tests.select(conn, sid, it["id"])
    level, level_reason = risk.impact_level(it["text"], it["doc_kind"], c["evidence"],
                                            int(verdict["level"]) if verdict else None)
    chs = [by_code[x] for x in c["change_ids"] if x in by_code]
    main = max(chs, key=lambda ch: risk.likelihood(ch["kind"], ch["wording_only"], c["depth"], bool(sel))[0])
    lk, lk_reason = risk.likelihood(main["kind"], main["wording_only"], c["depth"], bool(sel))
    ov = override or {}
    i_eff = ov.get("override_impact") or level
    l_eff = ov.get("override_likelihood") or lk
    r = int(i_eff) * int(l_eff)
    why = (verdict or {}).get("why", "").strip()
    idea = ((verdict or {}).get("test") or "").strip() or tests.idea(main, it)
    conf = 0.9 if verdict else round(min(1.0, max(e["score"] for e in c["evidence"]) if c["evidence"] else 0.0), 2)
    return {"item_id": it["id"], "item_code": it["code"], "document_name": it["document_name"], "doc_kind": it["doc_kind"],
            "location": it.get("location") or "", "section": it.get("section") or "", "text": clip(it["text"], 300),
            "depth": c["depth"], "evidence": c["evidence"] + ([{"type": "llm", "detail": why, "score": 0.9}] if why else []),
            "confidence": conf, "impact_level": level, "impact_reason": level_reason, "likelihood": lk,
            "likelihood_reason": lk_reason, "risk": r,
            "priority": risk.priority(r, int(system.get("p1_min") or 8), int(system.get("p2_min") or 4)),
            "change_ids": c["change_ids"], "tests": sel, "test_gap": 0 if sel else 1, "test_idea": idea,
            "method": "llm" if verdict else "rule"}


def _save(conn, cr_id: str, chs: list[dict], rows: list[dict], old: dict) -> None:
    with conn:
        conn.execute("DELETE FROM impacts WHERE cr_id = ?", (cr_id,))
        conn.execute("DELETE FROM changes WHERE cr_id = ?", (cr_id,))
        for ch in chs:
            conn.execute("INSERT INTO changes(id, cr_id, code, kind, location, before, after, wording_only)"
                         " VALUES(?,?,?,?,?,?,?,?)", (_id(), cr_id, ch["code"], ch["kind"], ch["location"],
                                                       ch["before"], ch["after"], int(ch["wording_only"])))
        for r in rows:
            keep = old.get((r["item_id"], json.dumps(sorted(r["change_ids"]))), {})
            vals = {**r, "id": _id(), "cr_id": cr_id, "change_ids": json.dumps(r["change_ids"], ensure_ascii=False),
                    "evidence": json.dumps(r["evidence"], ensure_ascii=False),
                    "tests": json.dumps(r["tests"], ensure_ascii=False),
                    **{k: keep.get(k) for k in CARRY}}
            vals["state"] = vals["state"] or "open"
            cols = list(vals)
            conn.execute(f"INSERT INTO impacts({','.join(cols)}) VALUES({','.join('?' * len(cols))})",
                         [vals[k] for k in cols])


def analyze(conn, sid: str, cr_code: str, actor: str, progress_cb=None, cancelled_cb=None, *,
            allow_send: bool = True, judge_fn=None, embedder=None):
    """分析して impacts を保存する。中止されたら保存せず 'cancelled' を返す。
    allow_send=False のときは policy に関わらず LLM・外部埋め込みを使わない。judge_fn / embedder はテスト用の差し替え。"""
    progress = progress_cb or (lambda stage, pct: None)
    cancelled = cancelled_cb or (lambda: False)
    srow = conn.execute("SELECT * FROM systems WHERE id = ?", (sid,)).fetchone()
    crow = conn.execute("SELECT * FROM change_requests WHERE system_id = ? AND code = ?", (sid, cr_code)).fetchone()
    if srow is None or crow is None:
        raise AnalyzeError("対象の変更要求が見つかりません。一覧から選び直してください。")
    system, cr = dict(srow), dict(crow)
    policy = system.get("policy") or "none"
    send_policy = policy if allow_send else "none"
    depth = int(cr.get("depth") or system.get("depth_default") or 2)

    progress("changes", STAGES["changes"])
    chs = extract(conn, cr)
    if cancelled():
        return "cancelled"
    progress("candidates", STAGES["candidates"])
    emb = embedder if embedder is not None else embed.make_embedder(send_policy)
    cands = cand_mod.collect(conn, cr, chs, depth, emb)
    if cancelled():
        return "cancelled"
    progress("llm", STAGES["llm"])
    verdicts = (judge_fn or llm_judge.judge)(chs, _llm_input(cands), send_policy) if send_policy != "none" else None
    if cancelled():
        return "cancelled"
    progress("risk", STAGES["risk"])
    vmap = {str(v["key"]): v for v in verdicts or []}
    old = {(r["item_id"], json.dumps(sorted(json.loads(r["change_ids"] or "[]")))): dict(r)
           for r in conn.execute("SELECT * FROM impacts WHERE cr_id = ?", (cr["id"],)).fetchall()}
    by_code = {ch["code"]: ch for ch in chs}
    rows = []
    for c in cands:
        v = vmap.get(c["item"]["id"])
        if v is not None and not v.get("related"):
            continue
        key = (c["item"]["id"], json.dumps(sorted(c["change_ids"])))
        rows.append(score(conn, sid, system, c, by_code, v, old.get(key)))
    rows.sort(key=lambda r: (r["priority"], -r["risk"], r["depth"], r["item_code"]))
    if cancelled():
        return "cancelled"
    progress("save", STAGES["save"])
    _save(conn, cr["id"], chs, rows, old)
    engine = _engine(policy, allow_send, verdicts, emb, system)
    counts = {"changes": len(chs), "candidates": len(cands), "impacts": len(rows),
              "p1": sum(r["priority"] == 1 for r in rows), "p2": sum(r["priority"] == 2 for r in rows),
              "p3": sum(r["priority"] == 3 for r in rows), "test_gap": sum(r["test_gap"] for r in rows)}
    return {"engine": engine, "counts": counts, "finished_at": _now()}
