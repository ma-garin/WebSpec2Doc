"""終了判定の集計と Excel 出力。"""
from __future__ import annotations

import io
from collections import Counter

_OPEN = {"adopted"}  # 候補（未検討）は未対応に数えず、別の理由として出す


def summary(insp: dict) -> dict:
    fs = insp.get("findings", []) or []
    by_status = dict(Counter(f.get("status") for f in fs))
    from web.services.docverify.settings import normalize_severity
    sev = lambda f: normalize_severity(f.get("severity"))  # noqa: E731
    by_severity = dict(Counter(sev(f) for f in fs if f.get("status") != "rejected"))
    adopted = sum(1 for f in fs if f.get("status") in ("adopted", "fixed", "verified"))
    n = len(insp.get("passages", []) or [])
    open_critical = sum(1 for f in fs if sev(f) == "critical" and f.get("status") in _OPEN)
    open_major = sum(1 for f in fs if sev(f) == "major" and f.get("status") in _OPEN)
    ec = insp.get("exit_criteria") or {}
    max_c = ec.get("max_open_critical", 0)
    max_w = ec.get("max_open_major", ec.get("max_open_warning", 5))
    reasons = []
    if not insp.get("document"):
        reasons.append("文書がまだ取り込まれていません。")
    pending = sum(1 for f in fs if f.get("status") == "candidate")
    if pending:
        reasons.append(f"未検討の候補が {pending} 件あります。「指摘にする」か「却下」を選んでください。")
    if open_critical > max_c:
        reasons.append(f"未対応の重大な指摘が {open_critical} 件あります（上限 {max_c} 件）。")
    if open_major > max_w:
        reasons.append(f"未対応の主要な指摘が {open_major} 件あります（上限 {max_w} 件）。")
    return {"by_status": by_status, "by_severity": by_severity, "quality": quality(insp),
            "density": round(adopted / n, 3) if n else 0.0,
            "open_critical": open_critical, "open_major": open_major,
            "open_warning": open_major,  # v1 画面との互換
            "exit_ok": not reasons, "reasons": reasons}


_ITEMS = ("necessary", "unambiguous", "complete", "consistent", "feasible", "verifiable", "traceable", "singular")
_LIVE = {"candidate", "adopted"}  # 却下・修正済みは減点しない


def quality(insp: dict) -> dict:
    """29148 の特性ごとに「未解決の指摘が無い断片の割合」を 0〜100 で返す。指摘の無い特性は検査対象外と区別しない。"""
    passages = insp.get("passages", []) or []
    n = len(passages)
    live = [f for f in insp.get("findings", []) or [] if f.get("status") in _LIVE and f.get("checklist_item")]
    items = {}
    for item in _ITEMS:
        hit = {f.get("passage_id") for f in live if f["checklist_item"] == item}
        items[item] = {"open": sum(1 for f in live if f["checklist_item"] == item),
                       "score": round(100 * (1 - len(hit) / n)) if n else None}
    hit_any = {f.get("passage_id") for f in live}
    return {"items": items, "overall": round(100 * (1 - len(hit_any) / n)) if n else None, "passages": n}


def _safe(v):
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(("=", "+", "-", "@")) else s


def to_xlsx(insp: dict) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "指摘一覧"
    cols = ["id", "severity", "viewpoint", "message", "location", "quote", "certainty", "status", "answer", "origin"]
    ws.append(["No.", "重大度", "観点", "指摘", "場所", "原文", "確度", "状態", "回答", "起点"])
    for f in insp.get("findings", []) or []:
        ws.append([_safe(f.get(c)) for c in cols])
    s = summary(insp)
    ws2 = wb.create_sheet("集計")
    ws2.append(["項目", "値"])
    for k, v in s["by_status"].items():
        ws2.append([f"状態: {k}", v])
    for k, v in s["by_severity"].items():
        ws2.append([f"重大度: {k}", v])
    ws2.append(["断片あたりの採用指摘", s["density"]])
    ws2.append(["未対応の重大", s["open_critical"]])
    ws2.append(["未対応の主要", s["open_major"]])
    ws2.append(["品質スコア（全体）", s["quality"]["overall"]])
    for k, v in s["quality"]["items"].items():
        ws2.append([f"品質スコア: {_ITEM_LABEL.get(k, k)}", v["score"]])
    ws2.append(["終了判定", "可" if s["exit_ok"] else "不可"])
    for r in s["reasons"]:
        ws2.append(["理由", r])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_ITEM_LABEL = {"necessary": "必要", "unambiguous": "曖昧でない", "complete": "完全", "consistent": "一貫",
               "feasible": "実現可能", "verifiable": "検証可能", "traceable": "追跡可能", "singular": "単一"}
_LABEL = {"critical": "重大", "major": "主要", "minor": "軽微"}


def overall(inspections: list[dict]) -> dict:
    """レビュー別・観点別・重大度別の件数、断片あたりの指摘密度、修正完了率。"""
    from web.services.docverify.settings import normalize_severity
    by_review, by_viewpoint, by_severity = [], Counter(), Counter()
    total_passages = total_valid = total_fixed = 0
    for insp in inspections:
        fs = [f for f in insp.get("findings") or [] if f.get("status") != "rejected"]
        valid = [f for f in fs if f.get("status") != "candidate"]
        fixed = sum(1 for f in valid if f.get("status") in ("fixed", "verified"))
        n = len(insp.get("passages") or [])
        by_viewpoint.update(f.get("checklist_item") or f.get("viewpoint") or "未分類" for f in valid)
        by_severity.update(normalize_severity(f.get("severity")) for f in valid)
        total_passages += n
        total_valid += len(valid)
        total_fixed += fixed
        by_review.append({"review_id": insp.get("id"), "review_name": insp.get("name"),
                          "findings": len(valid), "passages": n,
                          "density": round(len(valid) / n, 3) if n else 0.0,
                          "fix_rate": round(fixed / len(valid), 3) if valid else 0.0})
    return {"by_review": by_review, "by_viewpoint": dict(by_viewpoint), "by_severity": dict(by_severity),
            "density": round(total_valid / total_passages, 3) if total_passages else 0.0,
            "fix_rate": round(total_fixed / total_valid, 3) if total_valid else 0.0}
