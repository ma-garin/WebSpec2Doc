"""秘密情報・個人情報らしき値の検出と伏せ字（純関数）。

取り込み時の伏せ字版（redacted/）と、LLM 送信前検査（llm_gate）の (1) 秘密情報規則で使う。
規則は基本設計書 8 章のとおり。再現率は未検証（特に氏名らしき値は辞書なしの規則で低い）。
入力の文字列・リストは変更せず、新しい値を返す。
"""

from __future__ import annotations

import re
from typing import Iterable

#: 検出の種別。secret は送信先を問わず送らない。personal はデータ値として扱う。
KIND_SECRET = "secret"
KIND_PERSONAL = "personal"
KIND_CUSTOM = "custom"

_JA = r"[\u3040-\u30ff\u3400-\u9fff々ー]"
#: 氏名らしき値を「値の欄」に限るための境界（行頭・行末・引用符・区切り・代入）。
_CELL_LEFT = r"(?:^|(?<=[\"'`,\t=:：|]))"
_CELL_RIGHT = r"(?=$|[\"'`,\t|])"

#: (規則名, 種別, パターン, 伏せる範囲のグループ番号)
_RULES: tuple[tuple[str, str, re.Pattern[str], int], ...] = (
    (
        "private_key_block",
        KIND_SECRET,
        re.compile(
            r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"
        ),
        0,
    ),
    (
        "connection_string",
        KIND_SECRET,
        re.compile(r"\b(?:postgres(?:ql)?|mysql|mssql|oracle|jdbc:[a-z]+)://[^\s:/@]+:([^\s@]+)@"),
        1,
    ),
    (
        "password_assignment",
        KIND_SECRET,
        re.compile(
            r"(?i)\b(?:password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*"
            r"(\"[^\"\n]+\"|'[^'\n]+'|[^\s,;&\"']+)"
        ),
        1,
    ),
    ("aws_access_key", KIND_SECRET, re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), 0),
    ("openai_api_key", KIND_SECRET, re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}"), 0),
    (
        "email",
        KIND_PERSONAL,
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        0,
    ),
    (
        "phone",
        KIND_PERSONAL,
        re.compile(r"(?<![\d\-])(?:0\d{1,4}-\d{1,4}-\d{3,4}|0[5789]0\d{8})(?![\d\-])"),
        0,
    ),
    ("postal_code", KIND_PERSONAL, re.compile(r"(?<![\d\-])\d{3}-\d{4}(?![\d\-])"), 0),
    (
        "person_name",
        KIND_PERSONAL,
        re.compile(
            _CELL_LEFT + rf"\s*({_JA}{{2,4}}[ \u3000]{_JA}{{2,4}})\s*" + _CELL_RIGHT,
            re.MULTILINE,
        ),
        1,
    ),
)

_CARD_CANDIDATE = re.compile(r"(?<![\d\-])(?:\d[ \-]?){12,18}\d(?![\d\-])")


def _luhn_ok(digits: str) -> bool:
    """カード番号のチェックディジット（Luhn）が合うか。"""
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def _card_hits(text: str) -> list[dict]:
    hits = []
    for match in _CARD_CANDIDATE.finditer(text):
        digits = re.sub(r"[ \-]", "", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            hits.append(
                {"kind": KIND_PERSONAL, "start": match.start(), "end": match.end(), "rule": "card_number"}
            )
    return hits


def _rule_hits(text: str) -> list[dict]:
    hits = []
    for rule, kind, pattern, group in _RULES:
        for match in pattern.finditer(text):
            start, end = match.span(group)
            if start < end:
                hits.append({"kind": kind, "start": start, "end": end, "rule": rule})
    return hits


def _value_hits(text: str, values: Iterable[str], rule: str, kind: str) -> list[dict]:
    """指定された値の部分一致（大文字小文字を区別する）。"""
    hits = []
    for value in {str(v) for v in values if str(v).strip()}:
        start = text.find(value)
        while start != -1:
            hits.append({"kind": kind, "start": start, "end": start + len(value), "rule": rule})
            start = text.find(value, start + 1)
    return hits


def _drop_overlaps(hits: list[dict]) -> list[dict]:
    """重なる検出は、先に始まり長い方を残す。"""
    ordered = sorted(hits, key=lambda h: (h["start"], -(h["end"] - h["start"])))
    kept: list[dict] = []
    for hit in ordered:
        if kept and hit["start"] < kept[-1]["end"]:
            continue
        kept.append(hit)
    return kept


def scan(text: str, extra_values: Iterable[str] = ()) -> list[dict]:
    """秘密情報・個人情報らしき値の位置を返す。

    extra_values は利用者が追加で伏せたい値（部分一致）。戻り値は
    ``[{"kind", "start", "end", "rule"}]``（開始位置順・重なりなし）。値そのものは含めない。
    """
    if not text:
        return []
    hits = _rule_hits(text) + _card_hits(text)
    hits += _value_hits(text, extra_values, "extra_value", KIND_CUSTOM)
    return _drop_overlaps(hits)


def mask(text: str, hits: list[dict]) -> str:
    """検出範囲を規則名入りの伏せ字に置き換えた新しい文字列を返す。"""
    if not text or not hits:
        return text
    parts: list[str] = []
    cursor = 0
    for hit in _drop_overlaps(list(hits)):
        start, end = max(hit["start"], cursor), min(hit["end"], len(text))
        if start >= end:
            continue
        parts.append(text[cursor:start])
        parts.append(f"[伏せ字:{hit['rule']}]")
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def scrub(text: str, secrets: list[str]) -> str:
    """ログ・証跡用。入力された秘密の値と、秘密情報規則に当たる値を伏せる。

    個人情報らしき値は残す（証跡の再現に要るため。取り込み時の伏せ字は mask を使う）。
    """
    if not text:
        return text
    secret_hits = [h for h in _rule_hits(text) if h["kind"] == KIND_SECRET]
    secret_hits += _value_hits(text, secrets, "secret_value", KIND_SECRET)
    return mask(text, secret_hits)


def line_of(text: str, offset: int) -> int:
    """文字位置から 1 始まりの行番号を返す。"""
    return text.count("\n", 0, max(offset, 0)) + 1


def summarize(text: str, hits: list[dict]) -> list[dict]:
    """job.json の files[].redactions 用に ``[{"rule", "line"}]`` を返す（値は含めない）。"""
    seen: set[tuple[str, int]] = set()
    rows = []
    for hit in hits:
        key = (hit["rule"], line_of(text, hit["start"]))
        if key not in seen:
            seen.add(key)
            rows.append({"rule": key[0], "line": key[1]})
    return rows
