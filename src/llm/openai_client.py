"""OpenAI API への HTTP 呼び出しを一元化するクライアントモジュール。

各生成モジュールが urllib を直叩きするのを避け、Structured Outputs
（JSON Schema strict）でのリクエスト構築・レスポンス解釈をここに集約する。
"""

from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_TIMEOUT_SEC = 30


class LLMResponseError(RuntimeError):
    """LLM 応答が不正（スキーマ違反・JSON 解釈不能など）であることを表す例外。"""


def request_structured_json(
    api_key: str,
    model: str,
    prompt: str,
    schema_name: str,
    json_schema: dict[str, Any],
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> dict[str, Any]:
    """Structured Outputs（JSON Schema strict）で OpenAI API を呼び出し、応答 JSON を返す。

    応答が JSON として解釈できない場合は ``LLMResponseError`` を送出する。
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": json_schema,
            },
        },
        "temperature": 0,
    }
    request = urllib.request.Request(
        OPENAI_CHAT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_sec) as resp:  # nosec B310
        data = json.loads(resp.read().decode("utf-8"))
    try:
        text = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMResponseError(f"LLM 応答の形式が不正です: {exc}") from exc
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMResponseError(f"LLM 応答を JSON として解釈できません: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMResponseError("LLM 応答のトップレベルが JSON オブジェクトではありません。")
    return parsed
