from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from web.config import DEFAULT_OPENAI_MODEL
from web.env_store import _read_env
from web.services.openai_qa import (
    OPENAI_RESPONSES_URL,
    OpenAIQAError,
    _extract_output_text,
    _openai_headers,
)

PROPOSAL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["proposals"],
    "properties": {
        "proposals": {
            "type": "array",
            "maxItems": 10,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "name",
                    "category",
                    "purpose",
                    "recommended_checks",
                    "risk_weight",
                    "automation",
                    "standards",
                    "tags",
                    "rationale",
                    "confidence",
                ],
                "properties": {
                    "name": {"type": "string"},
                    "category": {"type": "string"},
                    "purpose": {"type": "string"},
                    "recommended_checks": {"type": "string"},
                    "risk_weight": {"type": "integer", "minimum": 1, "maximum": 5},
                    "automation": {
                        "type": "string",
                        "enum": ["automated", "semi_automated", "manual"],
                    },
                    "standards": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "rationale": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        }
    },
}


def generate_viewpoint_proposals(
    context: dict[str, Any], existing_items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """AI出力を提案として返す。DBへの保存・公開は呼び出し側で明示的に行う。"""
    env = _read_env()
    api_key = env.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise OpenAIQAError("OPENAI_API_KEY が設定されていません。")
    model = env.get("OPENAI_MODEL", "").strip() or DEFAULT_OPENAI_MODEL
    safe_existing = [
        {
            "persistent_key": str(item.get("persistent_key", ""))[:100],
            "name": str(item.get("name", ""))[:200],
            "category": str(item.get("category", ""))[:100],
        }
        for item in existing_items[:200]
    ]
    safe_context = {
        "url": str(context.get("url", ""))[:500],
        "industry": str(context.get("industry", ""))[:200],
        "screen_types": [str(value)[:100] for value in context.get("screen_types", [])[:30]],
        "notes": str(context.get("notes", ""))[:2000],
    }
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "あなたはWebアプリケーションのリスクベーステスト設計者です。"
                    "入力コンテキストに必要で、既存観点と重複しない観点だけを提案してください。"
                    "ISO/IEC 25010:2023の品質特性と、リスクの発生確率・影響度を根拠に優先度を決めてください。"
                    "推測した業務ルールは断定せず、確認可能な表現にしてください。"
                    "出力は提案であり、保存や公開を指示してはいけません。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"context": safe_context, "existing_viewpoints": safe_existing},
                    ensure_ascii=False,
                ),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "viewpoint_proposals",
                "strict": True,
                "schema": PROPOSAL_SCHEMA,
            }
        },
    }
    req = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=_openai_headers(api_key, env),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:  # nosec B310
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise OpenAIQAError(f"OpenAI API error: HTTP {exc.code} {body[:300]}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OpenAIQAError(f"OpenAI API request failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise OpenAIQAError("OpenAI API response is not valid JSON.") from exc
    text = _extract_output_text(response_data)
    if not text:
        raise OpenAIQAError("OpenAI API response did not include output text.")
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OpenAIQAError("AI提案がJSONではありません。") from exc
    proposals = result.get("proposals", []) if isinstance(result, dict) else []
    return [item for item in proposals if isinstance(item, dict)]
