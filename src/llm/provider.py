from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


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


def _screen_evidence_from_info(screen_info: dict[str, Any]) -> Any:
    """screen_info から画面全体の根拠（SourceEvidence）を構築する。"""
    from crawler.page_crawler import SourceEvidence

    raw_shot = screen_info.get("screenshot_path")
    return SourceEvidence(
        selector="body",
        html_attribute=None,
        screenshot_path=str(raw_shot) if raw_shot else None,
        bbox=None,
    )


def _viewpoint_dicts(viewpoints: list[Any], source: str) -> list[dict[str, Any]]:
    """TestViewpoint リストを dict に変換する。evidence なしの観点は出力しない。"""
    from crawler.page_crawler import evidence_to_dict

    results: list[dict[str, Any]] = []
    for viewpoint in viewpoints:
        if viewpoint.evidence is None:
            logger.warning(
                "根拠（evidence）のない観点を出力から除外しました: %s", viewpoint.viewpoint
            )
            continue
        results.append(
            {
                "category": viewpoint.category,
                "viewpoint": viewpoint.viewpoint,
                "risk_level": viewpoint.risk_level,
                "example_cases": list(viewpoint.example_cases),
                "source": source,
                "confidence": viewpoint.confidence,
                "evidence": evidence_to_dict(viewpoint.evidence),
            }
        )
    return results


class RulesProvider:
    """外部 API を使わない決定的なプロバイダ。"""

    def generate_viewpoints(self, screen_info: dict[str, Any]) -> list[dict[str, Any]]:
        from crawler.page_crawler import evidence_from_dict
        from llm.viewpoint_generator import (
            fallback_classification,
            generate_viewpoints_by_rules,
        )

        classification = fallback_classification(screen_info)
        fields = [
            (
                SimpleNamespace(
                    required=bool(field.get("required")),
                    maxlength=field.get("maxlength"),
                    name=str(field.get("name") or ""),
                    evidence=evidence_from_dict(field.get("evidence")),
                )
                if isinstance(field, dict)
                else field
            )
            for field in screen_info.get("fields", [])
        ]
        viewpoints = generate_viewpoints_by_rules(
            classification,
            fields,
            screen_evidence=_screen_evidence_from_info(screen_info),
        )
        return _viewpoint_dicts(viewpoints, source="rules")

    def generate_qa_process(
        self,
        domain: str,
        report: dict[str, Any],
        viewpoints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError("QA プロセス生成には OpenAIProvider が必要です。")


class OpenAIProvider:
    """OpenAI API を利用するプロバイダ（Structured Outputs / JSON Schema strict）。

    スキーマ違反・カテゴリ不正の応答は棄却して RulesProvider へフォールバックし、
    棄却理由をログに記録する。
    """

    def __init__(self, api_key: str, model: str = "") -> None:
        if not api_key:
            raise ValueError("api_key は空にできません。")
        from llm.screen_classifier import _LLM_MODEL

        self._api_key = api_key
        self._model = model or _LLM_MODEL

    def generate_viewpoints(self, screen_info: dict[str, Any]) -> list[dict[str, Any]]:
        from crawler.page_crawler import evidence_to_dict
        from llm.openai_client import LLMResponseError, request_structured_json
        from llm.screen_classifier import ScreenClassification
        from llm.viewpoint_generator import (
            VIEWPOINT_JSON_SCHEMA,
            VIEWPOINT_SCHEMA_NAME,
            ViewpointValidationError,
            build_viewpoint_prompt,
            llm_viewpoint_confidence,
            validate_viewpoint_payload,
        )

        payload = dict(screen_info)
        classification = payload.get("screen_classification")
        if isinstance(classification, ScreenClassification):
            payload["screen_classification"] = {
                "screen_type": classification.screen_type,
                "confidence": classification.confidence,
                "keywords": list(classification.keywords),
                "test_priority": classification.test_priority,
            }
        prompt = build_viewpoint_prompt(payload)
        try:
            raw = request_structured_json(
                self._api_key,
                self._model,
                prompt,
                VIEWPOINT_SCHEMA_NAME,
                VIEWPOINT_JSON_SCHEMA,
            )
            items = validate_viewpoint_payload(raw)
        except (ViewpointValidationError, LLMResponseError) as exc:
            logger.warning(
                "LLM 観点応答を棄却しました（理由: %s）。RulesProvider にフォールバックします。",
                exc,
            )
            return RulesProvider().generate_viewpoints(screen_info)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "LLM 呼び出しに失敗しました（%s）。RulesProvider にフォールバックします。", exc
            )
            return RulesProvider().generate_viewpoints(screen_info)

        screen_evidence = _screen_evidence_from_info(screen_info)
        return [
            {
                "category": str(item["category"]),
                "viewpoint": str(item["viewpoint"]),
                "risk_level": str(item["risk_level"]),
                "example_cases": [str(c) for c in item.get("example_cases", [])],
                "source": "openai",
                "confidence": llm_viewpoint_confidence(item),
                "evidence": evidence_to_dict(screen_evidence),
            }
            for item in items
        ]

    def generate_qa_process(
        self,
        domain: str,
        report: dict[str, Any],
        viewpoints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        from web.services.openai_qa import generate_openai_qa

        return generate_openai_qa(domain, report, viewpoints)
