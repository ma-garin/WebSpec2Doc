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

    def extract_document_semantics(
        self, lines: list[tuple[str, str]], source_file: str
    ) -> dict[str, Any]: ...

    def generate_ux_review(self, screen_info: dict[str, Any]) -> list[dict[str, Any]]: ...


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

    def extract_document_semantics(
        self, lines: list[tuple[str, str]], source_file: str
    ) -> dict[str, Any]:
        logger.info("LLM 抽出は無効です（Phase 1 抽出のみで継続）: %s", source_file)
        return {"screens": [], "fields": [], "rules": [], "requirements": []}

    def generate_ux_review(self, screen_info: dict[str, Any]) -> list[dict[str, Any]]:
        from ux.heuristics import generate_ux_findings_by_rules, ux_finding_to_dict

        findings = generate_ux_findings_by_rules(screen_info)
        return [ux_finding_to_dict(finding) for finding in findings]


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
                purpose="viewpoints",
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

    def extract_document_semantics(
        self, lines: list[tuple[str, str]], source_file: str
    ) -> dict[str, Any]:
        from ingest.llm_extractor import EXTRACTION_JSON_SCHEMA, EXTRACTION_SCHEMA_NAME
        from llm.openai_client import LLMResponseError, request_structured_json

        prompt = (
            "あなたは文書解析の専門家です。以下は文書（"
            f"{source_file}）から抽出したテキスト行です。各行は "
            "[位置] テキスト の形式です。\n\n"
            + "\n".join(f"[{location}] {text}" for location, text in lines)
            + "\n\n"
            "この文書に書かれている画面・入力項目・業務ルール（計算式・限度値・"
            "権限条件）・要件（RFP や要件一覧に記載された、実現すべき機能/非機能の"
            "記述）を抽出してください。"
            "文書に書かれていないことを推測で補完しないこと。"
            "各項目には、抽出根拠となった原文をそのまま quote に含めること。"
        )
        try:
            return request_structured_json(
                self._api_key,
                self._model,
                prompt,
                EXTRACTION_SCHEMA_NAME,
                EXTRACTION_JSON_SCHEMA,
                purpose="document_extract",
            )
        except LLMResponseError as exc:
            logger.warning("LLM 抽出応答を棄却しました（理由: %s）", exc)
            return {"screens": [], "fields": [], "rules": [], "requirements": []}

    def generate_ux_review(self, screen_info: dict[str, Any]) -> list[dict[str, Any]]:
        from crawler.page_crawler import SourceEvidence, evidence_to_dict
        from llm.openai_client import LLMResponseError, request_structured_json
        from ux.heuristics import (
            LLM_UX_CONFIDENCE,
            UX_REVIEW_JSON_SCHEMA,
            UX_REVIEW_SCHEMA_NAME,
            UxReviewValidationError,
            build_ux_review_prompt,
            filter_hallucinated_findings,
            validate_ux_payload,
        )

        known_selectors = {str(s) for s in screen_info.get("known_selectors", [])}
        prompt = build_ux_review_prompt(screen_info)
        try:
            raw = request_structured_json(
                self._api_key,
                self._model,
                prompt,
                UX_REVIEW_SCHEMA_NAME,
                UX_REVIEW_JSON_SCHEMA,
                purpose="ux_review",
            )
            items = validate_ux_payload(raw)
        except (UxReviewValidationError, LLMResponseError) as exc:
            logger.warning(
                "LLM UX 所見応答を棄却しました（理由: %s）。RulesProvider にフォールバックします。",
                exc,
            )
            return RulesProvider().generate_ux_review(screen_info)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "LLM 呼び出しに失敗しました（%s）。RulesProvider にフォールバックします。", exc
            )
            return RulesProvider().generate_ux_review(screen_info)

        kept = filter_hallucinated_findings(items, known_selectors)
        screenshot_path = screen_info.get("screenshot_path")
        return [
            {
                "principle": str(item["principle"]),
                "severity": str(item["severity"]),
                "finding": str(item["finding"]),
                "evidence": evidence_to_dict(
                    SourceEvidence(
                        selector=str(item["selector"]),
                        screenshot_path=str(screenshot_path) if screenshot_path else None,
                    )
                ),
                "source": "openai",
                "confidence": LLM_UX_CONFIDENCE,
            }
            for item in kept
        ]
