# WS2D-TV-001 テスト観点表

- 版数: 1.0 / 作成日: 2026-07-16 / 準拠: ISTQB / ISO 25010
- 観点の機械可読ソース: `data/viewpoint_templates/*.json`（アプリの観点管理機能が使用）。

## 1. 標準観点テンプレート（実装済み・`data/viewpoint_templates/`）

| テンプレート | 規格・出典 | 用途 |
|---|---|---|
| `istqb.json` | ISTQB FL | テスト技法・レベルの観点 |
| `iso25010.json` | ISO/IEC 25010 | 製品品質 8 特性の観点 |
| `nfr2018.json` | 非機能要求グレード(2018) | 非機能観点 |
| `pmbok.json` | PMBOK | プロセス・管理観点 |

これらは観点管理ビュー（`viewpoints`）から適用でき、生成テスト設計に反映される。

## 2. 本体検証に適用した観点（機能契約の required_tests）

各機能の受入観点は `feature_contracts.yml` の `required_tests` に規定（`WS2D-TM-001` で
テストへ追跡）。critical/high 機能は下記の異常系観点を必須とする。

| 観点 | 説明 | 適用機能例 |
|---|---|---|
| happy_path | 正常系 | 全機能 |
| error_path | 異常入力・失敗 | discover, crawl, autorun 他 |
| timeout_path | タイムアウト | login, autorun |
| cancel_path | キャンセル | crawl, autorun, login |
| session_expiry_path | セッション失効 | login |
| checkpoint_path | 再開・部分結果 | crawl |
| approval_path | 承認ステップ | autorun |
| breaking_change_path | 破壊的差分検知 | diff_history |
| validation_path | 入力検証 | settings |
| empty_path | 空状態 | usage_roi, coverage_gap_report |
| evidence | 実測根拠の付与 | ほぼ全機能 |
| state_join_key | 状態結合キー整合 | exploration_capture, reverse_assets, finding_ticket |
| unclassified_fallback | 未分類フォールバック | old_new_comparison |

## 3. 横断品質観点（ISO 25010 対応は `WS2D-NF-001`）

使用性（a11y=axe / キーボード / ダーク）、信頼性（異常系網羅）、セキュリティ
（CSRF/CSP/PW 非保持）、保守性（カバレッジ・契約検証）。
