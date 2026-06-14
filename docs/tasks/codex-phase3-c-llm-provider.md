# タスク: Phase 3-C — LLMProvider 抽象インターフェースを実装する

## ゴール

`src/llm/provider.py` に `LLMProvider` Protocol を定義し、既存の OpenAI 呼び出しを
`OpenAIProvider` として実装する。
`viewpoint_generator.py` と `screen_classifier.py` がプロバイダを受け取れるよう拡張する。

**なぜ必要か**: 現在は OpenAI 固定。プロバイダ抽象を挟むことで
「Anthropic / ローカル LLM への差し替え」「テスト時のモック注入」が可能になる。
Phase 3-A（実配線）と Phase 3-B（バッジ）の前提。

---

## 触るファイル（これ以外は変更しない）

- `src/llm/provider.py` — 新規作成（Protocol + OpenAIProvider）
- `src/llm/viewpoint_generator.py` — プロバイダ受け取りに拡張
- `tests/test_llm_provider.py` — 新規テストファイル

**変更禁止**:
- `src/llm/screen_classifier.py`（今回は触らない。3-A で必要なら別タスクで）
- `web/services/openai_qa.py`（Flask 側は別タスク 3-A で変更）
- `src/llm/industry_template.py`
- git 操作（commit は Claude が行う）

---

## 既存コードの参照（必ず読んでから実装すること）

### `src/llm/viewpoint_generator.py`

- `generate_viewpoints_by_rules(screen_classification, field_data_list)` — ルールベース
- `generate_viewpoints_with_llm(screen_info, api_key)` — LLM 呼び出し（`api_key` 直接受け取り）
- `generate_abnormal_scenarios_with_llm(screen_classification, field_data_list, api_key)` — 異常系

### `src/llm/screen_classifier.py`

- `_LLM_MODEL`, `_OPENAI_CHAT_URL` 定数が定義されている（再利用する）

---

## 実装の指示

### 1. `src/llm/provider.py` を新規作成

```python
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """LLM プロバイダの抽象インターフェース。
    
    ルールベースフォールバックと OpenAI 実装の両方が満たすべき契約。
    """

    def generate_viewpoints(
        self,
        screen_info: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """テスト観点を生成して返す。
        
        Returns:
            各要素が category / viewpoint / risk_level / example_cases を持つリスト。
        """
        ...

    def generate_qa_process(
        self,
        domain: str,
        report: dict[str, Any],
        viewpoints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """QA プロセス全体（テスト計画〜レポート）を生成して返す。
        
        Returns:
            QA_ARTIFACT_SCHEMA に準拠した dict。
        """
        ...


class RulesProvider:
    """ルールベース（オフライン・無料）の LLMProvider 実装。
    
    API キーなしで動作する決定的な生成ロジック。
    """

    def generate_viewpoints(
        self,
        screen_info: dict[str, Any],
    ) -> list[dict[str, Any]]:
        from llm.viewpoint_generator import (
            generate_viewpoints_by_rules,
            ScreenClassification,
        )
        from llm.screen_classifier import SCREEN_GENERAL

        sc = screen_info.get("screen_classification")
        if not isinstance(sc, ScreenClassification):
            sc = ScreenClassification(SCREEN_GENERAL, 0.5, (), "low")
        fields = screen_info.get("fields", [])
        result = generate_viewpoints_by_rules(sc, fields)
        return [
            {
                "category": v.category,
                "viewpoint": v.viewpoint,
                "risk_level": v.risk_level,
                "example_cases": list(v.example_cases),
                "source": "rules",
            }
            for v in result
        ]

    def generate_qa_process(
        self,
        domain: str,
        report: dict[str, Any],
        viewpoints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """ルールベースでは QA プロセス全体生成は非対応（APIキー必須のため）。"""
        raise NotImplementedError("QA プロセス生成には OpenAIProvider が必要です。")


class OpenAIProvider:
    """OpenAI API を使う LLMProvider 実装。"""

    def __init__(self, api_key: str, model: str = "") -> None:
        if not api_key:
            raise ValueError("api_key は空にできません。")
        self._api_key = api_key
        from llm.screen_classifier import _LLM_MODEL
        self._model = model or _LLM_MODEL

    def generate_viewpoints(
        self,
        screen_info: dict[str, Any],
    ) -> list[dict[str, Any]]:
        from llm.viewpoint_generator import generate_viewpoints_with_llm

        result = generate_viewpoints_with_llm(screen_info, self._api_key)
        return [
            {
                "category": v.category,
                "viewpoint": v.viewpoint,
                "risk_level": v.risk_level,
                "example_cases": list(v.example_cases),
                "source": "openai",
            }
            for v in result
        ]

    def generate_qa_process(
        self,
        domain: str,
        report: dict[str, Any],
        viewpoints: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        from web.services.openai_qa import generate_openai_qa

        return generate_openai_qa(domain, report, viewpoints)
```

