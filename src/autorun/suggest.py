"""段階の内容に対する LLM 提案（補助）。

**ルールベースの生成が主で、LLM は補助**という分担を崩さない。
LLM は「既存項目に足りていない候補」だけを出し、既存項目を書き換えない。
LLM が使えない環境でも段階は成立するため、失敗は例外ではなく空の結果で返す。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from llm.openai_client import (
    LLMResponseError,
    LLMUnavailableError,
    request_structured_json,
    resolve_endpoint,
)

logger = logging.getLogger(__name__)

MAX_SUGGESTIONS = 5
MAX_EXISTING_SHOWN = 20
TIMEOUT_SEC = 120

SUGGESTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["title", "detail", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["suggestions"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Suggestion:
    """LLM が提案した追加候補。採用は人間が判断する。"""

    title: str
    detail: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"title": self.title, "detail": self.detail, "reason": self.reason}


@dataclass(frozen=True)
class SuggestionResult:
    suggestions: tuple[Suggestion, ...] = ()
    available: bool = True
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggestions": [s.to_dict() for s in self.suggestions],
            "available": self.available,
            "message": self.message,
        }


def _prompt(stage_name: str, purpose: str, context: str, existing: list[str]) -> str:
    listed = "\n".join(f"- {t}" for t in existing[:MAX_EXISTING_SHOWN]) or "（まだ無し）"
    return (
        "あなたはベテランQAエンジニアです。日本語で答えてください。\n\n"
        f"# 現在の段階\n{stage_name}: {purpose}\n\n"
        f"# 対象の観測結果\n{context}\n\n"
        f"# すでに挙がっている項目\n{listed}\n\n"
        "# 依頼\n"
        f"すでに挙がっている項目に**含まれていない**追加候補を、最大 {MAX_SUGGESTIONS} 件挙げてください。\n"
        "制約:\n"
        "- 既存項目の言い換えは出さない。本当に抜けているものだけを出す。\n"
        "- 観測結果から言えないことは断定せず、推測は reason に「推測」と明記する。\n"
        "- テスト設計に関わる場合は ISTQB の技法名（同値分割・境界値分析・"
        "デシジョンテーブル・状態遷移・組合せ）を使う。\n"
        "- 抜けが無いと判断したら suggestions を空配列にする。"
    )


def suggest_additions(
    stage_name: str,
    purpose: str,
    context: str,
    existing_titles: list[str],
) -> SuggestionResult:
    """段階に対する追加候補を LLM に問い合わせる。

    LLM が使えない場合も例外にせず、`available=False` で返す。
    呼び出し側はルールベースの結果だけで先へ進める。
    """
    endpoint = resolve_endpoint()
    if not endpoint.api_key:
        return SuggestionResult(
            available=False,
            message="LLM の接続先が未設定のため、提案は利用できません。ルールベースの内容はそのまま使えます。",
        )

    try:
        data = request_structured_json(
            api_key=endpoint.api_key,
            model=endpoint.model,
            prompt=_prompt(stage_name, purpose, context, existing_titles),
            schema_name="stage_suggestions",
            json_schema=SUGGESTION_SCHEMA,
            timeout_sec=TIMEOUT_SEC,
            base_url=endpoint.base_url,
        )
    except LLMUnavailableError as exc:
        logger.info("LLM 提案に到達できません: %s", exc)
        return SuggestionResult(
            available=False,
            message="QAアシスタントに接続できませんでした。提案は補助であり、段階の内容には影響しません。",
        )
    except LLMResponseError as exc:
        logger.info("LLM 提案の応答が不正: %s", exc)
        return SuggestionResult(
            available=False,
            message="提案を解釈できませんでした。ルールベースの内容はそのまま使えます。",
        )

    raw = data.get("suggestions")
    items: list[Suggestion] = []
    if isinstance(raw, list):
        for entry in raw[:MAX_SUGGESTIONS]:
            if not isinstance(entry, dict):
                continue
            title = str(entry.get("title", "")).strip()
            if not title:
                continue
            items.append(
                Suggestion(
                    title=title,
                    detail=str(entry.get("detail", "")).strip(),
                    reason=str(entry.get("reason", "")).strip(),
                )
            )

    message = "" if items else "追加の候補は挙がりませんでした（抜けが無いという証明ではありません）。"
    return SuggestionResult(suggestions=tuple(items), message=message)
