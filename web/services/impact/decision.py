"""変更要求 1 件の「影響範囲 → 再テスト対象 → 判断」を 1 つの応答にまとめる（System 09 判断画面）。

並び順は件数ではなくリスク: 到達可能性（段数）× 変更の強さ × 未検証（テストなしで 2 倍）。
判定は共通語彙（合格／不合格／判定不能／未判定）で、「全体」と「今回の変更分」を別の行にする。
"""
from __future__ import annotations

from web.services.impact.repo import impacts as impacts_repo

S06_PREFIX = "System06 要件変更 "
REACH = {0: (3, "変更箇所そのもの"), 1: (2, "1 段先でつながる")}
STATE = {"open": "要確認", "required": "対応要", "not_required": "対応不要"}


def source(cr: dict) -> dict:
    """起票元。S06（ドキュメント検証）の自動起票は題名の接頭辞で判別する（links_sys09.submit_changes が付ける）。"""
    title = str(cr.get("title") or "")
    if title.startswith(S06_PREFIX):
        return {"kind": "docverify", "label": "ドキュメント検証から受領", "inspection": title[len(S06_PREFIX):].strip()}
    return {"kind": "manual", "label": "手動で起票", "inspection": None}


def _eff(i: dict) -> tuple[int, int]:
    lv = i.get("override_impact") if i.get("override_impact") is not None else i.get("impact_level")
    lk = i.get("override_likelihood") if i.get("override_likelihood") is not None else i.get("likelihood")
    return int(lv or 1), int(lk or 1)


def _tests(i: dict) -> list[str]:
    t = i.get("tests") or []
    return [str(x.get("code") if isinstance(x, dict) else x) for x in t if x] if isinstance(t, list) else []


def score(i: dict) -> dict:
    lv, _ = _eff(i)
    depth = int(i.get("depth") or 0)
    reach, reach_label = REACH.get(depth, (1, f"{depth} 段先でつながる"))
    untested = bool(i.get("test_gap")) or not _tests(i)
    value = 0 if i.get("state") == "not_required" else reach * lv * (2 if untested else 1)
    why = f"到達 {reach}（{reach_label}）× 変更の強さ {lv}" + (" × 未検証 2（つながるテストなし）" if untested else "")
    return {"score": value, "reach": reach, "untested": untested, "why": why}


def missing_links(conn, sid: str) -> list[dict]:
    """要件の項目ごとに、設計（設計書・画面仕様）とテストへのつながりが無いものを名指しする。"""
    reqs = conn.execute("SELECT i.id, i.code, i.text FROM items i JOIN documents d ON d.id=i.document_id "
                        "WHERE i.system_id=? AND d.kind='requirement' ORDER BY i.code", (sid,)).fetchall()
    out = []
    for r in reqs:
        kinds = {k[0] for k in conn.execute(
            "SELECT d.kind FROM links l JOIN items i ON i.id = CASE WHEN l.a_item=? THEN l.b_item ELSE l.a_item END "
            "JOIN documents d ON d.id=i.document_id WHERE l.system_id=? AND (l.a_item=? OR l.b_item=?)",
            (r["id"], sid, r["id"], r["id"])).fetchall()}
        lack = [lbl for lbl, ks in (("設計", {"design", "screen"}), ("テスト", {"testcase"})) if not kinds & ks]
        if lack:
            out.append({"code": r["code"], "text": str(r["text"] or "")[:60], "lack": lack})
    return out


def _count_requirements(conn, sid: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM items i JOIN documents d ON d.id=i.document_id "
                        "WHERE i.system_id=? AND d.kind='requirement'", (sid,)).fetchone()[0]


def _retest(rows: list[dict]) -> list[dict]:
    by: dict[str, dict] = {}
    for i in rows:
        if i["state"] == "not_required":
            continue
        for t in _tests(i):
            e = by.setdefault(t, {"test": t, "kind": "rerun", "because": [], "score": 0})
            e["because"].append(i["item_code"])
            e["score"] = max(e["score"], i["risk_score"]["score"])
        if i["risk_score"]["untested"]:
            by[f"new:{i['item_code']}"] = {"test": None, "kind": "new", "because": [i["item_code"]],
                                           "score": i["risk_score"]["score"], "idea": i.get("test_idea") or ""}
    return sorted(by.values(), key=lambda e: -e["score"])


def _names(rows, n=5) -> str:
    head = "、".join(rows[:n])
    return head + (f" ほか {len(rows) - n} 件" if len(rows) > n else "")


def _verdict_change(cr: dict, rows: list[dict], missing_codes: set[str]) -> dict:
    if not rows:
        if cr.get("status") == "draft" and not cr.get("job"):
            return {"verdict": "未判定", "reason": "まだ分析していません。", "next": "「分析する」を押してください。", "named": []}
        return {"verdict": "判定不能", "reason": "影響の候補が 0 件でした。文書の取り込みが足りない可能性があります。",
                "next": "設計書・テストケースを取り込んでから分析し直してください。", "named": []}
    open_ = [i["item_code"] for i in rows if i["state"] == "open"]
    bad = [i["item_code"] for i in rows if i["state"] == "required" and i["risk_score"]["untested"]]
    bad += [i["item_code"] for i in rows if i["state"] != "not_required" and i["item_code"] in missing_codes]
    bad = list(dict.fromkeys(bad))
    if bad:
        return {"verdict": "不合格", "reason": f"対応要なのに確かめるテストが無い・つながりが欠けている項目: {_names(bad)}。",
                "next": "テストを追加するか、つながりを登録してから見直してください。", "named": bad}
    if open_:
        return {"verdict": "未判定", "reason": f"要確認が残っています: {_names(open_)}。",
                "next": "上の順に、対応要か対応不要を決めてください。", "named": open_}
    return {"verdict": "合格", "reason": "影響はすべて判断済みで、対応要の項目には再テストがあります。",
            "next": "再テスト対象を実施し、承認に回してください。", "named": []}


def _verdict_all(conn, sid: str, missing: list[dict]) -> dict:
    if not _count_requirements(conn, sid):
        return {"verdict": "判定不能", "reason": "要件定義書が取り込まれていません。",
                "next": "文書タブで要件定義書を取り込んでください。", "named": []}
    if missing:
        codes = [m["code"] for m in missing]
        return {"verdict": "不合格", "reason": f"設計かテストへのつながりが無い要件: {_names(codes)}。",
                "next": "つながりタブで対応する設計・テストを登録してください。", "named": codes}
    return {"verdict": "合格", "reason": "すべての要件に設計とテストのつながりがあります。", "next": "", "named": []}


def build(conn, sid: str, cr: dict) -> dict:
    rows = []
    for i in impacts_repo.list(conn, cr["id"]):
        rows.append(dict(i, risk_score=score(i), state_label=STATE.get(i.get("state"), i.get("state"))))
    rows.sort(key=lambda i: (-i["risk_score"]["score"], -_eff(i)[0], str(i.get("item_code") or "")))
    missing = missing_links(conn, sid)
    codes = {m["code"] for m in missing}
    return {"source": source(cr), "impacts": rows, "retest": _retest(rows), "missing_links": missing,
            "verdict": {"overall": _verdict_all(conn, sid, missing), "change": _verdict_change(cr, rows, codes)},
            "order": "到達可能性 × 変更の強さ × 未検証（件数順ではありません）"}