### 2. `src/llm/viewpoint_generator.py` への追記

ファイル末尾に以下のファクトリ関数を追加する（既存関数は変更しない）:

```python
def make_provider(api_key: str = "", model: str = "") -> "LLMProvider":
    """api_key の有無でプロバイダを選択して返すファクトリ。
    
    api_key が空なら RulesProvider（オフライン・無料）、
    あれば OpenAIProvider を返す。
    """
    from llm.provider import LLMProvider, OpenAIProvider, RulesProvider  # noqa: F401

    if api_key:
        return OpenAIProvider(api_key, model)
    return RulesProvider()
```

> 循環インポートを避けるため、`provider.py` は `viewpoint_generator.py` を `import` し、
> `viewpoint_generator.py` は `provider.py` を関数内でのみ `import` する。

---

## テストの指示（`tests/test_llm_provider.py`）

```python
from __future__ import annotations
import pytest
from llm.provider import RulesProvider, OpenAIProvider, LLMProvider


def test_rules_provider_is_llmprovider():
    assert isinstance(RulesProvider(), LLMProvider)


def test_rules_provider_generate_viewpoints_returns_list():
    from llm.screen_classifier import ScreenClassification, SCREEN_FORM
    sc = ScreenClassification(SCREEN_FORM, 0.9, (), "medium")
    provider = RulesProvider()
    result = provider.generate_viewpoints({"screen_classification": sc, "fields": []})
    assert isinstance(result, list)
    assert all("category" in v and "source" in v for v in result)


def test_rules_provider_generate_viewpoints_source_is_rules():
    provider = RulesProvider()
    result = provider.generate_viewpoints({})
    assert all(v["source"] == "rules" for v in result)


def test_rules_provider_qa_process_raises():
    with pytest.raises(NotImplementedError):
        RulesProvider().generate_qa_process("example.com", {})


def test_openai_provider_raises_on_empty_key():
    with pytest.raises(ValueError):
        OpenAIProvider("")


def test_make_provider_returns_rules_without_key():
    from llm.viewpoint_generator import make_provider
    p = make_provider("")
    assert isinstance(p, RulesProvider)


def test_make_provider_returns_openai_with_key():
    from llm.viewpoint_generator import make_provider
    p = make_provider("sk-test-key")
    assert isinstance(p, OpenAIProvider)
```

---

## 完了条件

- [ ] `src/llm/provider.py` が存在し、`LLMProvider` Protocol / `RulesProvider` / `OpenAIProvider` が定義されている
- [ ] `isinstance(RulesProvider(), LLMProvider)` が `True`
- [ ] `make_provider("")` が `RulesProvider` を返す
- [ ] `make_provider("sk-test")` が `OpenAIProvider` を返す
- [ ] `python -m pytest tests/test_llm_provider.py -v` が全 PASS
- [ ] `python -m pytest tests/ -q` が全 PASS（既存テスト影響なし）

---

## スコープ外（やらないこと）

- `web/services/openai_qa.py` の変更（3-A で行う）
- Anthropic / ローカル LLM の実装（インターフェース定義のみ）
- `screen_classifier.py` の変更
- git 操作
