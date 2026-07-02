# タスク: Phase 3 — OpenAI連携（別環境のみ）

**優先度**: 別環境（OpenAI APIキーが使える環境でのみ着手）  
**背景**: `OPENAI_API_KEY` が設定された環境では、LLMによるQAプロセス補完・AI補完バッジ表示を有効化する。この環境では着手不可。

---

## Phase 3-A: QAプロセスへのLLM実配線

**対象ファイル**: `web/services/openai_qa.py`, `web/routes/qa_process.py`

QAプロセスの「テスト分析」ステップで、`OPENAI_API_KEY` が設定されている場合に `generate_openai_qa()` を呼び出す。

```python
# web/routes/qa_process.py の generate ハンドラ内
from web.services.openai_qa import generate_openai_qa
from llm.viewpoint_generator import make_provider

provider = make_provider(api_key=os.environ.get('OPENAI_API_KEY', ''))
if isinstance(provider, OpenAIProvider):
    qa_result = provider.generate_qa_process(domain, report)
else:
    qa_result = _rules_based_qa(report)  # 既存のルールベース
```

**完了条件**:
- [ ] `OPENAI_API_KEY` あり: LLMがStep3〜7を構造化JSONで補完する
- [ ] `OPENAI_API_KEY` なし: ルールベースにフォールバックする
- [ ] `python -m pytest tests/ -q` が全 PASS

---

## Phase 3-A 統合テスト

**対象ファイル**: `tests/integration/test_openai_qa.py`（新規）

```python
import pytest, os
pytestmark = pytest.mark.skipif(not os.environ.get('OPENAI_API_KEY'), reason='OpenAI key required')

def test_generate_openai_qa_returns_valid_schema():
    from web.services.openai_qa import generate_openai_qa
    result = generate_openai_qa('example.com', _minimal_report())
    assert 'test_plan' in result
    assert 'test_cases' in result
```

---

## Phase 3-B: AI補完バッジ

**対象ファイル**: `static/js/view-quality.js`, `static/app-report.css`

観点・異常系シナリオの各行に生成元バッジを表示する:

```html
<!-- ルールベース -->
<span class="source-badge source-badge--rules">ルール</span>
<!-- OpenAI補完 -->
<span class="source-badge source-badge--ai">AI補完</span>
```

判定: 各観点データの `"source": "rules"` または `"source": "openai"` を参照する。

**完了条件**:
- [ ] `source: rules` の行に「ルール」バッジが出る
- [ ] `source: openai` の行に「AI補完」バッジが出る
- [ ] `make verify-ui` が PASS

---

## スコープ外

- LLMProvider の実装（`src/llm/provider.py` に実装済み）
- この環境での動作確認（別環境のみ）
