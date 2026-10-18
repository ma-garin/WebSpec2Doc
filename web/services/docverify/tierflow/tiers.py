"""文書の格（1 方針〜4 メモ）を、ファイル名と見出し・語彙から決定的に推定する。"""
from __future__ import annotations

import re

TIERS = ((1, "方針"), (2, "決まりごと"), (3, "仕様"), (4, "メモ"))
TIER_HINT = {1: "ビジョン・憲章", 2: "規約・ガイドライン・用語集", 3: "PRD・設計書・ADR", 4: "議事録・台帳・メモ"}
LOW = 0.6

_WORDS = {
    1: re.compile(r"ビジョン|憲章|理念|vision|charter", re.I),
    2: re.compile(r"規約|ガイドライン|用語集|規程|guideline|glossary", re.I),
    3: re.compile(r"PRD|要件|要求|設計|ADR|仕様|spec", re.I),
    4: re.compile(r"議事録|メモ|台帳|ログ|memo|minutes", re.I),
}


def _hits(text: str) -> dict[int, int]:
    return {t: len(rx.findall(text)) for t, rx in _WORDS.items() if rx.search(text)}


def _heading(passages: list[dict]) -> str:
    for p in passages or []:
        text = (p.get("text") or "").strip()
        if text:
            return text.splitlines()[0][:80]
    return ""


def estimate(name: str, passages: list[dict]) -> dict:
    by_name = _hits(name)
    by_head = _hits(_heading(passages))
    if len(by_name) == 1:
        tier = next(iter(by_name))
        if by_head and tier not in by_head:
            return {"tier": tier, "confidence": 0.55,
                    "reason": f"ファイル名は{TIER_HINT[tier]}らしいが、先頭の見出しは別の種類に見えます。"}
        return {"tier": tier, "confidence": 0.9, "reason": f"ファイル名が{TIER_HINT[tier]}の語に一致しました。"}
    if len(by_name) > 1:
        tier = max(by_name, key=lambda t: (by_name[t], -t))
        return {"tier": tier, "confidence": 0.5, "reason": "ファイル名に複数の種類の語があり、決めきれませんでした。"}
    if by_head:
        tier = max(by_head, key=lambda t: (by_head[t], -t))
        conf = 0.7 if len(by_head) == 1 else 0.5
        return {"tier": tier, "confidence": conf, "reason": f"先頭の見出しの語から{TIER_HINT[tier]}と推定しました。"}
    return {"tier": 3, "confidence": 0.3, "reason": "名前にも見出しにも手がかりが無く、仕様と仮置きしました。"}
