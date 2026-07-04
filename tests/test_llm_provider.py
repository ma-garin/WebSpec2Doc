from __future__ import annotations

import pytest

from llm.provider import LLMProvider, OpenAIProvider, RulesProvider
from ux.heuristics import pop_hallucination_drop_count


def test_rules_provider_is_llmprovider() -> None:
    assert isinstance(RulesProvider(), LLMProvider)


def test_rules_provider_generate_viewpoints_returns_list() -> None:
    from llm.screen_classifier import SCREEN_FORM, ScreenClassification

    classification = ScreenClassification(SCREEN_FORM, 0.9, (), "medium")
    result = RulesProvider().generate_viewpoints(
        {"screen_classification": classification, "fields": []}
    )

    assert isinstance(result, list)
    assert all("category" in viewpoint and "source" in viewpoint for viewpoint in result)


def test_rules_provider_generate_viewpoints_source_is_rules() -> None:
    result = RulesProvider().generate_viewpoints({})

    assert all(viewpoint["source"] == "rules" for viewpoint in result)


def test_rules_provider_qa_process_raises() -> None:
    with pytest.raises(NotImplementedError):
        RulesProvider().generate_qa_process("example.com", {})


def test_openai_provider_raises_on_empty_key() -> None:
    with pytest.raises(ValueError):
        OpenAIProvider("")


def test_make_provider_returns_rules_without_key() -> None:
    from llm.viewpoint_generator import make_provider

    assert isinstance(make_provider(""), RulesProvider)


def test_make_provider_returns_openai_with_key() -> None:
    from llm.viewpoint_generator import make_provider

    assert isinstance(make_provider("sk-test-key"), OpenAIProvider)


# ---------- SPEC-3-4: generate_ux_review ----------


def _unlabeled_field_screen_info() -> dict:
    from crawler.page_crawler import SourceEvidence, evidence_to_dict

    return {
        "title": "画面",
        "headings": ["画面"],
        "fields": [
            {
                "name": "unlabeled",
                "has_visible_label": False,
                "aria_label": "",
                "placeholder": "",
                "required": False,
                "aria_required": False,
                "evidence": evidence_to_dict(SourceEvidence(selector="[name='unlabeled']")),
            }
        ],
        "buttons": [],
        "axe_violation_summary": [],
        "known_selectors": ["[name='unlabeled']"],
    }


class TestGenerateUxReview:
    def test_rules_provider_generate_ux_review_returns_rules_source(self) -> None:
        """RulesProvider は OPENAI キーなし相当で evidence 付き rules 所見を返す（AC-5）。"""
        result = RulesProvider().generate_ux_review(_unlabeled_field_screen_info())

        assert result
        assert all(item["source"] == "rules" for item in result)
        assert all(item["confidence"] == 1.0 for item in result)
        assert all(item["evidence"] is not None for item in result)

    def test_openai_provider_generate_ux_review_schema_violation_falls_back_to_rules(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """スキーマ違反の LLM 応答は全棄却され RulesProvider にフォールバックする（AC-4, 5）。"""
        import llm.openai_client as openai_client_module

        def _bad_request(*_args: object, **_kwargs: object) -> dict:
            return {"unexpected": "structure"}

        monkeypatch.setattr(openai_client_module, "request_structured_json", _bad_request)

        provider = OpenAIProvider("sk-test-key")
        result = provider.generate_ux_review(_unlabeled_field_screen_info())

        assert result
        assert all(item["source"] == "rules" for item in result)

    def test_openai_provider_generate_ux_review_drops_hallucinated_selector(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """known_selectors に無い selector を含む LLM 応答は、その 1 件だけ破棄する（AC-4）。"""
        pop_hallucination_drop_count()

        def _fake_request(*_args: object, **_kwargs: object) -> dict:
            return {
                "findings": [
                    {
                        "principle": "N6",
                        "severity": "high",
                        "finding": "実在するセレクタに基づく所見",
                        "selector": "[name='unlabeled']",
                    },
                    {
                        "principle": "N1",
                        "severity": "low",
                        "finding": "存在しないセレクタに基づく幻覚所見",
                        "selector": "#does-not-exist",
                    },
                ]
            }

        import llm.openai_client as openai_client_module

        monkeypatch.setattr(openai_client_module, "request_structured_json", _fake_request)

        provider = OpenAIProvider("sk-test-key")
        result = provider.generate_ux_review(_unlabeled_field_screen_info())

        assert len(result) == 1
        assert result[0]["evidence"]["selector"] == "[name='unlabeled']"
        assert all(item["source"] == "openai" for item in result)
        assert all(item["confidence"] <= 0.9 for item in result)
        assert pop_hallucination_drop_count() == 1
