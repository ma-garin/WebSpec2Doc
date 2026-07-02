# ゴールデンデータセット スキーマ

evalの土台。実運用ログから抽出した「入力＋期待出力」の集合。机上例だけだと本番分布とずれるため、必ず実ログから作る。

## 共通フォーマット（JSONL）
```jsonl
{"id":"esc_001","input":{...},"expected":{...},"context":[...],"tags":["escalation","critical"],"source":"prod_log_2026-05"}
```

| フィールド | 説明 |
|---|---|
| id | 一意ID |
| input | システムへの入力（状況・質問等） |
| expected | 期待出力（判定・回答の正解） |
| context | RAGの場合の検索コンテキスト |
| tags | severity・カテゴリ。集計軸に使う |
| source | 抽出元（prod_log / 手動作成）。分布把握用 |

## pmo_agent エスカレーション判定
```jsonl
{"id":"esc_001","input":{"progress_delay":0.2,"budget_over":0.15,"complaints":2},"expected":{"judgment":"escalate"},"tags":["critical"],"source":"prod_log"}
{"id":"esc_002","input":{"progress_delay":0.02,"budget_over":0.0,"complaints":0},"expected":{"judgment":"no_escalate"},"tags":["low"],"source":"prod_log"}
```
→ 混同行列を作り、FN（escalateすべきをno_escalateした見逃し）を最重要監視。

## RAGチャット
```jsonl
{"id":"rag_001","input":{"q":"受入基準は？"},"context":["受入基準: カバレッジ80%以上..."],"expected":{"must_include":["80%"],"must_cite":true},"source":"prod_log"}
```

## データセット規模の目安
- 初期: 20-50件（各カテゴリ・各severityを網羅）
- 運用: 本番で誤判定が出るたびに1件追加（回帰防止のレグレッションケース化）
- 偏り注意: escalate/no_escalateを極端に偏らせない（recall/precisionが歪む）

## バージョン管理
- データセットもgit管理。`evals/datasets/` に置く
- 期待出力を変更したらADRに理由を記録（正解の定義変更は評価結果を非連続にする）
