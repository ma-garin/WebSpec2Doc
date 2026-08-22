# System01/02 共通資産の棚卸し（2026-08-22）

System 01（ドキュメント作成）と System 02（テスト活動支援）が共有するロジックをファイル単位で整理する。
`docs/test-activity-support-scope.md` 第 5 節「既存資産の再利用」と整合させ、フロントエンド資産と
データフローの実測（`/api/testcases/table`・`/api/state-table`・`/api/history` の実応答確認済み）を追加した。

## 1. 結論（共通部分の一覧）

| 資産 | 正本ファイル | System01 での用途 | System02 での用途 | 共有方式 |
|---|---|---|---|---|
| 画面遷移データ | `report.json` の `screens[].transitions` / `transition_tests` / `meta.business_flows`（生成: `src/graph/transition_graph.py`・`src/graph/state_table.py`） | 画面遷移図・UML 3 タブの描画 | テスト観点マップ・遷移テストパス（MBT の入力） | データ共用（report.json） |
| 遷移図フロント | `static/js/view-transition.js`＋`/api/state-table`（`web/routes/report.py:453`） | ドキュメントの遷移図表示 | 同ファイル内でテスト観点マップも描画（`/api/testcases/table` を参照: 402 行目） | フロント共用（同一 JS） |
| テストケース生成 | `web/services/screen_test_design.py` / `testcase_spec_generator.py` / `spec_ts_generator.py` / `test_design_settings.py` | ドキュメント成果物の一部としてケース表を生成 | 設計工程の中核（生成ロジックそのもの） | サービス層共用 |
| テストケース保管 | `web/services/testcase_table_store.py`＋`/api/testcases/table`（`web/routes/qa_process.py:156`） | ケース表タブの表示・編集 | ケースの正本ストア（実行対象の選択元） | API 共用 |
| ケース表フロント | `static/js/view-testcase-grid.js` / `testcase-grid-edit.js` | ケース表の表示・セル編集 | 実行対象の選択・結果カラム表示 | フロント共用 |
| テスト自動実行 | `web/services/playwright_executor.py` | AutoRun 内の実行ステップ | 実行工程の中核 | サービス層共用 |
| 実行結果フロント | `static/js/view-test-runs.js`（データ源: `testcases/run_result.json` を `files.playwright_json` 経由 `/preview` で取得） | テスト実行タブの PASS/FAIL 表示 | 実行結果の一次画面 | データ共用 |
| 実行回ストア | `web/services/run_store.py`＋`web/routes/runs.py`（1 実行回 = report.json / report.html / qa_process/ のハブ） | 実行履歴・実行結果ページ | 証跡の保管と参照（他回の成果物を流用しない設計） | API 共用 |
| AutoRun 基盤 | `web/services/auto_run_pipeline.py` / `auto_run_job.py` / `auto_run_config.py` / `auto_run_preview.py` / `document_autorun.py` | 17 ステップ段階承認の実行 | ステージ定義を差し替えて 8 工程を駆動 | サービス層共用（ステージ定義は別） |
| 観点管理 | `web/services/viewpoint_store.py` / `viewpoint_blueprints.py` / `viewpoint_proposals.py` / `viewpoint_sources.py` / `viewpoint_templates.py` | 観点タブ・観点エディタ | 分析工程の観点カタログ | サービス層共用 |
| トレーサビリティ | `web/services/traceability.py` | 要求→観点→ケースの鎖の表示 | 鎖の末端に実行結果・不具合・PR を追加 | サービス層共用 |
| 不具合分析 | `web/services/failure_classifier.py` / `failure_hypothesis.py` / `mutation_verifier.py` | AutoRun 失敗時の分類 | 不具合分析工程（ODC 拡張の土台） | サービス層共用 |
| 証跡・出力 | `web/services/evidence_pack_service.py` / `export_xlsx.py` | 成果物のエクスポート | 証跡パックの出力 | サービス層共用 |
| 外部アクセス安全弁 | `web/services/egress_gateway.py` / `untrusted_content.py` | クロール時の外部取得 | GitHub API・外部文書の取り込み経路 | サービス層共用 |
| 完了判定の形式 | `quality/feature_contracts.yml` / `scripts/quality_harness.py` | 機能契約の機械判定 | 同じ契約形式で別 feature_id を定義 | 形式共用（内容は別、第 3 節参照） |
| フロント基盤 | `static/js/core.js` / `view-utils.js` / `table-utils.js` / `ui-states.js` | SPA 共通基盤 | 同左（具体的な分担は未確認） | フロント共用 |

