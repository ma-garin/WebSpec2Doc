from __future__ import annotations

import json
from typing import Any

from web.services.openai_qa import call_structured

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
    system = (
        "あなたはWebアプリケーションのリスクベーステスト設計者です。"
        "入力コンテキストに必要で、既存観点と重複しない観点だけを提案してください。"
        "ISO/IEC 25010:2023の品質特性と、リスクの発生確率・影響度を根拠に優先度を決めてください。"
        "推測した業務ルールは断定せず、確認可能な表現にしてください。"
        "出力は提案であり、保存や公開を指示してはいけません。"
    )
    result, _model = call_structured(
        system,
        json.dumps(
            {"context": safe_context, "existing_viewpoints": safe_existing}, ensure_ascii=False
        ),
        "viewpoint_proposals",
        PROPOSAL_SCHEMA,
        max_tokens=4096,
    )
    proposals = result.get("proposals", [])
    return [item for item in proposals if isinstance(item, dict)]
