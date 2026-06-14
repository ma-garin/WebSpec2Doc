from __future__ import annotations

import pytest

from llm.provider import LLMProvider, OpenAIProvider, RulesProvider


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
