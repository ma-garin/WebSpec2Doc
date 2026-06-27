"""
Streamlit pytest scaffold（business_agent系用）
セットアップ:
  pip install pytest streamlit
実行:
  pytest tests/test_app.py -v
"""
from unittest.mock import patch
from streamlit.testing.v1 import AppTest


def test_app_launches_without_exception():
    at = AppTest.from_file("app.py").run()
    assert not at.exception


def test_session_state_keys_no_collision():
    at = AppTest.from_file("app.py").run()
    keys = list(at.session_state.keys())
    # {module}_{name} 形式で重複がないこと
    assert len(keys) == len(set(keys))


@patch("app.call_llm")  # LLMラッパーをモック（非決定性を排除）
def test_decision_logic_with_mocked_llm(mock_llm):
    mock_llm.return_value = {"judgment": "escalate", "reason": "予算超過", "evidence": "..."}
    at = AppTest.from_file("app.py").run()
    # フェーズ選択 → 判定実行
    at.selectbox(key="decision_phase").select("実行").run()
    at.button(key="decision_run").click().run()
    # ロジックがLLM応答を正しく反映
    assert "escalate" in str(at.session_state.get("decision_result", ""))


def test_multitenant_isolation():
    """テナントAのデータがテナントBに漏れないこと"""
    at = AppTest.from_file("app.py").run()
    at.session_state["current_tenant"] = "tenant_a"
    at.run()
    # tenant_bのデータが結果に含まれない（実装に応じてアサーション調整）
    result = str(at.session_state.get("rag_results", ""))
    assert "tenant_b" not in result
