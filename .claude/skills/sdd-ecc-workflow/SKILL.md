---
name: sdd-ecc-workflow
description: 仕様駆動開発（SDD: Spec-Driven Development）でプロジェクトを進めるためのスキル。新規プロジェクト立ち上げ、spec.md/plan.md/tasks.mdの作成、Everything Claude Code（ECC）やcc-sdd（/kiroコマンド）の利用、Coordinator/Implementor/Verifierの役割分離、トークン最適化の相談があった場合は必ずこのスキルを使用すること。「仕様から作りたい」「要件定義から」「タスク分解して」という依頼にも適用する。
---

# SDD + ECC ワークフロー

仕様ファイルを単一の真実とし、実装・検証を分離して進める。詳細テンプレートは references/templates.md を参照。

## 10ステップフロー
1. spec.md（要求・制約・検証基準）→ 2. plan.md（アーキテクチャ・技術選定）→ 3. tasks.md（依存関係付きタスク分解）→ 4. 実装ループ → 5. 検証 → 6. implement.md（実装記録）→ 7. documentation.md → 8. AGENTS.md/CLAUDE.md更新 → 9. レビュー → 10. 次イテレーション

## ガバナンス選択（プロジェクト開始時に必ず確認）
| パターン | 適用条件 |
|---|---|
| spec-first | 小規模・個人PWA。specは初期ガイドのみ |
| spec-anchored | 社内ツール・PoC。実装後にspecへ逆同期 |
| spec-as-source | 顧客納品・規制要件あり。specが常に正 |

## 役割分離
- **Coordinator**: タスク割当・進捗管理のみ。コードを書かない
- **Implementor**: tasks.mdの1タスクのみ実装。範囲外に手を出さない
- **Verifier**: 実装と独立にspec.mdの検証基準に対して判定。evidence-only

## トークン規律
- spec.mdに「禁止操作・対象外ファイル」を明記し探索を抑制
- 1タスク1セッション。/clear を区切りで実行、strategic-compactを論理的区切りで
- MAX_THINKING_TOKENS=10000、MCPは必要分のみ
- 大きい仕様は口頭でなくファイルで渡す

## cc-sdd を使う場合
```
npx cc-sdd@latest --claude-agent --lang ja
/kiro:spec-init <一文で: 言語・構成・API・管理方式を明示>
/kiro:spec-requirements <name> → レビューを1回挟む（最重要）
/kiro:spec-design <name> -y
/kiro:spec-tasks <name> -y
/kiro:spec-impl <name>
```
spec-initの一文の質が全体を決める。requirements後のレビューで判定ロジック・制約を確定させてからdesignに進む。

## cc-sdd が使えない場合（社内ポリシー等でnpm不可）
- CLAUDE.md にプロジェクト指示を記述
- requirements.md / design.md / tasks.md を手動作成（templates.md参照）
- 同じ10ステップフローを手動で回す

## ECC導入時
```
./install.sh python typescript   # 必要言語のみ選択的導入
npx ecc-agentshield scan         # CIに組み込み継続検査
```
不要な言語スキルは入れない。SQLite追跡で増分更新・ロールバック可能。
