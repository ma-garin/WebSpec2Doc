"""追跡表（System 06 R3）。文書中の ID を決定的に抽出し、要件→設計→テストの対応・完全率・孤立を出す。

契約: docs/sdlc/20_design/WS2D-DD-006_詳細設計書_System06_R3.md 4 章。
"""
from __future__ import annotations

import io
import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

KINDS = (("requirement", "要件"), ("design", "設計"), ("test", "テスト"))
KIND_LABEL = dict(KINDS)
FORMATS = (
    {"id": "REQ", "label": "REQ-数字", "example": "REQ-001"},
    {"id": "FR", "label": "FR-数字", "example": "FR-001"},
    {"id": "NFR", "label": "NFR-数字", "example": "NFR-001"},
    {"id": "UC", "label": "UC-数字", "example": "UC-001"},
    {"id": "US", "label": "US-数字", "example": "US-001"},
    {"id": "SR", "label": "SR-数字", "example": "SR-001"},
)
DEFAULT_FORMAT = "REQ"
COVERAGE = "網羅性: 未検証"
NO_IDS = "この文書から ID を読み取れませんでした。ID の書式を確かめてください。"
NO_UPSTREAM = "要件の文書が登録されていません。種別「要件」で文書を登録してください。"


def pattern(fmt: str) -> re.Pattern:
    """書式 ID から正規表現を作る。前後が英数字の ID（NFR-001 の中の FR-001 等）は拾わない。"""
    if fmt not in {f["id"] for f in FORMATS}:
        raise ValueError("ID の書式を一覧から選んでください。")
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(fmt)}-\d+(?![0-9])")


def extract(passages: list[dict], fmt: str) -> list[dict]:
    """断片から ID を抜き出す。[{"id","location"}]（文書内の出現順・重複は最初の位置）。"""
    rx = pattern(fmt)
    seen: dict[str, dict] = {}
    for p in passages or []:
        for m in rx.findall(unicodedata.normalize("NFKC", p.get("text") or "").upper()):
            seen.setdefault(m, {"id": m, "location": p.get("location", "")})
    return list(seen.values())


def _sort_key(tid: str) -> tuple:
    num = re.search(r"(\d+)$", tid)
    return (tid.rsplit("-", 1)[0], int(num.group(1)) if num else 0, tid)


def _rate(covered: int, total: int) -> int | None:
    if not total:
        return None
    return int(Decimal(covered * 100 / total).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _index(docs: list[dict], fmt: str) -> tuple[dict, list[dict]]:
    """種別ごとに {ID: [位置]} を作る。ID の無い文書は unreadable に入れて外す（FR-06-135）。"""
    by_kind: dict[str, dict[str, list[str]]] = {k: {} for k, _ in KINDS}
    unreadable = []
    for d in docs:
        ids = extract(d.get("passages") or [], fmt)
        if not ids:
            unreadable.append({"doc_id": d.get("id"), "doc": d.get("name", ""), "kind": d.get("kind"), "message": NO_IDS})
            continue
        for x in ids:
            by_kind.setdefault(d.get("kind"), {}).setdefault(x["id"], []).append(f"{d.get('name', '')} {x['location']}".strip())
    return by_kind, unreadable


def build(documents: list[dict], fmt: str = DEFAULT_FORMAT) -> dict:
    """追跡表。完全率は「登録された下流の種別すべてに対応がある上流 ID の割合」。"""
    docs = [d for d in documents or [] if d.get("kind") in KIND_LABEL]
    by_kind, unreadable = _index(docs, fmt)
    downstream = [k for k, _ in KINDS[1:] if any(d.get("kind") == k for d in docs)]
    up = by_kind["requirement"]
    rows = [{"id": tid, "requirement": up[tid], **{k: by_kind[k].get(tid, []) for k in downstream}}
            for tid in sorted(up, key=_sort_key)]
    covered = sum(1 for r in rows if downstream and all(r[k] for k in downstream))
    orphans = [{"id": tid, "kind": k, "kind_label": KIND_LABEL[k], "locations": locs}
               for k in downstream for tid, locs in sorted(by_kind[k].items(), key=lambda x: _sort_key(x[0])) if tid not in up]
    messages = [] if any(d.get("kind") == "requirement" for d in docs) else [NO_UPSTREAM]
    return {"format": fmt, "columns": [{"kind": k, "label": KIND_LABEL[k]} for k in ("requirement", *downstream)],
            "rows": rows, "complete": {"covered": covered, "total": len(rows), "rate": _rate(covered, len(rows))},
            "orphans": orphans, "unreadable": unreadable, "messages": messages, "coverage": COVERAGE}


def to_xlsx(table: dict) -> bytes:
    """追跡表を xlsx にする。シート「追跡表」の行数は画面と同じ（見出し 1 行＋rows）（FR-06-133）。"""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "追跡表"
    cols = table.get("columns") or []
    ws.append(["ID", *[c["label"] for c in cols]])
    for r in table.get("rows") or []:
        ws.append([r["id"], *["\n".join(r.get(c["kind"]) or []) or "（対応なし）" for c in cols]])
    info = wb.create_sheet("完全率と孤立")
    c = table.get("complete") or {}
    info.append(["完全率", "—" if c.get("rate") is None else f"{c['rate']}%（{c.get('covered', 0)}/{c.get('total', 0)}）"])
    info.append(["孤立（上流の無い下流 ID）", len(table.get("orphans") or [])])
    for o in table.get("orphans") or []:
        info.append([o["id"], f"{o['kind_label']}: " + "／".join(o["locations"])])
    for u in table.get("unreadable") or []:
        info.append([u["doc"], u["message"]])
    info.append(["網羅性", "未検証"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
