# /qa-review — ISO 25010 + ISTQB準拠のAIレビュー実行

引数: $ARGUMENTS（対象ファイルパス または URL）

## 実行内容

qa-review-standardsスキルの基準で対象をレビューします。

1. **対象を読み込む**（HTMLファイルまたはURLのスクリーンショット）

2. **5カテゴリでスコアリング**（各0〜100 + 根拠）
   - 使用性（WCAG 2.1 / 操作の学習性 / エラー防止）
   - 性能効率性（応答時間 / リソース）
   - 信頼性（障害許容 / データ保全）
   - セキュリティ（機密性 / XSS/CSRF観点）
   - 保守性（モジュール性 / コード解析性）

3. **指摘リストを出力**（形式: id / category / severity / evidence / 改善案）
   - severity は Critical / High / Medium / Low で必ず付与
   - evidenceが空の指摘は出力しない（evidence-only原則）

4. **Whittakerツアー観点で見落とし確認**
   - Saboteur Tour（破壊的入力）
   - FedEx Tour（データのライフサイクル）

5. **前回スナップショットがある場合** → delta比較を追加セクションで出力

対象が未指定の場合は現在のワーキングディレクトリのHTMLを探して確認する。
