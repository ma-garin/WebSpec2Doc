"""数量表現の正規化。「900秒」「15分」「15 min」「０.25時間」「1,000件」「十分」を同じ尺度に換算する。

決定論のみ。canonical_value は time=秒 / size=バイト / count=個数 / percent=% / money=円。
"""
from __future__ import annotations

import re
import unicodedata

_KANJI_DIGIT = {"〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_KANJI_UNIT = {"十": 10, "百": 100, "千": 1000, "万": 10000}

# (表記, 種別, 換算係数)。長い表記を先に照合する（regex 側で長さ降順に並べる）。
_UNIT_TABLE: tuple[tuple[str, str, float], ...] = (
    ("秒", "time", 1), ("sec", "time", 1), ("seconds", "time", 1), ("second", "time", 1),
    ("分間", "time", 60), ("分", "time", 60), ("min", "time", 60), ("minutes", "time", 60), ("minute", "time", 60),
    ("時間", "time", 3600), ("hours", "time", 3600), ("hour", "time", 3600),
    ("営業日", "time", 86400), ("日間", "time", 86400), ("日", "time", 86400), ("days", "time", 86400), ("day", "time", 86400),
    ("週間", "time", 604800), ("か月", "time", 2592000), ("ヶ月", "time", 2592000), ("カ月", "time", 2592000),
    ("年", "time", 31536000),
    ("バイト", "size", 1), ("KB", "size", 1024), ("MB", "size", 1024 ** 2), ("GB", "size", 1024 ** 3), ("TB", "size", 1024 ** 4),
    ("件", "count", 1), ("回", "count", 1), ("個", "count", 1), ("人", "count", 1), ("名", "count", 1),
    ("文字", "count", 1), ("桁", "count", 1), ("行", "count", 1), ("ページ", "count", 1), ("台", "count", 1),
    ("%", "percent", 1), ("パーセント", "percent", 1),
    ("万円", "money", 10000), ("円", "money", 1),
)
_NUM = r"\d[\d,]*(?:\.\d+)?|[〇一二三四五六七八九十百千万]+"
_UNIT_ALT = "|".join(re.escape(u[0]) for u in sorted(_UNIT_TABLE, key=lambda x: -len(x[0])))
_QTY_RE = re.compile(r"(" + _NUM + r")\s*(" + _UNIT_ALT + r")(?![A-Za-z])", re.IGNORECASE)
_HM_RE = re.compile(r"(\d+)\s*時間\s*(\d+)\s*分")
_LOOKUP = {u[0].lower(): (u[1], u[2]) for u in _UNIT_TABLE}
_BOUND_AFTER = (("以上", "ge"), ("を超え", "gt"), ("超", "gt"), ("以下", "le"), ("以内", "le"),
                ("未満", "lt"), ("まで", "le"))
_BOUND_BEFORE = (("最大", "le"), ("最低", "ge"), ("最小", "ge"), ("少なくとも", "ge"))


def nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def _kanji_num(s: str) -> float | None:
    total, cur = 0, 0
    for ch in s:
        if ch in _KANJI_DIGIT:
            cur = _KANJI_DIGIT[ch]
        elif ch in _KANJI_UNIT:
            total += (cur or 1) * _KANJI_UNIT[ch]
            cur = 0
        else:
            return None
    return float(total + cur)


def _number(s: str) -> float | None:
    if s[0].isdigit():
        try:
            return float(s.replace(",", ""))
        except ValueError:
            return None
    return _kanji_num(s)


def _bound(text: str, start: int, end: int) -> str:
    after = text[end:end + 4]
    for key, b in _BOUND_AFTER:
        if after.startswith(key):
            return b
    before = text[max(0, start - 5):start]
    for key, b in _BOUND_BEFORE:
        if before.endswith(key) or key in before:
            return b
    return "eq"


def normalize_quantity(text: str) -> list[dict]:
    """text 中の数量を出現順に返す。span は NFKC 正規化後の文字位置。"""
    t = nfkc(text)
    out: list[dict] = []
    taken: list[tuple[int, int]] = []
    for m in _HM_RE.finditer(t):
        secs = int(m.group(1)) * 3600 + int(m.group(2)) * 60
        out.append({"value": float(secs), "unit_kind": "time", "canonical_value": float(secs),
                    "raw": m.group(0), "span": (m.start(), m.end()), "bound": _bound(t, m.start(), m.end())})
        taken.append((m.start(), m.end()))
    for m in _QTY_RE.finditer(t):
        if any(m.start() < e and s < m.end() for s, e in taken):
            continue
        if m.group(2) in ("日", "日間") and m.start() > 0 and t[m.start() - 1] == "月":
            continue
        val = _number(m.group(1))
        info = _LOOKUP.get(m.group(2).lower())
        if val is None or info is None:
            continue
        kind, factor = info
        out.append({"value": val, "unit_kind": kind, "canonical_value": val * factor,
                    "raw": m.group(0), "span": (m.start(), m.end()), "bound": _bound(t, m.start(), m.end())})
    return sorted(out, key=lambda q: q["span"][0])
