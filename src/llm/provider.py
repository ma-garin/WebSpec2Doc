from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """テスト観点と QA プロセスを生成するプロバイダ契約。"""

    def generate_viewpoints(self, screen_info: dict[str, Any]) -> list[dict[str, Any]]: ...

    def generate_qa_process(
        self,
        domain: str,
        report: dict[str, Any],
        viewpoints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]: ...


class RulesProvider:
    """外部 API を使わない決定的なプロバイダ。"""

    def generate_viewpoints(self, screen_info: dict[str, Any]) -> list[dict[str, Any]]:
        from llm.screen_classifier import SCREEN_GENERAL, ScreenClassification
        from llm.viewpoint_generator import generate_viewpoints_by_rules

        classification = screen_info.get("screen_classification")
        if not isinstance(classification, ScreenClassification):
            classification = ScreenClassification(SCREEN_GENERAL, 0.5, (), "low")
        fields = [
            (
                SimpleNamespace(
                    required=bool(field.get("required")),
                    maxlength=field.get("maxlength"),
                )
                if isinstance(field, dict)
                else field
            )
            for field in screen_info.get("fields", [])
        ]
        return [
            {
                "category": viewpoint.category,
                "viewpoint": viewpoint.viewpoint,
                "risk_level": viewpoint.risk_level,
                "example_cases": list(viewpoint.example_cases),
                "source": "rules",
            }
            for viewpoint in generate_viewpoints_by_rules(classification, fields)
        ]

    def generate_qa_process(
        self,
        domain: str,
        report: dict[str, Any],
        viewpoints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError("QA プロセス生成には OpenAIProvider が必要です。")


class OpenAIProvider:
    """OpenAI API を利用するプロバイダ。"""

    def __init__(self, api_key: str, model: str = "") -> None:
        if not api_key:
            raise ValueError("api_key は空にできません。")
        from llm.screen_classifier import _LLM_MODEL

        self._api_key = api_key
        self._model = model or _LLM_MODEL

    def generate_viewpoints(self, screen_info: dict[str, Any]) -> list[dict[str, Any]]:
        from llm.screen_classifier import ScreenClassification
        from llm.viewpoint_generator import generate_viewpoints_with_llm

        payload = dict(screen_info)
        classification = payload.get("screen_classification")
        if isinstance(classification, ScreenClassification):
            payload["screen_classification"] = {
                "screen_type": classification.screen_type,
                "confidence": classification.confidence,
                "keywords": list(classification.keywords),
                "test_priority": classification.test_priority,
            }
        return [
            {
                "category": viewpoint.category,
                "viewpoint": viewpoint.viewpoint,
                "risk_level": viewpoint.risk_level,
                "example_cases": list(viewpoint.example_cases),
                "source": "openai",
            }
            for viewpoint in generate_viewpoints_with_llm(payload, self._api_key)
        ]

    def generate_qa_process(
        self,
        domain: str,
        report: dict[str, Any],
        viewpoints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        from web.services.openai_qa import generate_openai_qa

        return generate_openai_qa(domain, report, viewpoints)