## 2. ユーザー仮説の検証

仮説「画面遷移図・テストケース実装・自動実行は共通」— **3 つとも共通。ただし共有の形はそれぞれ異なる。**

### 画面遷移図 — 共通（データ共用）
- 正本はデータ側: `report.json` の `screens[].transitions` / `transition_tests` / `meta.business_flows`。
- 根拠: `static/js/view-transition.js` 109・226・309〜327 行目（reportJson の上記キーを直接参照）、
  `/api/state-table`（`web/routes/report.py:453`、report.json を読む）。生成側は `src/graph/transition_graph.py`。
- System02 は同じ JS 内の「テスト観点マップ」タブで `/api/testcases/table` も併用しており（402 行目）、
  1 ファイルの中で System01 のデータと System02 のデータが既に合流している。

### テストケース — 共通（API 共用。ただし正本は report.json ではない）
- 正本は専用ストア: `web/services/testcase_table_store.py`。取得は `/api/testcases/table`
  （`web/routes/qa_process.py:156`）。`static/js/view-testcase-grid.js` 63 行目がこれを取得する。
- report.json のキーではない点に注意。遷移図（report.json）とはデータの置き場が別。
- 生成は `screen_test_design.py` / `testcase_spec_generator.py`、編集は `testcase-grid-edit.js`（TCG 状態を共有）。

### 自動実行 — 共通（サービス層共用＋データ共用）
- 実行本体の正本: `web/services/playwright_executor.py`。結果の正本: `testcases/run_result.json`
  （`static/js/view-test-runs.js` 冒頭コメントに明記。`files.playwright_json` 経由 `/preview` で取得）。
- 実行回の保管: `web/services/run_store.py`＋`web/routes/runs.py`（1 実行回 = 3 成果物のハブ。
  他回の成果物で代替しない設計が docstring に明記）。
- AutoRun 基盤（`auto_run_pipeline.py` ほか）は両システムの実行エンジンだが、ステージ定義は別物（第 3 節）。

## 3. 共通化してはいけないもの

| 対象 | 理由 |
|---|---|
| 「実行結果」の意味 | System01 はドキュメント生成実行の成果物（report.json）、System02 はテストの PASS/FAIL（run_result.json）。`view-test-runs.js` 冒頭に「他系統の古い結果を流用しない」と明記済み |
| AutoRun のステージ定義 | 基盤は共用だが、System01 は 17 ステップの文書生成、System02 は 8 工程。定義の混在は段階承認の意味を壊す |
| feature_contracts の中身 | 契約の「形式」は共用してよいが、feature_id と判定条件は各システム固有。共通 ID にすると完了判定が他方の変更で壊れる |
| ケース表の編集履歴 | `testcase-grid-edit.js` の undo/redo・保存履歴はケース表固有の状態。他ビューへの一般化は不要な結合を生む |

## 4. 適用の順序（P0/P1/P2）

`docs/test-activity-support-scope.md` 第 6 節の段階分けに従い、共有方式の確立を対応づける。

| 段階 | 共通資産の適用 | 根拠 |
|---|---|---|
| **P0** | データ共用と API 共用をそのまま使う: report.json（遷移）・`/api/testcases/table`（ケース）・`playwright_executor.py`（実行）・`run_store.py`（証跡）。新規の共有層は作らない | 流用率が最も高く、実データ 1 周で設計誤りを早期検出できる（scope doc P0 と同旨） |
| **P1** | サービス層共用を拡張: `failure_classifier.py` に ODC 属性、`traceability.py` の鎖の末端に実行結果・Issue を追加。AutoRun のステージ定義差し替えを導入 | 不具合分析・計画は既存部品の拡張で足りる |
| **P2** | 形式共用の整備: System02 用 feature_id を `quality/feature_contracts.yml` に追加し、`quality_harness.py` で両システムを同一ゲートに載せる。フロント基盤（core.js 等）の分担整理はこの段階まで保留 | 書き込み権限（PR 提出）と同時期でよく、先行整備は過剰 |

## 未確認事項

- `static/js/core.js` / `view-utils.js` / `table-utils.js` / `ui-states.js` の中身は未読。両システムでの具体的な関数分担は未確認。
- `src/mbt/`（`pairwise.py` / `metamorphic.py` 等）が System02 の設計工程からどう呼ばれるかは未確認（ディレクトリの実在のみ確認）。
- `report.html` / `qa_process/` の生成経路は `web/routes/runs.py` docstring での確認のみ。生成側ファイルは未特定。
