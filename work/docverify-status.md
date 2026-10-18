# System 06 ドキュメント検証 — 引き継ぎ（2026-10-18 19:02）

## 完了（main にマージ済み）
- コード地図 `.claude/rules/docverify-map.md`（docverify のファイルを触ると自動で読み込まれる）
- 競合・先行研究 `docs/research/docverify/F_winning_strategy.md`、トレーサビリティ `G_traceability.md`
- 対検査の評価セット `quality/docverify_eval/pair_v1`（11 組）・`pair_v2`（5 組・未見の評価用）
- 対検査エンジン `web/services/docverify/pair/`、予測 `scripts/docverify_pair_predict.py`、採点 `scripts/docverify_pair_eval.py`

## 精度（pair_v2 = どの担当も開発に使っていない 5 組）
| 区分 | 適合率 | 再現率 |
|---|---|---|
| 全体 | 0.77 | 0.60 |
| 追跡リンク | 0.89 | 0.68 |
| 用語ゆれ | 0.0 | 0.0 |
| 余分な設計 | 0.0 | 0.0 |
- pair_v1 は開発中に全組を見たため、汎化の根拠にしない
- 用語ゆれ・余分な設計は文字 n-gram の規則では汎化しない（言い換え・語の重なり）。意味の比較（埋め込みか LLM）が要る → 要判断: LLM（OpenAI）を検出の二段目に使うか。Ollama は使わない

## 次の一手
1. 検証観点の画面: 案 `docs/design/docverify/checklists-v1.html` の承認待ち（4 方向: 対検査の観点・V 字の対・編集・自社基準の取り込み）。承認後に実装
2. 用語ゆれ・余分な設計: 上の要判断を受けて方式を決める。評価は pair_v2 で行い、pair_v2 の中身を見て規則を作らない（見たら pair_v3 を作る）
3. エンジンを画面（R3 集合検査）へ結線（未実施）

## 未実行
- pytest・lint・画面の結線確認
- 共有ツリーの他セッション: 8765 共有、自分の検証は 8766 以降
