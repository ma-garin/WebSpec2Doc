# WS2D-QA-001 品質保証計画書

- 版数: 1.0 / 作成日: 2026-07-16 / 準拠: IEEE 730（SQA）
- 正本参照: 完了定義 `docs/DEFINITION_OF_DONE.md`、機能整合性ゲート
  `docs/process/functional-integrity-gate.md`。本書はその統合ビュー＋メトリクス実測。

## 1. 品質方針

- **機能整合性**: 「UI がある/ボタンがある/テストが通った」だけを完了としない。
  実行パス（UI→API→backend→service/core→出力→永続化→エラー処理→利用者可視の証跡）を
  検証する（`.claude/rules/functional-integrity.md`）。
- **狩野モデル×VDD**: 当たり前品質（ゲート正常化・死んだ UI 排除）を最優先で回復し、
  外部/魅力的品質へ投資する。

## 2. 品質ゲート体系（多層）

| ゲート | 内容 | ツール |
|---|---|---|
| L0 | 機能契約の機械検証（UI-only 禁止・シンボル実在・異常系必須） | `scripts/quality_harness.py` |
| L1/L2 | 単体・結合 | `make test` |
| L3 | 実ブラウザ E2E | `make verify-ui` |
| カバレッジ | ≥80% | `make coverage` |
| 静的/セキュリティ | ruff・mypy・bandit・pip-audit | `make lint` / `make security` |
| pre-commit | 構文＋test＋UI ハッシュ照合 | `.githooks/pre-commit` |

## 3. 完了の定義（DoD 要約）

変更タイプ A/B/C 別のチェックリストは `docs/DEFINITION_OF_DONE.md`（IEEE 730 / ISTQB 準拠）。
共通: 該当ゲート green・証跡・トレーサビリティ（要件⇔テスト）を満たすこと。

## 4. 品質メトリクス（実測サマリ）

| メトリクス | 目標 | 実測（2026-07-16） |
|---|---|---|
| 機能契約検証 | PASS | validated_features=19 |
| L1/L2 テスト | 全 green | 1,831 passed |
| L3 E2E | 全 green・skip 0 | 200 passed / 0 skipped |
| カバレッジ | ≥80% | 84.30% |
| トレーサビリティ GAP | 0 | 0（`WS2D-TM-001`） |
| quarantine | 0 | 0 |

## 5. 継続的品質活動

- 不具合は `WS2D-DL-001` に起票→原因分類→対策→検証→クローズ。
- 開発プロセス失敗時は名前付き RCA（5 Whys / Fishbone / FMEA / CAPA / DoD 更新）を用いる
  （`.claude/rules/functional-integrity.md`）。
- レトロの学びは `yuki-aidd-kit`（lessons）等に蓄積。
