"""曖昧語の語単位照合（REQ-F-010-04 / REQ-F-005-04。設計 DD-069）。

語彙は要件 REQ-F-010-04 の 12 語で閉じる（`scripts/req-lint.py` の既定の語と同じ）。
別の語の一部（不適切に・三十分・同等 など）は検出しない。純粋関数だけで、他のモジュールを読み込まない。
"""
from __future__ import annotations

import re
from typing import NamedTuple

WORDS: tuple[str, ...] = (
    "適切に", "必要に応じて", "など", "等", "高速", "十分", "可能な限り", "迅速", "柔軟",
    "使いやすい", "わかりやすい", "分かりやすい")

_K = "一-龯々〆ヵヶ"                       # 漢字
_H = "ぁ-ん"                               # ひらがな
_P = "のをがにでとはもへやか"              # 助詞
_TOU_PREFIX = "同平対上高中下初一二三優劣均不相何"   # 「等」が熟語の一部になる直前の字


class Match(NamedTuple):
    word: str
    start: int
    end: int


# 語 -> 境界規則つきの正規表現（lookbehind は固定長）
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("適切に", re.compile(rf"(?<![{_K}])適切に")),
    ("必要に応じて", re.compile(rf"(?<![{_K}])必要に応じて")),
    ("可能な限り", re.compile(rf"(?<![{_K}])可能な限り")),
    ("高速", re.compile(rf"(?<![{_K}])高速(?![{_K}])")),
    ("迅速", re.compile(rf"(?<![{_K}])迅速(?![{_K}])")),
    ("柔軟", re.compile(rf"(?<![{_K}])柔軟(?![{_K}])")),
    ("十分", re.compile(rf"(?<![{_K}])十分(?![{_K}])")),
    ("等", re.compile(rf"(?<![{_TOU_PREFIX}])等(?![{_K}しじ])")),
    ("など", re.compile(rf"など(?:(?![{_H}])|(?=[{_P}]))")),
    ("使いやすい", re.compile("使いやすい")),
    ("わかりやすい", re.compile("わかりやすい")),
    ("分かりやすい", re.compile(rf"(?<![{_K}])分かりやすい")),
)


def find_ambiguous(text: str) -> tuple[Match, ...]:
    """曖昧語の出現を出現順に返す。重なりは先に始まる語、同じ開始なら長い語を採る。None は TypeError。"""
    found = [Match(word, m.start(), m.end()) for word, pat in _PATTERNS for m in pat.finditer(text)]
    found.sort(key=lambda m: (m.start, -(m.end - m.start)))
    chosen: list[Match] = []
    for m in found:
        if not chosen or m.start >= chosen[-1].end:
            chosen.append(m)
    return tuple(chosen)


def ambiguous_words(text: str) -> tuple[str, ...]:
    """見つかった語を、出現順・重複なしで返す（従来の署名）。"""
    return tuple(dict.fromkeys(m.word for m in find_ambiguous(text)))


__all__ = ["WORDS", "Match", "ambiguous_words", "find_ambiguous"]
