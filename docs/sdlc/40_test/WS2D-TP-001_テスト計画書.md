# WS2D-TP-001 テスト計画書（マスターテスト計画）

- 版数: 1.0 / 作成日: 2026-07-16
- 準拠: ISO/IEC/IEEE 29119-2、ISTQB FL v4.0
- **正本参照**: 詳細なテスト戦略・レベル定義・UAT シナリオは
  `docs/TESTING_STRATEGY.md` を正とし、本書は SIer 体系上の要約とリリース判定基準の
  差分補強に留める（MECE・二重管理しない）。

## 1. テスト目的・範囲

- 対象: WebSpec2Doc 全 19 機能（`quality/feature_contracts.yml`）。
- 目的: 機能適合性・信頼性（異常系網羅）・使用性（a11y/ダーク）・保守性（カバレッジ）の担保。

## 2. テストレベル（多層ゲート）

| レベル | 内容 | 実体 | 実行 |
|---|---|---|---|
| L0 契約 | 機能契約の機械検証（UI-only 禁止・シンボル実在・異常系必須） | `feature_contracts.yml` | `python scripts/quality_harness.py` |
| L1 単体 | ドメイン中核（`src/`）の関数/クラス | tests/ 85 ファイル | `make test` |
| L2 結合 | Flask ルート統合（test_client） | tests/ 23 ファイル | `make test` |
| L3 システム | 実ブラウザ E2E（Playwright） | tests/e2e/ 32 ファイル | `make verify-ui` |
| 受入 | UAT シナリオ | `WS2D-AT-001` | 手動 |

## 3. 合格基準（リリースゲート）

- L0: `validated_features=19` PASS。
- L1/L2: 全 green（現状 **1,831 passed**）。
- L3: 全 green・**skip 0**（現状 **200 passed**）。quarantine 0 件。
- カバレッジ: ≥80%（現状 **84.30%**）。
- ビジュアル回帰: ベースライン一致（意図変更時のみ再取得＋目視）。
- Console error ゼロ・全 11 ビュー × light/dark 表示崩れなし。

## 4. テスト環境

- Python 3.12 / venv、Playwright Chromium。E2E は conftest がサーバ自動起動（127.0.0.1:8765）。
- ローカル URL 検証は `WEBSPEC2DOC_ALLOW_LOCAL=1`。

## 5. リスクと対策

- 実ブラウザ E2E の flaky → 同期状態の決定的検証・quarantine 機構（現在 0 件）で管理。
- ビジュアル基準線の環境差 → ローカル基準線（gitignore）＋意図変更時のみ再取得。
- 詳細リスク登録簿は `docs/TESTING_STRATEGY.md`。

## 6. 成果物（本体系）
- 観点: `WS2D-TV-001` / 結果報告: `WS2D-UT/IT/ST-001` / トレース: `WS2D-TM-001` /
  不具合: `WS2D-DL-001` / サマリ: `WS2D-TR-001`。
