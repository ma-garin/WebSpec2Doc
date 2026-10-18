"""6 つの規則。文書群から指摘（Finding）を決定的に作る。"""
from __future__ import annotations

import hashlib
import logging
import re

from .. import setcheck

log = logging.getLogger(__name__)

RULES = (("STATE", "日付や状態を書いていない"), ("TERMS", "用語集どおりの言葉"),
         ("PROTECTED_CHANGE", "勝手に直してはいけない文書を直していない"), ("CONFLICT", "上の格と食い違っていない"),
         ("REVERSE_REF", "上の格が下の格を参照していない"), ("DUPLICATE", "同じことを 2 か所に書いていない"))
SEVERITY = {"CONFLICT": "high", "REVERSE_REF": "mid", "PROTECTED_CHANGE": "high",
            "DUPLICATE": "mid", "TERMS": "low", "STATE": "low"}
_LABEL = dict(RULES)
_STATE = re.compile(r"20\d{2}[-/年]\s?\d{1,2}[-/月]\s?\d{1,2}日?|未実装|裁定待ち|TODO|対応中|検討中|未定|暫定")
_TERM_ARROW = re.compile(r"([^\s:：→|]{1,30})\s*(?:[:：]|→)\s*([^\s:：→|]{1,30})")


def _finding(rule: str, doc: dict, passage: dict, quote: str, reason: str, fix: str,
             rel_doc: str | None = None, rel_quote: str | None = None) -> dict | None:
    text = passage.get("text") or ""
    start = text.find(quote)
    if start < 0:
        return None
    key = f"{rule}|{doc['id']}|{passage.get('id')}|{quote}"
    return {"id": "F" + hashlib.sha1(key.encode()).hexdigest()[:8], "rule": rule, "rule_label": _LABEL[rule],
            "severity": SEVERITY[rule], "doc_id": doc["id"], "passage_id": passage.get("id"), "quote": quote,
            "start": start, "end": start + len(quote), "reason": reason, "fix": fix,
            "related_doc_id": rel_doc, "related_quote": rel_quote}


def _stem(name: str) -> str:
    return re.sub(r"\.[A-Za-z0-9]{1,5}$", "", name or "")


def _state(docs: list[dict]) -> list[dict]:
    out = []
    for d in docs:
        for p in d.get("passages") or []:
            for m in _STATE.finditer(p.get("text") or ""):
                out.append(_finding("STATE", d, p, m.group(0), f"「{m.group(0)}」は日付や状態で、古くなると嘘になります。",
                                    "日付や状態は台帳など下の格の文書に移し、この文書からは外してください。"))
    return out


def _banned(docs: list[dict]) -> dict[str, str]:
    banned: dict[str, str] = {}
    for d in docs:
        if d["tier"] != 2 or "用語" not in d["name"]:
            continue
        for p in d.get("passages") or []:
            for bad, good in _TERM_ARROW.findall((p.get("text") or "").replace("|", " ")):
                if bad != good and not bad.startswith(("正", "用語")):
                    banned[bad] = good
                elif bad.startswith("正") and good != bad:
                    banned[good] = bad[1:] if len(bad) > 1 else bad
    return banned


def _terms(docs: list[dict]) -> list[dict]:
    banned = _banned(docs)
    out = []
    for d in docs:
        if d["tier"] == 2 and "用語" in d["name"]:
            continue
        for p in d.get("passages") or []:
            for bad, good in banned.items():
                if bad in (p.get("text") or ""):
                    out.append(_finding("TERMS", d, p, bad, f"用語集では「{good}」と書く決まりで、「{bad}」は使えません。",
                                        f"「{bad}」を「{good}」に直してください。"))
    return out


def _protected(docs: list[dict]) -> list[dict]:
    out = []
    for d in docs:
        prev = d.get("prev_passages")
        if d["tier"] > 2 or not prev:
            continue
        old = {p.get("id"): p.get("text") for p in prev}
        for p in d.get("passages") or []:
            if p.get("id") in old and old[p["id"]] != p.get("text"):
                q = (p.get("text") or "").strip()[:60]
                out.append(_finding("PROTECTED_CHANGE", d, p, q, "方針・決まりごとの文書が前の版から書き換わっています。",
                                    "変更が正式な決定によるものか確認し、違えば元の版に戻してください。"))
    return out


def _conflict(docs: list[dict]) -> list[dict]:
    tier = {d["id"]: d["tier"] for d in docs}
    us = [u for u in setcheck.units(docs) if u["norm"]]
    by_doc = {d["id"]: d for d in docs}
    out = []
    for low in us:
        sl = setcheck.subject(low["norm"])
        for up in us:
            if not sl or tier[up["doc_id"]] >= tier[low["doc_id"]] or setcheck.subject(up["norm"]) != sl:
                continue
            why = setcheck.contradiction_reason(low, up)
            doc = by_doc[low["doc_id"]]
            psg = next((p for p in doc["passages"] if p.get("id") == low["passage_id"]), None)
            if why and psg:
                f = _finding("CONFLICT", doc, psg, low["text"], f"上の格の「{up['doc_name']}」と食い違っています。{why}",
                             f"「{up['doc_name']}」に合わせて直すか、上の文書を直す判断を仰いでください。",
                             up["doc_id"], up["text"])
                if f:
                    out.append(f)
    return out


def _reverse(docs: list[dict]) -> list[dict]:
    out = []
    for up in docs:
        for low in docs:
            stem = _stem(low["name"])
            if low["tier"] <= up["tier"] or len(stem) < 2:
                continue
            for p in up.get("passages") or []:
                f = _finding("REVERSE_REF", up, p, stem, f"上の格の文書が下の格の「{low['name']}」を参照しています。",
                             "上の文書から名前を外し、下の文書が上を参照する形にしてください。", low["id"], stem)
                if f:
                    out.append(f)
    return out


def _duplicate(docs: list[dict]) -> list[dict]:
    by_doc = {d["id"]: d for d in docs}
    out = []
    for pr in setcheck.find_pairs(setcheck.units(docs)):
        a, b = pr["a"], pr["b"]
        if pr["kind"] != "duplicate" or a["doc_id"] == b["doc_id"]:
            continue
        doc = by_doc[a["doc_id"]]
        psg = next((p for p in doc["passages"] if p.get("id") == a["passage_id"]), None)
        f = psg and _finding("DUPLICATE", doc, psg, a["text"], f"「{b['doc_name']}」にほぼ同じ文があります。",
                             "どちらか一方に寄せ、もう一方からは参照にしてください。", b["doc_id"], b["text"])
        if f:
            out.append(f)
    return out


_FUNCS = {"STATE": _state, "TERMS": _terms, "PROTECTED_CHANGE": _protected, "CONFLICT": _conflict,
          "REVERSE_REF": _reverse, "DUPLICATE": _duplicate}


def run(documents: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for rule, _ in RULES:
        try:
            found = _FUNCS[rule](documents)
        except Exception:
            log.exception("規則 %s の実行に失敗しました", rule)
            found = []
        for f in found:
            if f["id"] not in seen:
                seen.add(f["id"])
                out.append(f)
    return out
