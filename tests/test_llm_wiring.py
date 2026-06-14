from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from web.services.qa.helpers import _load_qa_viewpoints

from llm.provider import OpenAIProvider, RulesProvider


def test_make_provider_called_with_empty_key_returns_rules() -> None:
    from llm.viewpoint_generator import make_provider

    assert isinstance(make_provider(""), RulesProvider)


def test_rules_provider_generate_viewpoints_no_api_call() -> None:
    with patch("urllib.request.urlopen") as mock_urlopen:
        result = RulesProvider().generate_viewpoints({})

    mock_urlopen.assert_not_called()
    assert isinstance(result, list)


def test_openai_provider_generate_viewpoints_calls_api() -> None:
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(
        {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "viewpoints": [
                                    {
                                        "category": "機能",
                                        "viewpoint": "テスト",
                                        "risk_level": "低",
                                        "example_cases": [],
                                    }
                                ]
                            }
                        )
                    }
                }
            ]
        }
    ).encode()
    mock_response.__enter__ = lambda response: response
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = OpenAIProvider("sk-test-key").generate_viewpoints({"screen_info": {}})

    assert len(result) == 1
    assert result[0]["source"] == "openai"


def test_load_qa_viewpoints_adds_provider_results() -> None:
    provider = MagicMock()
    provider.generate_viewpoints.return_value = [
        {
            "category": "機能",
            "viewpoint": "プロバイダ観点",
            "risk_level": "低",
            "example_cases": [],
            "source": "rules",
        }
    ]
    report = {
        "screens": [
            {
                "page_id": "SCR-001",
                "title": "入力画面",
                "url": "https://example.com/form",
                "forms": [{"fields": [{"name": "email", "required": True}]}],
            }
        ]
    }

    result = _load_qa_viewpoints("example.com", report, provider=provider)

    provider.generate_viewpoints.assert_called_once()
    assert any(item.get("name") == "プロバイダ観点" for item in result)
