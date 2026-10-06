"""実画面との照合: 文書の「」内の語を巡回結果の画面文言と突き合わせる。"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from web.config import OUTPUT_DIR
from web.tenancy import scoped_output_dir

_QUOTED = re.compile(r"「([^「」]{1,40})」")


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(text or ""))).lower()


def _base() -> Path:
    return scoped_output_dir(OUTPUT_DIR)


def domains() -> list[str]:
    base = _base()
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir() and (p / "report.json").is_file())


def _labels(report: dict) -> set[str]:
    out = set()
    for s in report.get("screens", []) or []:
        for b in s.get("buttons", []) or []:
            out.add(_norm(b.get("text") or b.get("label") if isinstance(b, dict) else b))
        for h in s.get("headings", []) or []:
            out.add(_norm(h.get("text") if isinstance(h, dict) else h))
        for form in s.get("forms", []) or []:
            for fld in form.get("fields", []) or []:
                for k in ("label", "name", "placeholder", "element_id"):
                    if fld.get(k):
                        out.add(_norm(fld[k]))
    out.discard("")
    return out


def match(passages: list[dict], domain: str) -> list[dict]:
    if domain not in domains():
        raise ValueError("このサイトはまだ巡回されていません。まず System 01 で対象サイトを巡回してください。")
    report = json.loads((_base() / domain / "report.json").read_text(encoding="utf-8"))
    labels = _labels(report)
    findings, seen = [], set()
    for p in passages:
        for word in _QUOTED.findall(p.get("text", "")):
            key = (p["id"], _norm(word))
            if key in seen or _norm(word) in labels:
                continue
            seen.add(key)
            findings.append({
                "rule": "SCREEN.MISMATCH", "severity": "warning", "viewpoint": "実画面との食い違い",
                "message": f"「{word}」は巡回した画面の項目名・ボタン名・見出しに見つかりません。",
                "location": p.get("location", ""), "passage_id": p["id"], "quote": word,
                "certainty": "推定", "status": "candidate", "answer": None, "origin": "auto",
            })
    return findings
