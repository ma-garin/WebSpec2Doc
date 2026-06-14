# タスク: Phase 3-A 統合テスト — OpenAI API 実呼び出しの検証

## ゴール

`OPENAI_API_KEY` が設定された環境で、以下を確認する。

1. `OpenAIProvider.generate_viewpoints()` が実際に OpenAI API を呼び、`source="openai"` の観点リストを返す
2. `generate_openai_qa()` に観点カタログが渡され、QA アーティファクトが生成される
3. GUI の QA プロセス画面で `✨ AI補完` バッジが表示される

**なぜ必要か**: モック環境（開発機）では RulesProvider のみ動作確認済み。
本タスクは API キーがある専用環境でのみ実施できる統合検証。

---

## 前提チェック（必ず実行してから始める）

```bash
# 1. Python 環境の確認
source venv/bin/activate
python --version   # 3.12.x であること

# 2. テスト環境の確認
python -m pytest tests/ -q --co -q 2>&1 | tail -5   # テスト収集が通ること

# 3. API キーの確認（.env に設定されていること）
grep OPENAI_API_KEY .env   # 値が空でないこと（キー本体は表示しない）

# 4. 既存テストが全 PASS であること
python -m pytest tests/ -q 2>&1 | tail -5
```

> `.env` が存在しない場合は `cp .env.example .env` して API キーを設定すること。

---

## 触るファイル（これ以外は変更しない）

- `tests/test_llm_openai_integration.py` — 新規作成（実 API 統合テスト）

**変更禁止**:
- `src/llm/provider.py`（変更完了済み）
- `src/llm/viewpoint_generator.py`（変更完了済み）
- `web/routes/qa_process.py`（変更完了済み）
- `web/services/qa/helpers.py`（変更完了済み）
- `web/services/openai_qa.py`（変更なし）
- その他すべての既存ファイル
- git 操作（commit は Claude が行う）

---

## 既存コードの参照（実装前に必ず読むこと）

```bash
# プロバイダ実装
cat src/llm/provider.py

# ファクトリ関数
grep -n "make_provider" src/llm/viewpoint_generator.py

# 既存モックテスト（構造の参考）
cat tests/test_llm_wiring.py

# QA プロセス生成の全体フロー
cat web/routes/qa_process.py
cat web/services/openai_qa.py | head -90
```

---

## テストの実装指示

### `tests/test_llm_openai_integration.py` を新規作成

```python
"""
Phase 3-A 統合テスト: OpenAI API 実呼び出し検証。
OPENAI_API_KEY が未設定の場合はすべてスキップする。
実行するとAPIコストが発生する。件数は最小化している。
"""
from __future__ import annotations

import os
import pytest

# API キーがなければモジュール全体をスキップ
pytestmark = pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY", "").strip(),
    reason="OPENAI_API_KEY が未設定のため統合テストをスキップ",
)


def _api_key() -> str:
    return os.environ.get("OPENAI_API_KEY", "").strip()


# ──────────────────────────────────────────────
# 1. OpenAIProvider.generate_viewpoints() の実 API 呼び出し
# ──────────────────────────────────────────────

def test_openai_provider_generate_viewpoints_real_api():
    """実 API でテスト観点リストを生成し、source="openai" が付くことを確認。"""
    from llm.provider import OpenAIProvider

    provider = OpenAIProvider(_api_key())
    # 画面情報は最小限（コスト削減）
    screen_info = {
        "domain": "integration-test.example",
        "screens": [{"page_id": "P001", "title": "ログイン画面", "url": "https://example.com/login"}],
        "fields": [
            {"name": "email", "required": True, "maxlength": 255},
            {"name": "password", "required": True, "maxlength": 128},
        ],
    }
    result = provider.generate_viewpoints(screen_info)

    assert isinstance(result, list), "観点リストが返ること"
    assert len(result) > 0, "1件以上の観点が生成されること"
    for item in result:
        assert "category" in item, f"category キーがあること: {item}"
        assert "viewpoint" in item, f"viewpoint キーがあること: {item}"
        assert item.get("source") == "openai", f"source='openai' が付くこと: {item}"


# ──────────────────────────────────────────────
# 2. make_provider() が API キーありで OpenAIProvider を返す
# ──────────────────────────────────────────────

def test_make_provider_with_real_key_returns_openai_provider():
    """実 API キーで make_provider() が OpenAIProvider を返すことを確認。"""
    from llm.provider import OpenAIProvider
    from llm.viewpoint_generator import make_provider

    provider = make_provider(_api_key())
    assert isinstance(provider, OpenAIProvider), "OpenAIProvider が返ること"


# ──────────────────────────────────────────────
# 3. generate_openai_qa() に viewpoints が渡り QA アーティファクトが生成される
# ──────────────────────────────────────────────

def test_generate_openai_qa_with_viewpoints(tmp_path, monkeypatch):
    """
    viewpoints カタログが generate_openai_qa() に渡され、
    QA アーティファクト（dict）が返ることを確認。
    コスト削減のため画面数・フィールド数を最小化。
    """
    import json
    from web.services.openai_qa import generate_openai_qa

    # .env の API キーを環境変数から直接使う（monkeypatch 不要）
    domain = "integration-test.example"
    report = {
        "meta": {"domain": domain, "screen_count": 1, "page_count": 1},
        "screens": [
            {
                "page_id": "P001",
                "title": "ログイン",
                "url": "https://example.com/login",
                "forms": [
                    {
                        "fields": [
                            {"name": "email", "type": "email", "required": True},
                            {"name": "password", "type": "password", "required": True},
                        ]
                    }
                ],
                "buttons": ["ログイン"],
                "transitions": {"to": []},
            }
        ],
    }
    viewpoints = [
        {"summary_type": "機能", "name": "ログイン正常系", "count": 1, "source": "openai"},
        {"summary_type": "セキュリティ", "name": "XSS入力検証", "count": 1, "source": "openai"},
    ]

    result = generate_openai_qa(domain, report, viewpoints)

    assert isinstance(result, dict), "dict が返ること"
    # QA_ARTIFACT_SCHEMA の必須キーが含まれること
    assert "test_plan" in result or "test_analysis" in result or "test_cases" in result, \
        f"QA アーティファクトのキーが含まれること: {list(result.keys())}"


# ──────────────────────────────────────────────
# 4. _load_qa_viewpoints() が OpenAIProvider 経由で source="openai" を追加する
# ──────────────────────────────────────────────

def test_load_qa_viewpoints_with_openai_provider():
    """
    _load_qa_viewpoints() に OpenAIProvider を渡したとき、
    source="openai" の観点が CSV 観点に追加されることを確認。
    """
    from llm.provider import OpenAIProvider
    from web.services.qa.helpers import _load_qa_viewpoints

    provider = OpenAIProvider(_api_key())
    report = {
        "screens": [
            {
                "page_id": "P001",
                "title": "検索画面",
                "url": "https://example.com/search",
                "forms": [{"fields": [{"name": "query", "required": False}]}],
            }
        ]
    }

    result = _load_qa_viewpoints("integration-test.example", report, provider=provider)

    assert isinstance(result, list)
    openai_items = [item for item in result if item.get("source") == "openai"]
    assert len(openai_items) > 0, "source='openai' の観点が1件以上追加されること"
```

