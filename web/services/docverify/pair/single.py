"""要件定義書側の単独検査: AMBIGUOUS（解釈が割れる語）と UNTESTABLE（合否の基準が無い要件）。

入力は segment.requirement_units() が返す単位。出力は対検査の不整合と同じ形の dict。

- UNTESTABLE: 評価語（使いやすい・直感的・迷わず・十分な・高速な・安定して 等）だけで基準値が無い要件。
  または非機能要件のうち性能・可用性・容量の節にあって数値が 1 つも無い要件。
- AMBIGUOUS: checks の曖昧語（速やかに 等）を含み、同じ要件に数値の基準が併記されていない要件。
  評価語は UNTESTABLE に回すので AMBIGUOUS には数えない。
- 背景・目的・理由・補足の行は要件本文ではないので対象外。
"""
from __future__ import annotations

import re

from web.services.docverify import checks

# 合否を量で決められない評価語（ISO/IEC/IEEE 29148 5.2.7 の避けるべき表現のうち、主観的な形容）
_EVALUATIVE = re.compile(
    r"使い(?:やす|易)い?|(?:分|わ)かりやすい?|見やすい?|読みやすい?|直感的|迷わ(?:ず|ない|なく)|快適|"
    r"ストレス(?:なく|の無い|のない)|スムーズ|親しみやす|誰(?:にとって|で)も|"
    r"(?<![一-龯])十分(?:な|に)|(?<![一-龯])高速(?:な|に)|安定し(?:て|た)|"
    r"(?<![一-龯])柔軟(?:な|に)|(?<![一-龯])良好な|(?<![一-龯])適切な(?:性能|応答|品質)|"
    r"(?<![一-龯])高い(?:品質|性能|可用性|信頼性|操作性)|ユーザーフレンドリー"
)
# 要件本文ではない補足の行（「- 背景: …」など）
_NOTE = re.compile(r"^\s*(?:[-*+]|\d+[.)])?\s*(?:\*\*)?(?:背景|目的|理由|補足|備考|注|根拠)(?:\*\*)?\s*[:：]")
# 基準値: 算用数字、または数値の語
_NUMBER = re.compile(r"[0-9０-９]|パーセント")
# 数値が無ければ検証できない非機能の節
_MEASURED_SECTION = re.compile(r"性能|可用性|応答|容量|稼働|処理能力|スループット")
_NFR = "非機能要件"


def _is_note(text: str) -> bool:
    return bool(_NOTE.match(text))


def _has_number(text: str) -> bool:
    """ID（REQ-012 等）の数字を除いて、数値の基準があるか。"""
    return bool(_NUMBER.search(_free_text(text)))


def _free_text(text: str) -> str:
    """要件 ID と箇条書きの番号を取り除いた本文。"""
    text = re.sub(r"\b[A-Z]{2,}-\d+\b", "", text)
    return re.sub(r"^\s*\d+[.)]\s+", "", text)


def _in_nfr(unit) -> bool:
    return any(_NFR in h for h in unit.heading)


def _measured_section(unit) -> bool:
    return _in_nfr(unit) and any(_MEASURED_SECTION.search(h) for h in unit.heading[1:])


def _ambiguous_words(text: str) -> list[str]:
    """checks の曖昧語のうち、評価語（UNTESTABLE 側）を除いたもの。"""
    words = []
    for _, word in checks._ambiguous(text):
        if not _EVALUATIVE.search(word) and word not in words:
            words.append(word)
    return words


def _defect(kind: str, unit, reason: str) -> dict:
    return {"type": kind, "req_lines": [unit.start, unit.end], "design_lines": [], "reason": reason}


def _untestable(unit, vague: bool) -> dict | None:
    """vague: 曖昧語の指摘が既にある。節の数値欠落だけを理由に重ねて出さない。"""
    text = unit.text
    if _has_number(text):
        return None
    m = _EVALUATIVE.search(text)
    if m:
        return _defect("UNTESTABLE", unit, f"「{m.group(0)}」に合否を判定する基準値がありません。")
    if not vague and _measured_section(unit) and checks._is_req(text.splitlines()[-1].strip()):
        return _defect("UNTESTABLE", unit, "非機能要件に合否を判定する数値がありません。")
    return None


def _ambiguous(unit) -> dict | None:
    text = unit.text
    if _has_number(text):
        return None  # 曖昧語でも同じ要件に数値の基準があれば解釈は割れない
    words = _ambiguous_words(text)
    if not words:
        return None
    return _defect("AMBIGUOUS", unit, f"「{words[0]}」の基準が無く、解釈が割れます。")


def detect(req_units) -> list[dict]:
    """要件の単位から AMBIGUOUS と UNTESTABLE を検出する。"""
    found: list[dict] = []
    for unit in req_units:
        if _is_note(unit.text):
            continue
        amb = _ambiguous(unit)
        unt = _untestable(unit, amb is not None)
        found.extend(d for d in (amb, unt) if d)
    return found
