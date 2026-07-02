# /sdd-start — SDD 10ステップの起動

引数: $ARGUMENTS（プロジェクト概要: 言語・構成・API・管理方式を1文で）

## 実行内容

sdd-ecc-workflowスキルに従い、SDDのフロントエンドを一気に生成します。

1. **ガバナンスパターンを確認**（引数または質問で決定）
   - spec-first（個人PWA規模）
   - spec-anchored（社内ツール・PoC）
   - spec-as-source（顧客納品・規制要件）

2. **spec.md を生成**（references/templates.mdのテンプレートを使用）
   - FR-01〜の機能要求に検証基準を必ず付与
   - 禁止操作・対象外ファイルを明記してトークン漏洩を防ぐ

3. **plan.md を生成**
   - 技術選定は比較表形式で根拠を示す

4. **tasks.md を生成**
   - 1タスク = 1セッションで完了できる粒度に分解
   - 依存関係を明記

5. **プロジェクト用 CLAUDE.md を生成**
   - Coordinator / Implementor / Verifier の役割指示を含む

プロジェクト概要が未指定の場合は「言語・構成・AI使用有無・デプロイ先」を確認してから生成する。
