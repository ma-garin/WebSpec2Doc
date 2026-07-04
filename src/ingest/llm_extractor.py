"""PDF/Word 等の自由文からの LLM 意味抽出（Doc Fusion Phase 2）。

表構造からは読み取れない画面・項目の言及や業務ルール（計算式・限度値・
権限条件）を LLM Structured Outputs で構造化する。すべての抽出項目は
文書中の原文（quote）を伴い、quote が原文行に見つからない出力は
幻覚とみなして破棄する（evidence-only 原則）。
"""

from __future__ import annotations

import logging
import unicodedata
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from ingest.models import DocumentedField, DocumentedRule, DocumentedScreen, DocumentEvidence

if TYPE_CHECKING:
    from llm.provider import LLMProvider

logger = logging.getLogger(__name__)

EXTRACTION_SCHEMA_NAME = "document_semantics"
EXTRACTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "screens": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "url_hint": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["name", "url_hint", "quote"],
                "additionalProperties": False,
            },
        },
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "screen_name": {"type": "string"},
                    "field_type": {"type": "string"},
                    "required": {"type": ["boolean", "null"]},
                    "max_length": {"type": ["integer", "null"]},
                    "quote": {"type": "string"},
                },
                "required": [
                    "name",
                    "screen_name",
                    "field_type",
                    "required",
                    "max_length",
                    "quote",
                ],
                "additionalProperties": False,
            },
        },
        "rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["calculation", "limit", "permission", "other"],
                    },
                    "description": {"type": "string"},
                    "screen_name": {"type": "string"},
                    "field_name": {"type": "string"},
                    "expression": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": [
                    "kind",
                    "description",
                    "screen_name",
                    "field_name",
                    "expression",
                    "quote",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["screens", "fields", "rules"],
    "additionalProperties": False,
}

_UNKNOWN_SCREEN_NOTE = "画面参照を文書内で確認できず"
_CONFIDENCE_EXACT = 0.9
_CONFIDENCE_NORMALIZED = 0.7


def _normalize_quote(text: str) -> str:
    """全角/半角・空白揺れを吸収した比較用文字列に正規化する。"""
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(normalized.split())


def _locate_quote(quote: str, lines: list[tuple[str, str]]) -> tuple[str, float] | None:
    """quote が原文行のどこにあるかを逆引きし、(location, confidence) を返す。

    完全一致（正規化前の文字列同士でも部分一致）なら confidence 0.9、
    正規化後にのみ一致するなら 0.7。どちらでも見つからなければ None。
    """
    stripped = quote.strip()
    if not stripped:
        return None
    for location, text in lines:
        if stripped in text:
            return location, _CONFIDENCE_EXACT
    normalized_quote = _normalize_quote(quote)
    if not normalized_quote:
        return None
    for location, text in lines:
        if normalized_quote in _normalize_quote(text):
            return location, _CONFIDENCE_NORMALIZED
    return None


def filter_hallucinations(
    payload: dict[str, Any],
    lines: list[tuple[str, str]],
    source_file: str,
    known_screens: Iterable[str] = (),
) -> tuple[list[DocumentedScreen], list[DocumentedField], list[DocumentedRule]]:
    """quote を原文行から逆引きし、見つからない項目を破棄する。

    location は LLM 出力を信用せず、quote が最初に見つかった行の
    location を採用する。known_screens は同一文書内の表由来画面名
    （呼び出し側が把握している既知画面）。LLM 抽出画面に加えてこれらの
    名称も「確認できる画面参照」として扱う。
    """
    screens: list[DocumentedScreen] = []
    fields: list[DocumentedField] = []
    rules: list[DocumentedRule] = []

    for index, raw in enumerate(payload.get("screens") or []):
        quote = str(raw.get("quote") or "")
        located = _locate_quote(quote, lines)
        if located is None:
            logger.warning("幻覚の疑いで破棄: %s / %s", raw.get("name"), quote[:40])
            continue
        location, confidence = located
        screens.append(
            DocumentedScreen(
                screen_id=f"LLM-{source_file}-S{index + 1}",
                name=str(raw.get("name") or ""),
                url_hint=str(raw.get("url_hint") or ""),
                source="llm",
                confidence=confidence,
                evidence=DocumentEvidence(file=source_file, location=location, quote=quote),
            )
        )

    known_screen_names = {s.name for s in screens} | {str(name) for name in known_screens}

    for raw in payload.get("fields") or []:
        quote = str(raw.get("quote") or "")
        located = _locate_quote(quote, lines)
        if located is None:
            logger.warning("幻覚の疑いで破棄: %s / %s", raw.get("name"), quote[:40])
            continue
        location, confidence = located
        screen_name = str(raw.get("screen_name") or "")
        note = ""
        if screen_name and screen_name not in known_screen_names:
            note = _UNKNOWN_SCREEN_NOTE
            screen_name = ""
        fields.append(
            DocumentedField(
                name=str(raw.get("name") or ""),
                screen_name=screen_name,
                field_type=str(raw.get("field_type") or ""),
                required=raw.get("required"),
                max_length=raw.get("max_length"),
                note=note,
                source="llm",
                confidence=confidence,
                evidence=DocumentEvidence(file=source_file, location=location, quote=quote),
            )
        )

    for index, raw in enumerate(payload.get("rules") or []):
        quote = str(raw.get("quote") or "")
        located = _locate_quote(quote, lines)
        if located is None:
            logger.warning("幻覚の疑いで破棄: %s / %s", raw.get("kind"), quote[:40])
            continue
        location, confidence = located
        screen_name = str(raw.get("screen_name") or "")
        description = str(raw.get("description") or "")
        if screen_name and screen_name not in known_screen_names:
            description = f"{description}（{_UNKNOWN_SCREEN_NOTE}）"
            screen_name = ""
        rules.append(
            DocumentedRule(
                rule_id=f"RULE-{index + 1:03d}",
                kind=str(raw.get("kind") or "other"),
                description=description,
                screen_name=screen_name,
                field_name=str(raw.get("field_name") or ""),
                expression=str(raw.get("expression") or ""),
                confidence=confidence,
                evidence=DocumentEvidence(file=source_file, location=location, quote=quote),
            )
        )

    return screens, fields, rules


def extract_semantics(
    lines: list[tuple[str, str]],
    source_file: str,
    provider: LLMProvider,
    known_screens: Iterable[str] = (),
) -> tuple[list[DocumentedScreen], list[DocumentedField], list[DocumentedRule]]:
    """自由文行から LLM で画面・項目・ルールを抽出する。

    失敗・キーなし（RulesProvider の空応答）は空 3-tuple を返す。
    known_screens は同一文書の表由来画面名（screen_name 検証に使う）。
    """
    if not lines:
        logger.info("テキストが抽出できないため LLM 抽出をスキップします: %s", source_file)
        return [], [], []
    try:
        payload = provider.extract_document_semantics(lines, source_file)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 抽出応答を棄却しました（理由: %s）", exc)
        return [], [], []
    if not payload.get("screens") and not payload.get("fields") and not payload.get("rules"):
        return [], [], []
    return filter_hallucinations(payload, lines, source_file, known_screens)
