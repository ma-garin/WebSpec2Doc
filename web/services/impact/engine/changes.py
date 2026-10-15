"""変更箇所の抽出（DD-004 changes.py）。change = {code, kind, location, before, after, wording_only}。"""
from __future__ import annotations

import re

from .text import clip, norm

CONDITION = ("以上", "以下", "未満", "超", "必須", "任意", "不可", "可", "のみ", "ない")
NEGATION = ("ない", "ず", "不", "非", "無", "禁止", "しない", "できない")
_NUM = re.compile(r"\d+(?:\.\d+)?")
_SENT = re.compile(r"[。\n]+")
_CODE = re.compile(r"\b[A-Z]{2,5}-\d{3,4}\b")
# 「X」から「Y」に／XからYに（X・Y は助詞で区切られた 1 語句）
_FROM_TO = re.compile(r"(「[^」]*」|[^をのがはで、。「」\s]+)から(「[^」]*」|[^をのがはで、。「」\s]+?)(?=に|へ)")
MAX_CHANGES = 40


def _markers(s: str) -> tuple[frozenset, frozenset]:
    s = norm(s)
    nums = frozenset(_NUM.findall(s))
    words = frozenset(w for w in CONDITION + NEGATION if w in s)
    return nums, words


def is_wording_only(before: str | None, after: str | None) -> bool:
    """数字・否定語・条件語の集合が変更前後で同じなら True（語句だけの変更）。"""
    if not norm(before) or not norm(after):
        return False
    return _markers(before) == _markers(after)


def _change(i: int, kind: str, location: str, before: str, after: str) -> dict:
    before, after = clip(before, 300), clip(after, 300)
    return {"code": f"C{i}", "kind": kind, "location": location, "before": before, "after": after,
            "wording_only": is_wording_only(before, after)}


def from_baselines(diff: dict) -> list[dict]:
    """ベースラインの差分 {added, modified:[{old,new}], removed} から変更を作る。所在は項目の code。"""
    raw = []
    for m in diff.get("modified", []):
        raw.append(("modify", m["new"].get("code") or m["old"].get("code") or "", m["old"].get("text", ""), m["new"].get("text", "")))
    for p in diff.get("added", []):
        raw.append(("add", p.get("code") or "", "", p.get("text", "")))
    for p in diff.get("removed", []):
        raw.append(("delete", p.get("code") or "", p.get("text", ""), ""))
    return [_change(i, *r) for i, r in enumerate(raw[:MAX_CHANGES], start=1)]


def _kind_of(sentence: str, has_from_to: bool) -> str:
    if has_from_to:
        return "modify"
    if re.search(r"削除|廃止|なくす|取りやめ", sentence):
        return "delete"
    if re.search(r"追加|新設|新たに", sentence):
        return "add"
    return "text"


def from_text(text: str | None) -> list[dict]:
    """変更の指示文を 1 文 = 1 変更にする。「X から Y に」は before/after に分ける。"""
    out = []
    for s in _SENT.split(norm(text)):
        s = s.strip()
        if len(s) < 4:
            continue
        codes = _CODE.findall(s)
        location = " ".join(dict.fromkeys(codes)) if codes else "変更の指示"
        m = _FROM_TO.search(s)
        if m:
            before = s[:m.start()] + m.group(1) + s[m.end():]
            after = s[:m.start()] + m.group(2) + s[m.end():]
        else:
            before, after = "", s
        out.append((_kind_of(s, bool(m)), location, before, after))
    return [_change(i, *r) for i, r in enumerate(out[:MAX_CHANGES], start=1)]
