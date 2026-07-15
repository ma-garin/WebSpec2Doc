# WS2D-UT-001 単体テスト仕様兼結果報告書（L1）

- 版数: 1.0 / 作成日: 2026-07-16 / 準拠: ISO/IEC/IEEE 29119 / ISTQB
- 定義: ドメイン中核（`src/`）の関数・クラス単体。Flask 非依存ロジックを対象とする。

## 1. 対象と方針

- 対象モジュール群（`src/`）: `crawler`（解析・探索・礼儀・認証）、`analyzer`（BVA・
  正規化・フォーム/HTML 解析）、`diff`（比較・差分・影響分析）、`generator`
  （アーキ図・比較レポート・カバレッジギャップ）、`graph`（遷移グラフ）、
  `ingest`（データ/Excel/LLM 抽出）、`llm`（プロバイダ抽象・分類）、`capture`
  （バーンダウン・カバレッジ・逆生成・気づき）、`registry`（セッション/サイト）。
- 技法: 同値分割・境界値（BVA は実装機能かつテスト対象）・状態遷移・例外系。

## 2. 実施結果（実測）

| 指標 | 値 |
|---|---|
| 単体テストファイル | 84 |
| L1/L2 合計（`make test`） | **1,794 passed** |
| カバレッジ（`src` + `web`） | **84.32%**（閾値 80%） |
| 実行コマンド | `make test` / `make coverage` |
| 収集/実行時の警告 | 0（pyproject で error 昇格） |

> L1 単体と L2 結合は同一コマンド（`make test`）で実行される。ファイル分類上、
> `src/` 中核ロジックを検証するものを L1、`test_client` 経由を L2（`WS2D-IT-001`）とする。

## 3. 代表的な単体テスト観点（抜粋）

- クロール礼儀: robots 尊重・レート制御・破壊的遮断（`test_politeness*`, `test_crawler*`）。
- バリデーション実測: HTML5 `validationMessage` 収集（Phase A で `--lang` 基底コード修正）。
- 解析: 正規化・フォーム/フィールド抽出・evidence 付与（`test_analyzer*`, `test_evidence*`）。
- 差分: 破壊的属性差分・影響分析（`test_diff*`, `test_comparison*`）。
- 生成: アーキ図・カバレッジギャップ・バーンダウン（`test_architecture_generator*` 他）。

## 4. 再現方法

```bash
make test        # 1,794 passed
make coverage    # Total coverage 84.32%（term-missing）
```
