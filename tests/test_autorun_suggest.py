"""段階へのLLM提案（補助）のテスト。

**LLM は補助であり必須ではない**という契約を固定する。
到達できない場合も例外にせず、段階の内容に影響しないこと。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import autorun.suggest as suggest_mod
from autorun.suggest import suggest_additions
from llm.openai_client import LLMResponseError, LLMUnavailableError


class _Endpoint:
    def __init__(self, api_key: str = "local") -> None:
        self.api_key = api_key
        self.model = "test-model"
        self.base_url = "http://127.0.0.1:11434/v1"


@pytest.fixture()
def endpoint(monkeypatch):
    monkeypatch.setattr(suggest_mod, "resolve_endpoint", lambda: _Endpoint())


class TestUnavailableLLM:
    """LLM が無くても段階は成立する。"""

    def test_missing_api_key_is_not_an_error(self, monkeypatch) -> None:
        monkeypatch.setattr(suggest_mod, "resolve_endpoint", lambda: _Endpoint(api_key=""))
        result = suggest_additions("テスト目的", "目的を定める", "画面 3", [])
        assert result.available is False
        assert result.suggestions == ()
        assert "ルールベース" in result.message

    def test_unreachable_llm_returns_empty_not_exception(self, endpoint, monkeypatch) -> None:
        def boom(**_kwargs):
            raise LLMUnavailableError("接続できません")

        monkeypatch.setattr(suggest_mod, "request_structured_json", boom)
        result = suggest_additions("テスト観点分析", "観点を洗い出す", "画面 3", ["表示"])
        assert result.available is False
        assert result.suggestions == ()
        assert "影響しません" in result.message

    def test_malformed_response_is_handled(self, endpoint, monkeypatch) -> None:
        def boom(**_kwargs):
            raise LLMResponseError("JSON ではありません")

        monkeypatch.setattr(suggest_mod, "request_structured_json", boom)
        result = suggest_additions("テスト設計", "技法を決める", "画面 3", [])
        assert result.available is False


class TestSuggestions:
    def test_parses_suggestions(self, endpoint, monkeypatch) -> None:
        monkeypatch.setattr(
            suggest_mod,
            "request_structured_json",
            lambda **_k: {
                "suggestions": [
                    {"title": "セッション期限切れ", "detail": "期限切れ後の操作", "reason": "推測"},
                    {"title": "二重送信", "detail": "連打時の挙動", "reason": "フォームがある"},
                ]
            },
        )
        result = suggest_additions("テスト観点分析", "観点を洗い出す", "画面 3", ["表示"])
        assert result.available is True
        assert [s.title for s in result.suggestions] == ["セッション期限切れ", "二重送信"]

    def test_caps_the_number_of_suggestions(self, endpoint, monkeypatch) -> None:
        many = [{"title": f"候補{i}", "detail": "", "reason": ""} for i in range(20)]
        monkeypatch.setattr(
            suggest_mod, "request_structured_json", lambda **_k: {"suggestions": many}
        )
        result = suggest_additions("観点", "洗い出す", "画面 3", [])
        assert len(result.suggestions) == suggest_mod.MAX_SUGGESTIONS

    def test_drops_entries_without_title(self, endpoint, monkeypatch) -> None:
        monkeypatch.setattr(
            suggest_mod,
            "request_structured_json",
            lambda **_k: {"suggestions": [{"title": "  ", "detail": "x", "reason": ""},
                                          {"title": "有効", "detail": "", "reason": ""}]},
        )
        result = suggest_additions("観点", "洗い出す", "画面 3", [])
        assert [s.title for s in result.suggestions] == ["有効"]

    def test_empty_result_does_not_claim_completeness(self, endpoint, monkeypatch) -> None:
        """「候補なし」は「抜けが無い」ことの証明ではない。"""
        monkeypatch.setattr(
            suggest_mod, "request_structured_json", lambda **_k: {"suggestions": []}
        )
        result = suggest_additions("観点", "洗い出す", "画面 3", ["表示"])
        assert result.available is True
        assert "証明ではありません" in result.message

    def test_prompt_includes_existing_titles_to_avoid_duplicates(self, endpoint, monkeypatch) -> None:
        captured = {}

        def capture(**kwargs):
            captured.update(kwargs)
            return {"suggestions": []}

        monkeypatch.setattr(suggest_mod, "request_structured_json", capture)
        suggest_additions("観点", "洗い出す", "画面 3", ["既存の観点A"])
        assert "既存の観点A" in captured["prompt"]
        assert "含まれていない" in captured["prompt"]