---

## テストの実行方法

```bash
# 前提: .env に OPENAI_API_KEY が設定済みであること
source venv/bin/activate

# 環境変数として読み込む（.env を直接 export）
export $(grep -v '^#' .env | xargs)

# 統合テストのみ実行（コスト発生）
python -m pytest tests/test_llm_openai_integration.py -v

# 全テストを実行して既存テストへの影響がないことを確認
python -m pytest tests/ -q
```

> **⚠️ コスト注意**: テスト4件で合計 1,000〜3,000 トークン程度（gpt-4o-mini なら $0.01 未満）。
> `OPENAI_MODEL` を `.env` で `gpt-4o-mini` に設定することを推奨。

---

## GUI での目視確認（テスト後）

```bash
# サーバーを起動
python app.py   # → http://127.0.0.1:8765 でアクセス
```

1. **QAプロセス** メニューを開く
2. 対象サイトをクロール済みのドメインに設定
3. 「AI を使用する」チェックをオンにして「実行」
4. 観点テーブルの各行に `✨ AI補完` バッジが表示されること
5. `ai.used: true`, `ai.model: "<モデル名>"` がレスポンスに含まれること（ブラウザ DevTools → Network で確認）

---

## 完了条件

- [ ] `test_openai_provider_generate_viewpoints_real_api` が PASS
- [ ] `test_make_provider_with_real_key_returns_openai_provider` が PASS
- [ ] `test_generate_openai_qa_with_viewpoints` が PASS
- [ ] `test_load_qa_viewpoints_with_openai_provider` が PASS
- [ ] `python -m pytest tests/ -q` が全 PASS（既存テスト影響なし）
- [ ] GUI で `✨ AI補完` バッジが表示されること（目視確認）
- [ ] テスト結果とバッジのスクリーンショットを Claude に報告

---

## Claude への報告フォーマット

実装完了後、以下を Claude に報告してください（git 操作は Claude が行う）:

```
## Phase 3-A 統合テスト 完了報告

### テスト結果
- test_openai_provider_generate_viewpoints_real_api: PASS / FAIL
- test_make_provider_with_real_key_returns_openai_provider: PASS / FAIL
- test_generate_openai_qa_with_viewpoints: PASS / FAIL
- test_load_qa_viewpoints_with_openai_provider: PASS / FAIL
- 全テスト: X PASS, Y FAIL

### 使用モデル
OPENAI_MODEL: <設定値>

### GUI 確認
✨ AI補完 バッジ: 表示された / 表示されなかった

### エラー・問題
（あれば記載）
```

---

## スコープ外（やらないこと）

- `src/llm/*.py` や `web/routes/*.py` など既存実装ファイルの変更
- OpenAI API 以外のプロバイダ（Anthropic / ローカル LLM）の実装
- 大量のページをクロールして API に投入するテスト（コスト肥大防止）
- git 操作（commit は Claude が行う）
