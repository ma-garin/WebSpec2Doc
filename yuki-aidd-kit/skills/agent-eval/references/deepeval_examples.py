"""
DeepEval scaffold — business_agent / multi-agent research system 用のeval例
セットアップ:
  pip install deepeval
  # 業務eval: OpenAI APIをjudgeに（DeepEvalデフォルト。精度重視）
  export OPENAI_API_KEY=...        # GPT-4o系がデフォルトjudge
  # 個人PWA: 課金回避でGemini無料枠 or Ollamaに切替
  # deepeval set-gemini --model-name=gemini-2.0-flash --api-key=$GEMINI_API_KEY
  # deepeval set-local-model --model-name=llama3 --base-url=http://localhost:11434/v1
実行:
  deepeval test run evals/test_business_agent.py
  # または pytest evals/ -v
"""
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase, ToolCall
from deepeval.metrics import (
    FaithfulnessMetric,
    ContextualPrecisionMetric,
    HallucinationMetric,
    JsonCorrectnessMetric,
    ToolCorrectnessMetric,
    GEval,
)
from deepeval.test_case import LLMTestCaseParams


# ========== business_agent: エスカレーション判定 ==========

# G-Eval: 根拠が判定を支持しているかをカスタムrubricで採点
escalation_evidence = GEval(
    name="Escalation Evidence Validity",
    criteria="出力のevidenceフィールドが、escalate判定を論理的に支持しているか。"
             "根拠が薄い・無関係な場合は低スコア。",
    evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
    threshold=0.8,
)


def test_escalation_judgment():
    # ゴールデンデータ（実運用ログから抽出した1件）
    tc = LLMTestCase(
        input="進捗20%遅延、予算15%超過、顧客クレーム2件",
        actual_output='{"judgment":"escalate","reason":"予算超過と顧客影響","evidence":"予算15%超過は閾値10%を超える"}',
    )
    assert_test(tc, [escalation_evidence])


def test_escalation_json_schema():
    tc = LLMTestCase(
        input="軽微な仕様確認1件",
        actual_output='{"judgment":"no_escalate","reason":"影響軽微","evidence":"単一の仕様確認のみ"}',
    )
    # スキーマ準拠を検証（pydanticモデルを渡す形式。詳細はDeepEvalドキュメント参照）
    assert_test(tc, [JsonCorrectnessMetric(expected_schema=None, threshold=1.0)])


# ========== business_agent: RAGチャット（成果物支援） ==========

def test_rag_faithfulness():
    """回答が検索コンテキストにグラウンディングされているか（ハルシネーション検出）"""
    tc = LLMTestCase(
        input="このプロジェクトの受入基準は？",
        actual_output="受入基準はテストカバレッジ80%以上と性能要件の充足です。",
        retrieval_context=[
            "受入基準: テストカバレッジ80%以上、応答時間3秒以内を満たすこと。",
        ],
    )
    assert_test(tc, [
        FaithfulnessMetric(threshold=0.9),      # グラウンディング必須ゲート
        ContextualPrecisionMetric(threshold=0.7),
    ])


# ========== multi-agent research system: マルチエージェント ==========

def test_agent_tool_correctness():
    """正しいツールを正しく呼んだか"""
    tc = LLMTestCase(
        input="トヨタの直近30日の株価トレンドを分析",
        actual_output="上昇トレンドです",
        tools_called=[ToolCall(name="fetch_price", input_parameters={"ticker": "7203", "days": 30})],
        expected_tools=[ToolCall(name="fetch_price", input_parameters={"ticker": "7203", "days": 30})],
    )
    assert_test(tc, [ToolCorrectnessMetric(threshold=1.0)])


# ========== 回帰ゲート ==========
# ベースラインスコアをJSONで保存し、CIで比較。低下したらビルドを落とす。
# pytest --deepeval や deepeval test run の結果を baseline と突合する運用にする。
