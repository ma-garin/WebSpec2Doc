# SDDファイルテンプレート

## spec.md
```markdown
# <プロジェクト名> 仕様

## 目的（1〜2文）
## スコープ / 対象外
## 機能要求（FR-01〜）
- FR-01: <要求> / 検証基準: <観測可能な合格条件>
## 非機能要求（ISO/IEC 25010の特性で記述）
- 性能効率性 / 使用性 / セキュリティ / 保守性 ...
## 制約
- 技術制約（例: 単一HTML、GitHub Pages、無料枠APIのみ）
- 禁止操作（例: 依存追加禁止、対象外ディレクトリ）
## 検証方針
- evidence-only判定。各FRに対するテスト観点
```

## plan.md
```markdown
# 実装計画
## アーキテクチャ（図 or 箇条書き）
## 技術選定と理由（比較表）
## ディレクトリ/モジュール構成
## データスキーマ（localStorage / SQLite / JSON）
## リスクと回避策
```

## tasks.md
```markdown
# タスク
| ID | タスク | 依存 | 担当 | 検証基準 | 状態 |
|---|---|---|---|---|---|
| T-01 | ... | - | Implementor | FR-01合格 | TODO |
```
- 1タスク＝1セッションで完了する粒度に分解
- Phase分割の判断基準: Phase1=実務インパクト最大、Phase2=精度/実用性、Phase3=磨き込み

## implement.md
```markdown
# 実装記録
## <日付> T-XX
- 変更ファイル / 判断と理由 / 検証結果 / 残課題
```

## AGENTS.md（プロジェクト用）
```markdown
# エージェント指示
## Coordinator
tasks.mdの状態管理のみ。実装禁止。
## Implementor
指定タスクのみ。spec.mdの制約を遵守。完了時にimplement.mdへ記録。
## Verifier
spec.mdの検証基準に対しevidence-onlyで判定。ISTQB severityで報告。
```
