# /eval — AIエージェントシステムのeval実行

引数: $ARGUMENTS（対象システム名 / 評価したい観点）

## 実行内容

agent-evalスキルに従い、自作AIシステムの品質を評価する。

1. **対象システムを特定**（business_agent / multi-agent research system / RAGチャット等）
2. **該当スコアラーを選定**（スキルのシステム別設計を参照）
   - エスカレーション判定 → 判定正確性・根拠妥当性(G-Eval)・JSON妥当性
   - RAG → Faithfulness・Contextual Precision/Recall・引用提示率
   - マルチエージェント → 層別正確性・Tool Correctness・ハンドオフ整合性
3. **ゴールデンデータセットの有無を確認**
   - あれば: DeepEvalでeval実行 → ベースライン比でスコア提示
   - なければ: references/eval_dataset_schema.md形式で初期データセット作成を提案
4. **回帰判定**: ベースラインからスコア低下があれば該当ケースを特定して報告
5. judgeモデル: 業務システムはOpenAI API（GPT-4o系、精度重視）、個人PWAはGemini無料枠/Ollama（課金回避）。ベースライン比較は同一judgeで行う

データセット・ベースライン未整備なら、まずその構築手順を案内する。
