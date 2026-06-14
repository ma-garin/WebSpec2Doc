# タスク: Phase 3-A — LLM テスト観点生成を QA プロセスに実配線する

## ゴール

QA プロセスの「テスト分析」ステップで、`OPENAI_API_KEY` が設定されている場合に
`OpenAIProvider` を使って観点を生成し、`generate_openai_qa()` に渡す。
未設定の場合は `RulesProvider`（決定的・無料）にフォールバックする。

**なぜ必要か**: 現在の QA プロセスは `generate_openai_qa()` を呼ぶか否かが API キーの
有無で分岐しているが、LLM 観点カタログ（`qa_viewpoint_catalog`）が OpenAI に渡されていない。
観点を渡すことでテストケースの品質が大幅に向上する。

## 前提

- `codex-phase3-c-llm-provider.md` が完了していること（`LLMProvider` / `RulesProvider` / `OpenAIProvider` が存在）
- `src/llm/viewpoint_generator.py` に `make_provider()` が定義済みであること

## ⚠️ API キーが必要なテスト

`OPENAI_API_KEY` を使う統合テストは、**専用の API キー環境でのみ実行すること**。
この環境では `api_key=""` のフォールバックパス（ルールベース）のみテストする。
API 呼び出し部分はモックで代替する。

---

## 触るファイル（これ以外は変更しない）

- `web/services/qa/helpers.py` — `_load_qa_viewpoints()` を `LLMProvider` 経由に変更
- `web/routes/qa_process.py` — `generate` エンドポイントでプロバイダを選択して渡す
- `tests/test_llm_wiring.py` — 新規テスト（モック使用）

**変更禁止**:
- `web/services/openai_qa.py`（そのまま使う）
- `src/llm/viewpoint_generator.py`（Phase 3-C で対応済み）
- `src/llm/provider.py`（Phase 3-C で対応済み）
- git 操作（commit は Claude が行う）

---

## 既存コードの参照（必ず読んでから実装すること）

### `web/routes/qa_process.py`

`api_qa_process_generate()` の実装を読む:
- どのように `report` を読み込んでいるか
- `generate_openai_qa()` をどのタイミングで呼んでいるか
- `viewpoints` パラメータに何を渡しているか（おそらく `_load_qa_viewpoints()` の結果）

### `web/services/qa/helpers.py`

`_load_qa_viewpoints(domain, report)` の現在の実装を読む:
- どのようにテスト観点を生成・読み込みしているか
- 戻り値の型と構造

### `web/env_store.py`

`_read_env()` で `OPENAI_API_KEY` を読む方法は既存の `openai_qa.py` 参照。

---

## 実装の指示

### 1. `web/services/qa/helpers.py` の修正

`_load_qa_viewpoints(domain, report)` 関数に `provider` パラメータを追加:

```python
def _load_qa_viewpoints(
    domain: str,
    report: dict,
    provider=None,  # LLMProvider | None
) -> list[dict]:
    """テスト観点カタログを返す。provider がある場合はそれを使って生成する。"""
    # 既存の観点読み込みロジックを維持しつつ、provider が渡された場合は
    # report の最初の数画面から screen_info を組み立てて generate_viewpoints() を呼ぶ
    ...
```

> 具体的な実装は `helpers.py` の現在のコードを読んでから決定すること。
> 既存の動作（ファイル読み込み等）を壊さないよう、`provider` が `None` の場合は
> 現在と同じ動作を維持する。

### 2. `web/routes/qa_process.py` の `api_qa_process_generate()` を修正

```python
from web.env_store import _read_env

@bp.post("/api/qa-process/generate")
def api_qa_process_generate() -> dict | tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    ...
    # プロバイダを選択（API キーがあれば OpenAI、なければルールベース）
    env = _read_env()
    api_key = env.get("OPENAI_API_KEY", "").strip()
    model = env.get("OPENAI_MODEL", "").strip()

    # src/llm は sys.path に入っていないため、絶対インポートを確認すること
    # app.py で sys.path.insert が行われているか、または相対パスで import 可能か確認
    try:
        from llm.viewpoint_generator import make_provider
        provider = make_provider(api_key, model)
    except ImportError:
        provider = None  # フォールバック

    viewpoints = _load_qa_viewpoints(domain, report, provider=provider)
    ...
```

### 3. `src/llm` の import パスについて

`app.py` が `sys.path` に `src/` を追加しているか確認すること:
```bash
grep -n "sys.path" app.py src/main.py
```
`src/` が path に入っていない場合は `from src.llm.viewpoint_generator import make_provider` になる。
実際のプロジェクト構造に合わせること。

---

## テストの指示（`tests/test_llm_wiring.py`）

```python
from __future__ import annotations
from unittest.mock import patch, MagicMock
import pytest


def test_make_provider_called_with_empty_key_returns_rules():
    """API キー未設定時にルールベースプロバイダが選択される。"""
    from llm.viewpoint_generator import make_provider
    from llm.provider import RulesProvider
    p = make_provider("")
    assert isinstance(p, RulesProvider)


def test_rules_provider_generate_viewpoints_no_api_call():
    """ルールベースは外部APIを呼ばない。"""
    from llm.provider import RulesProvider
    with patch("urllib.request.urlopen") as mock_urlopen:
        provider = RulesProvider()
        result = provider.generate_viewpoints({})
        mock_urlopen.assert_not_called()
    assert isinstance(result, list)


def test_openai_provider_generate_viewpoints_calls_api(tmp_path):
    """OpenAIProvider は urlopen を呼ぶ（モック）。"""
    from llm.provider import OpenAIProvider
    import json
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "choices": [{
            "message": {
                "content": json.dumps({"viewpoints": [
                    {"category": "機能", "viewpoint": "テスト", "risk_level": "低", "example_cases": []}
                ]})
            }
        }]
    }).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_response):
        provider = OpenAIProvider("sk-test-key")
        result = provider.generate_viewpoints({"screen_info": {}})
    assert len(result) == 1
    assert result[0]["source"] == "openai"
```

---

## 完了条件

- [ ] `OPENAI_API_KEY` が未設定の場合、QA プロセス生成がルールベース観点を使う
- [ ] `OPENAI_API_KEY` が設定されている場合、観点カタログを `generate_openai_qa()` に渡す
- [ ] `python -m pytest tests/test_llm_wiring.py -v` が全 PASS（モック使用）
- [ ] `python -m pytest tests/ -q` が全 PASS（既存テスト影響なし）
- [ ] 変更が `web/services/qa/helpers.py` と `web/routes/qa_process.py` のみに収まっている

---

## スコープ外（やらないこと）

- `OPENAI_API_KEY` を使った実際の API 呼び出しテスト（専用環境で行う）
- UI の変更（バッジは Phase 3-B で対応）
- `openai_qa.py` のスキーマ変更
- git 操作
