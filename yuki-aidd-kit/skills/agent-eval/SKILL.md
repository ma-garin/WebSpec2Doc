---
name: agent-eval
description: 自作のAIエージェント・LLMシステム（business_agent、multi-agent research system多層エージェント、RAGチャット等）の品質をトレース・データセット・スコアラーで継続評価するスキル。「evalしたい」「精度を測りたい」「ハルシネーションを検出」「エスカレーション判定の正確性」「プロンプト変更の回帰」「Weaveみたいなことをしたい」「LLM出力の品質を見たい」への言及があれば必ずこのスキルを使うこと。test-automationが「コードが動くか」を見るのに対し、こちらは「AIの出力が良いか」を非決定性前提で評価する。
---

# AIエージェント eval（Weave相当を自前・無料で）

LLM出力は非決定性なので pass/fail の単体テストでは測れない。トレース（何が起きたか）＋データセット（正解例）＋スコアラー（採点）＋回帰ゲート（劣化検知）の4点で評価する。Weave/LangSmithの中核機能を無料スタックで再現する。

## 推奨スタック

| 役割 | ツール | 配置 |
|---|---|---|
| eval本体（回帰ゲート） | **DeepEval**（pytest-native, MIT） | `evals/` |
| トレース・観測・データセットUI | **Langfuse セルフホスト**（MIT） | 任意のローカルサーバにDocker |
| judgeモデル（業務） | **OpenAI API**（GPT-4o系。会社利用可） | eval/トレース評価 |
| judgeモデル（個人PWA） | **Gemini無料枠** or ローカルOllama | 課金ゼロ運用 |

DeepEvalがQA思考（pytest=テストとして書く）に最もフィットする。judgeは用途で切り分ける: **業務システム（business_agent / multi-agent research system）はOpenAI APIで精度重視**、個人PWAはGemini無料枠/Ollamaで課金ゼロ。G-EvalやFaithfulness等のLLM-as-judgeはjudgeの質がそのままeval精度になるため、業務評価ではGPT-4o系を使う価値が高い。詳細は references/langfuse_setup.md / deepeval_examples.py 参照。

## システム別のスコアラー設計

### business_agent — 意思決定支援（エスカレーション判定）
- **判定正確性**: ゴールデンデータセット（入力状況→正しいescalate要否）に対する一致率。混同行列でFP/FNを見る（FN=見逃しが業務上Critical）
- **根拠の妥当性**: G-Eval（カスタムrubric）で「evidenceが判定を支持しているか」を0-1採点
- **JSON妥当性**: 出力スキーマ準拠率（DeepEvalのJsonCorrectnessMetric）

### business_agent — 成果物支援（RAGチャット）
- **Faithfulness（グラウンディング）**: 回答が検索コンテキストに基づくか。ハルシネーション検出の主軸
- **Contextual Precision/Recall**: 検索が必要な情報を引けているか
- **引用提示率**: 引用元ドキュメントが必ず提示されているか（ルールベース）

### multi-agent research system — 多層マルチエージェント
- **層別の判定正確性**: 各エージェント（分析/戦略/リスク/執行）の出力を個別にスコア
- **Tool Correctness**: 正しいツール・正しい引数を呼んだか（DeepEvalのToolCorrectnessMetric）
- **層間ハンドオフ整合性**: 上位層の出力が下位層の入力として矛盾しないか

## 共通スコアラー
- Hallucination / Bias / Toxicity（DeepEval組み込み）
- Task Completion（エージェントがタスクを完遂したか）
- Answer Relevancy

## 運用フロー
1. **ゴールデンデータセット作成**: 実運用ログから20-50件の「入力＋期待出力」を抽出（Langfuse上で管理）
2. **スコアラー定義**: 上記から該当するものを `evals/` にpytestとして実装
3. **ベースライン記録**: 現行版のスコアを基準値として保存
4. **回帰ゲート**: プロンプト/モデル/ロジック変更時にeval実行 → ベースライン比でスコア低下したらCIで落とす
5. **トレース常時記録**: 本番/開発の全LLM呼び出しを Langfuse `@observe()` で記録し、劣化を可視化

## 閾値の決め方（ISTQB severity連動）
- 見逃し（FN）が業務Criticalな指標（escalation判定等）は recall優先で閾値を高く（例: 0.95）
- ハルシネーションは faithfulness 0.9以上を必須ゲートに
- 閾値はベースラインから決め、根拠をADRに記録する（恣意的に決めない）

## 注意
- judgeモデルの選択: 業務evalはOpenAI API（GPT-4o系）で精度を取る。個人PWAはGemini無料枠/Ollamaで課金ゼロ。同一データセットでもjudgeが違えばスコアがずれるため、ベースラインとの比較は必ず同一judgeで行う
- judgeモデルの非決定性: 同じ出力でもスコアがぶれる。temperature=0で安定化、必要なら複数回平均
- eval自体のeval: judgeの判定が人間の判断と一致するか、初期に数件を目視突合して校正する
- データセットは「実運用ログから」作る。机上の例だけだと本番分布とずれる
- コスト: OpenAI judgeはトークン課金が発生する。データセット50件×複数メトリクスを毎コミットで回すと積み上がるため、回帰evalはCI（PR時）に限定し、開発中はサブセットで回す
