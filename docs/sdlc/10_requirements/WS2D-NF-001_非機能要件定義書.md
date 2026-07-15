# WS2D-NF-001 非機能要件定義書

- 版数: 1.0 / 作成日: 2026-07-16 / 準拠: ISO/IEC 25010（製品品質モデル 8 特性）
- 関連: `docs/TESTING_STRATEGY.md` §6、観点テンプレ `data/viewpoint_templates/{iso25010,nfr2018}.json`

ISO/IEC 25010 の 8 品質特性ごとに要件と現状（as-built の実測・実装根拠）を示す。

## 1. 機能適合性（Functional Suitability）
- 生成物は evidence-only 原則で実測根拠に紐づく（根拠なきものは破棄）。
- 要件 17 件が実装・テストまで追跡可能（`WS2D-TM-001`）。GAP は台帳で可視化。

## 2. 性能効率性（Performance Efficiency）
- クロール目安: 10 画面で約 2〜3 分（`view-dashboard` の表示、`CONTEXT.md`）。
- per-origin レート制御・robots crawl-delay 尊重（`src/crawler/politeness.py`）。
- クロール既定上限: 深さ `MAX_DEPTH=5`、ページ `MAX_PAGES_LIMIT=300`（`web/config.py`）。
- 解析タイムアウト: `DISCOVER_TIMEOUT_SEC=180`、ページ既定 30 秒。

## 3. 互換性（Compatibility）
- 実行基盤: Playwright Chromium。生成物は HTML / Markdown / Excel / PDF / JSON。
- ダークモード対応（`html[data-theme]`、tokens 駆動）。iframe / Shadow DOM 抽出対応。

## 4. 使用性（Usability）
- アクセシビリティ: UX 自動レビューに axe-core を統合（`ux_review`）。UI は
  フォーカスリング・ARIA 属性・キーボード操作（⌘K クイック検索・Esc クローズ）。
- 状態の一貫提示: 空 / ローディング / エラー（再試行導線）を `ui-states.js` に統一。
- 目標: WCAG 2.1 AA 相当のコントラスト（tokens のライト/ダーク両対応で担保）。

## 5. 信頼性（Reliability）
- 異常系網羅: critical/high 機能は `failure_modes` と `required_tests` を契約で必須化
  （`quality_harness` が検証）。happy/failure/timeout/cancel/session-expiry を規定。
- 回復性: クロールのチェックポイント／履歴からの再開、部分結果の保全。
- 品質ゲート: L1/L2 1,794・L3 E2E 200（skip 0）green（`WS2D-TR-001` 実測）。

## 6. セキュリティ（Security）
- 既定 127.0.0.1 バインド、`localhost_guard`＋CSRF（Origin/Referer）ガード。
- CSP（`script-src 'self'`）、セキュリティヘッダ付与。破壊的リクエスト遮断。
- サイト認証: ID/PW は送信のみで即破棄、`auth.json` は Cookie 等のみ保存
  （パスワード本体を保持しない・ADR-0002）。
- 依存脆弱性監査: `make security`（bandit＋pip-audit）、記録 `docs/security/`。

## 7. 保守性（Maintainability）
- コード規約: 1 ファイル 800 行以内・多数小ファイル・イミュータブル（`WS2D-CS-001`）。
- カバレッジ: **84.32%**（閾値 80%、`make coverage`）。
- 機能契約による構造検証（`quality_harness`：UI-only 実装の禁止・シンボル実在）。

## 8. 移植性（Portability）
- パス・接続先は環境変数で注入可能（`WEBSPEC2DOC_PORT` / `TRUSTED_HOSTS` /
  `VIEWPOINTS_DB` / `OUTPUT_DIR` 等）。ローカル／社内サーバ／コンテナ展開に対応。

## 9. 測定値サマリ（実測）

| NFR 指標 | 目標 | 実測 |
|---|---|---|
| カバレッジ | ≥80% | 84.32% |
| L1/L2 テスト | 全 green | 1,794 passed |
| L3 E2E | 全 green・skip 0 | 200 passed / 0 skipped |
| 機能契約検証 | PASS | validated_features=17 |
| a11y 検査 | 統合済み | axe-core（ux_review） |
