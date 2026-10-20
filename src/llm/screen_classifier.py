"""画面の業務コンテキストをルールまたは LLM で分類するモジュール。

LLM 版は OpenAI の gpt-4o-mini を使用し、API キーが不要な
ルールベース版にフォールバックする設計になっている。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from llm.openai_client import request_structured_json, resolve_endpoint

logger = logging.getLogger(__name__)

# 画面種別定数
SCREEN_PAYMENT = "payment"
SCREEN_PERSONAL_INFO = "personal_info"
SCREEN_AUTH = "auth"
SCREEN_SEARCH = "search"
SCREEN_LIST = "list"
SCREEN_FORM = "form"
SCREEN_GENERAL = "general"

_LLM_MODEL = "gpt-4o-mini"
_PRIORITIES = ("critical", "high", "medium", "low")
_SCREEN_TYPES = (
    SCREEN_PAYMENT,
    SCREEN_PERSONAL_INFO,
    SCREEN_AUTH,
    SCREEN_SEARCH,
    SCREEN_LIST,
    SCREEN_FORM,
    SCREEN_GENERAL,
)
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["screen_type", "confidence", "keywords", "test_priority"],
    "properties": {
        "screen_type": {"type": "string", "enum": list(_SCREEN_TYPES)},
        "confidence": {"type": "number"},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "test_priority": {"type": "string", "enum": list(_PRIORITIES)},
    },
}

# キーワードマップ: (screen_type, test_priority, keywords_tuple)
_RULE_TABLE: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        SCREEN_PAYMENT,
        "critical",
        ("決済", "支払", "payment", "クレジット", "カード", "課金", "billing"),
    ),
    (
        SCREEN_PERSONAL_INFO,
        "critical",
        ("個人情報", "マイナンバー", "住所", "プライバシー", "氏名", "生年月日", "privacy"),
    ),
    (
        SCREEN_AUTH,
        "critical",
        ("ログイン", "サインイン", "パスワード", "login", "signin", "password", "auth"),
    ),
    (
        SCREEN_SEARCH,
        "medium",
        ("検索", "search", "filter", "フィルター"),
    ),
)

_CONFIDENCE_MATCHED = 0.9
_CONFIDENCE_FALLBACK = 0.5


@dataclass(frozen=True)
class ScreenClassification:
    screen_type: str
    confidence: float
    keywords: tuple[str, ...]
    test_priority: str


def classify_screen_by_rules(
    title: str,
    headings: tuple[str, ...],
    form_fields: list[str],
) -> ScreenClassification:
    """LLM を使わないルールベース分類（オフライン動作）。"""
    all_text = _join_text(title, headings, form_fields)

    for screen_type, priority, candidates in _RULE_TABLE:
        matched = tuple(kw for kw in candidates if kw.lower() in all_text.lower())
        if matched:
            return ScreenClassification(
                screen_type=screen_type,
                confidence=_CONFIDENCE_MATCHED,
                keywords=matched,
                test_priority=priority,
            )

    # list: フィールド 1 件以下 かつ リスト系キーワード
    list_keywords = ("一覧", "リスト", "list", "index")
    if len(form_fields) <= 1:
        matched_list = tuple(kw for kw in list_keywords if kw.lower() in all_text.lower())
        if matched_list:
            return ScreenClassification(
                screen_type=SCREEN_LIST,
                confidence=_CONFIDENCE_MATCHED,
                keywords=matched_list,
                test_priority="medium",
            )

    # form: フィールド 2 件以上
    if len(form_fields) >= 2:
        return ScreenClassification(
            screen_type=SCREEN_FORM,
            confidence=_CONFIDENCE_MATCHED,
            keywords=(),
            test_priority="high",
        )

    return ScreenClassification(
        screen_type=SCREEN_GENERAL,
        confidence=_CONFIDENCE_FALLBACK,
        keywords=(),
        test_priority="low",
    )


def classify_screen_with_llm(
    title: str,
    headings: tuple[str, ...],
    form_fields: list[str],
    api_key: str,
) -> ScreenClassification:
    """OpenAI gpt-4o-mini で画面分類を行い、失敗時はルールベースへフォールバックする。"""
    try:
        return _call_llm(title, headings, form_fields, api_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM classification failed, falling back to rules: %s", exc)
        return classify_screen_by_rules(title, headings, form_fields)


def _call_llm(
    title: str,
    headings: tuple[str, ...],
    form_fields: list[str],
    api_key: str,
) -> ScreenClassification:
    prompt = (
        "あなたは QA エンジニアです。以下の Web 画面情報を分析して分類してください。\n"
        f"画面タイトル: {title}\n"
        f"見出し: {list(headings)}\n"
        f"フィールド名: {form_fields}\n\n"
        "以下の JSON で回答してください:\n"
        '{"screen_type": "payment/personal_info/auth/search/list/form/general のいずれか", '
        '"confidence": 0.0〜1.0, "keywords": ["...", ...], '
        '"test_priority": "critical/high/medium/low"}'
    )
    endpoint = resolve_endpoint()
    key = api_key or endpoint.api_key
    if not key:
        raise RuntimeError("LLM の接続先またはキーが未設定です。")
    model = endpoint.model if endpoint.is_local else _LLM_MODEL
    parsed = request_structured_json(
        key,
        model,
        prompt,
        "screen_classification",
        _SCHEMA,
        base_url=endpoint.base_url,
        purpose="screen_classifier",
    )
    screen_type = str(parsed["screen_type"])
    priority = str(parsed["test_priority"])
    if screen_type not in _SCREEN_TYPES or priority not in _PRIORITIES:
        raise ValueError(f"想定外の分類結果です: {screen_type}/{priority}")
    return ScreenClassification(
        screen_type=screen_type,
        confidence=float(parsed["confidence"]),
        keywords=tuple(str(k) for k in parsed.get("keywords", [])),
        test_priority=priority,
    )


def _join_text(title: str, headings: tuple[str, ...], form_fields: list[str]) -> str:
    return " ".join([title, *headings, *form_fields])
