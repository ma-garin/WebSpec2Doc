# テスト設計仕様書 T04 成果物・永続化・履歴・サンプル・再クロール（FedEx Tour）

## 1. 対象と前提

- SUT: `http://127.0.0.1:8765`（02-test-environment.md 準拠・停止禁止）。対象サイト: モック `http://127.0.0.1:9104`（`env/mock_site.py 9104 9199`・起動済みを確認）。
- 出力先: `output/127.0.0.1:9104/`（テスト開始時点で不存在＝クリーン状態を確認済み）。
- 追跡対象: データのライフサイクル（生成 → 永続化 → 実行回退避 runs/ → 履歴 → 再クロール条件復元 → エクスポート → 破損時挙動）。FedEx Tour（データの生成から消費までを追う）。
- 実行は API 直叩き（`POST /run`）を主とし、UI は結果パネルの照合に限定する（環境定義 5. により Playwright headless スクリプト）。
- 前提: `output/` に他トラック・過去のディレクトリが残存（削除禁止・触れない）。

## 2. テスト条件一覧

| 条件ID | テスト条件 | 契約 failure_mode | 25010 特性 | ツアー/手法 | リスク |
|---|---|---|---|---|---|
| T04-D01 | 初回実行（selected 6 URL）で契約 outputs 一式が生成される | crawl.outputs 欠落 | 機能適合性（完全性） | FedEx/契約ベース | High |
| T04-D02 | report.json スキーマと SUMMARY（screens/forms/fields/buttons）の一致 | - | 機能適合性（正確性） | 契約ベース | High |
| T04-D03 | `/form` の入力属性（required/maxlength/pattern/min/max）が report.json に抽出される | - | 機能適合性（正確性） | 仕様ベース | High |
| T04-D04 | report.html / screens.md / forms.md の存在と report.json との件数一致 | - | 機能適合性（一貫性） | 契約ベース | Medium |
| T04-D05 | screenshots が画面数分あり欠損ゼロ | - | 信頼性（証跡完全性） | FedEx | High |
| T04-D06 | snapshots の永続化 | - | 信頼性 | FedEx | Medium |
| T04-D07 | audit.jsonl の行数と内容（有効な JSONL） | mutation_blocked_audit | セキュリティ（責任追跡性） | 契約ベース | High |
| T04-D08 | site.json の保存（urls/crawl_mode/depth/max_pages/login_urls） | crawl.persistence | 機能適合性 | 契約ベース | High |
| T04-D09 | accessibility_audit.json / technical_health.json の生成と妥当性 | - | 機能適合性 | 仕様ベース | Medium |
| T04-D10 | `/api/result?domain=` の summary・files パスが実ファイルと一致 | - | 機能適合性（正確性） | 契約ベース | High |
| T04-D11 | `/api/result?run_id=` が当該実行回の成果物を返す | - | 機能適合性 | 契約ベース | High |
| T04-D12 | `/api/runs/<domain>`・`/<run_id>`・`/exists`・`/artifact` の整合（траversal 拒否含む） | - | 機能適合性/セキュリティ | 契約ベース | High |
| T04-D13 | `/api/history/runs` に実行条件（scope_preset/depth/max_pages/crawl_mode/target_url_count）が残る | - | 機能適合性（完全性） | 契約ベース | High |
| T04-D14 | 2 回目実行（URL 集合変更）: 最新の上書きと過去実行回（runs/）の保全・run_id での取り出し | partial_checkpoint | 信頼性（データ保全） | FedEx | Critical |
| T04-D15 | 履歴の順序（新しい順）と時刻の整合 | - | 機能適合性 | 契約ベース | Medium |
| T04-D16 | サンプルレポート: is_sample 明示・履歴不混入・再クロール導線 | sample_leaks_into_history / recrawl_dead_end_on_sample / sample_mistaken_for_own_analysis | 機能適合性 | 契約ベース | Medium |
| T04-D17 | 再クロール: `/api/site` で前回条件が復元され login_required フラグが失われない | login_required_flags_lost_on_recrawl | 信頼性 | 契約ベース | High |
| T04-D18 | spec-xlsx: シート名・行数の UI 一致、再エクスポートで重複なし、不正ドメイン拒否 | sheet_rows_diverge_from_ui / duplicate_sheets_on_reexport / invalid_domain | 機能適合性 | 契約ベース | High |
| T04-D19 | `/download-zip` が有効な ZIP を返し内容が実ファイルと一致 | - | 機能適合性 | 契約ベース | Medium |
| T04-D20 | `/api/report/<domain>/spec-ts` の応答 | - | 機能適合性 | 契約ベース | Low |
| T04-D21 | `/preview?path=` の正常表示・不在パス 404・output 外/他ドメインパスの扱い | - | セキュリティ（機密性） | 攻撃者視点 | High |
| T04-D22 | report.json 破損/欠落時の `/api/result` の縮退 | report_corrupt / report_json_missing / report_json_unreadable | 信頼性（障害許容性） | 障害注入 | High |
| T04-D23 | 結果パネル UI（実行回ページ）の件数・タブ・ファイルリンクが実ファイルと一致 | sheet_rows_diverge_from_ui 類推 | 機能適合性（UI 整合） | UI 照合 | High |

## 3. 網羅性の根拠

- 照合した外部基準: **ISO/IEC 25010:2011**（機能適合性・信頼性・セキュリティの副特性へ全条件をマッピング）、**ISTQB CTFL v4.0**（契約ベース＝仕様ベース技法、障害注入＝経験ベース、FedEx Tour は Whittaker の Exploratory Tours に拠る）。
- 契約 failure_modes との対応: feature_id=`crawl` の outputs/persistence（D01〜D08）、`zero_wait_sample_report` の 4 failure_modes 中 3 件（D16。bundled_sample_missing は同梱物削除が必要なため除外）、`spec_xlsx_full_export` の 6 failure_modes 中 5 件（D18・D22。state_table_not_applicable は状態遷移表なしデータの作成が別実行を要するため除外）。

## 4. 意図的に除外した条件と理由

- `bundled_sample_missing`: `demo/sample_report/` の退避が必要（ソースツリー変更禁止に抵触）。
- `state_table_not_applicable`: 遷移表が構築できないサイト構成の準備に追加実行が必要。リスク Medium・ツール上限 60 回の制約から除外。
- テナント切替下の runs 分離（tenancy）: T0x 他トラック（マルチテナント）担当領域。
- UI からの実行トリガ（btn-view-report 押下前のクロール起動）: クロール 3 回目相当の時間を要するため、結果パネル照合は run ページ経由（同一の results.js 経路）で代替。差分は execution-log に未実行として明記。
