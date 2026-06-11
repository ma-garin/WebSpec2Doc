"""画面の業務コンテキストをルールまたは LLM で分類するモジュール。

LLM 版は OpenAI の gpt-4o-mini を使用し、API キーが不要な
ルールベース版にフォールバックする設計になっている。
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

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
_OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

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
    payload = {
        "model": _LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    request = urllib.request.Request(
        _OPENAI_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as resp:  # nosec B310
        data = json.loads(resp.read().decode("utf-8"))
    text = data["choices"][0]["message"]["content"]
    parsed = json.loads(text)
    return ScreenClassification(
        screen_type=str(parsed["screen_type"]),
        confidence=float(parsed["confidence"]),
        keywords=tuple(str(k) for k in parsed.get("keywords", [])),
        test_priority=str(parsed["test_priority"]),
    )


def _join_text(title: str, headings: tuple[str, ...], form_fields: list[str]) -> str:
    return " ".join([title, *headings, *form_fields])
