"""質問票: 要確認の指摘から質問を作り、CSV/Excel で出し、回答 CSV を取り込む。"""
from __future__ import annotations

import csv
import io

_HEADER = ["No.", "場所", "質問", "回答"]
_DANGEROUS = ("=", "+", "-", "@")


def build(findings: list[dict]) -> list[dict]:
    out = []
    for f in findings:
        if f.get("certainty") != "要確認" or f.get("status") == "rejected":
            continue
        quote = f.get("quote") or ""
        q = f.get("message") or ""
        if quote:
            q = f"「{quote}」について: {q}" if q else f"「{quote}」の意味を具体的に教えてください。"
        out.append({"id": f"Q{len(out) + 1}", "finding_id": f.get("id"),
                    "location": f.get("location") or "", "question": q})
    return out


def _safe(v) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(_DANGEROUS) else s


def _rows(qs):
    return [[_safe(q["finding_id"]), _safe(q["location"]), _safe(q["question"]), ""] for q in qs]


def to_csv(qs: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(_HEADER)
    w.writerows(_rows(qs))
    return "﻿" + buf.getvalue()


def to_xlsx(qs: list[dict]) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "質問票"
    ws.append(_HEADER)
    for r in _rows(qs):
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def import_answers(insp: dict, csv_text: str) -> int:
    """No.（指摘 ID）と回答の列を読み、回答のある指摘に反映する。反映件数を返す。"""
    text = csv_text.lstrip("﻿")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "No." not in reader.fieldnames or "回答" not in reader.fieldnames:
        raise ValueError("質問票の CSV に「No.」と「回答」の列がありません。出力した質問票に回答を書いて取り込んでください。")
    answers = {}
    for row in reader:
        no = (row.get("No.") or "").strip().lstrip("'")
        ans = (row.get("回答") or "").strip()
        if no and ans:
            answers[no] = ans
    applied = 0
    for f in insp.get("findings", []):
        if f.get("id") in answers:
            f["answer"] = answers[f["id"]]
            f["certainty"] = "事実"
            applied += 1
    return applied
