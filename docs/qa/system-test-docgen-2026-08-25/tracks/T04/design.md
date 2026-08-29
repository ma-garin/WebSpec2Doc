# テスト設計仕様書 T04 成果物・永続化・履歴・サンプル・再クロール（FedEx Tour）

## 1. 対象と前提

- 対象: `POST /run` が生成する成果物一式（`output/127.0.0.1:9104/`）、`GET /api/result`, `GET /api/site`, `POST /api/sample-report`, `GET /api/history`, `GET /api/history/runs`, `GET /preview`, `GET /download`, `GET /download-zip`, `GET /api/export/spec-xlsx`, `GET /api/state-table`, `GET /api/coverage-heatmap`、UI 結果パネル（`#report/<domain>`）と再クロール導線（`static/js/recrawl.js`）。
- 手法: FedEx Tour — データの生成→保存→閲覧→エクスポート→再クロールのライフサイクルを 1 個のデータ（9104 クロール成果物）で通しで追跡する。
- 前提条件（実測 2026-08-25 00:13）:
  - 本体 8765 稼働（認証オフ）・モック 9104 稼働。`output/127.0.0.1:9104/` は開始時点で不存在（クリーン）。
  - `output/sample.webspec2doc.local/` は**過去実行の残存あり**（削除禁止のため前提として記録。履歴混入判定は POST 前後の差分で行う）。
  - `demo/sample_report/` 同梱一式あり（report.html/json, screenshots, snapshots, audit.jsonl, spec.xlsx 他）。
- クロール対象: `9104/`, `9104/products`, `9104/contact` に加え、login_required フラグの再クロール保持（条件 7）を成立させるためログイン壁ページ `9104/dashboard` を 4 本目として追加した。

## 2. テスト条件一覧

| 条件ID | テスト条件 | 契約 failure_mode | 25010 特性 | ツアー/手法 | リスク |
|---|---|---|---|---|---|
| T04-D01 | 成果物一式の生成（report.json/html/md, screenshots/, snapshots/, audit.jsonl, site.json が揃う） | crawl.outputs（欠落＝誤納品） | 機能適合性 | FedEx | High |
| T04-D02 | 成果物の中身健全性（各ファイル非空・スクショが実画像・report.json に performance LCP/CLS/TTFB） | crawl.outputs（performance samples） | 信頼性 | FedEx | High |
| T04-D03 | SUMMARY（screens/forms/fields）と report.json 内容の一致 | crawl.outputs（要約と実体の乖離） | 機能適合性 | 契約ベース | High |
| T04-D04 | /contact のフォーム項目（name/email/body・required/maxlength）が項目定義に反映される | crawl.outputs（フォーム抽出欠落） | 機能適合性 | 契約ベース | Medium |
| T04-D05 | /api/result: domain 指定で要約+files 一覧、run_id 指定で該当実行を取得。/api/state-table・/api/coverage-heatmap が同一成果物から応答 | — | 機能適合性 | FedEx | Medium |
| T04-D06 | /api/export/spec-xlsx が開ける xlsx（シート: 画面一覧/フォーム/項目定義/境界値/テスト設計/テストケース/遷移表） | — | 機能適合性 | FedEx | Medium |
| T04-D07 | /download-zip が壊れていない zip（testzip 通過・全ファイル格納） | — | 機能適合性 | FedEx | Medium |
| T04-D08 | /preview が report.json を返す。`path=../../etc/passwd` は拒否（軽確認・網羅は T06） | — | セキュリティ | Back Alley（軽） | High |
| T04-D09 | POST /api/sample-report で demo/sample_report が output に展開され、is_sample フラグで自前解析と識別される | zero_wait_sample_report.bundled_sample_missing / sample_mistaken_for_own_analysis | 機能適合性 | 契約ベース | Medium |
| T04-D10 | サンプル展開が実行履歴（/api/history, /api/history/runs）に混入しない | zero_wait_sample_report.sample_leaks_into_history | 機能適合性 | 契約ベース | Medium |
| T04-D11 | サンプルからの再クロール導線が行き止まりにならない（導線の実装と遷移先の実在性） | zero_wait_sample_report.recrawl_dead_end_on_sample | 機能適合性 | FedEx | Medium |
| T04-D12 | 実クロールが /api/history/runs に記録され、出所が usage_log.jsonl と実行中ジョブのみ | 監査証跡欠落（リスク分析 #4） | 信頼性/否認防止 | FedEx | High |
| T04-D13 | 既存 domain の再クロールで成果物が正しく更新され、login_required フラグが失われない | crawl（再実行時のデータ整合） | 信頼性 | FedEx | High |
| T04-D14 | screenshots/ が 0 バイト/プレースホルダでなく、report の screen 数と枚数一致（証跡欠落＝既知修正対象の重点確認） | crawl.outputs（screenshots） | 完全性 | FedEx | High |
| T04-D15 | UI 経路: `#report/<domain>` で結果パネルが表示され、再クロールボタンが存在する | — | 使用性 | Guidebook | Medium |

## 3. 網羅性の根拠

- **契約照合**: `quality/feature_contracts.yml` — feature `crawl` の outputs 5 種（report.html/json, screenshots, snapshot, audit.jsonl, performance samples）→ D01/D02/D14。feature `zero_wait_sample_report` の failure_modes 4 件全件 → bundled_sample_missing=D09, sample_mistaken_for_own_analysis=D09, sample_leaks_into_history=D10, recrawl_dead_end_on_sample=D11。
- **ISO/IEC 25010**: 機能適合性（D01/D03-07/D09-11）・信頼性（D02/D12/D13）・セキュリティ（D08）・完全性/否認防止は計画書リスク #4・#8 に対応（D12/D14）。
- **Whittaker ツアー**: FedEx Tour（生成→保存→閲覧→エクスポート→再クロールの通し追跡）を主線、Back Alley（D08 軽確認）を補助。
- **計画書リスク対応**: リスク表「誤った成果物（画面漏れ・欠損スクショ）を正常品として納品」→ D14 を重点化。「監査証跡の欠落」→ D12（T07 と分担、T04 は存在・記録経路のみ）。

## 4. 意図的に除外した条件と理由

| 除外条件 | 理由 |
|---|---|
| bundled_sample_missing の動的再現（demo/ を退避して POST） | `demo/` の改変はソース変更禁止（環境定義 §4-2）に抵触。同梱物の存在確認＋実装の静的確認（web/routes/report.py:218）に縮退し、動的挙動は「未実行」と明記 |
| パストラバーサルの網羅（エンコード変種・絶対パス等） | T06 の担当。本トラックは代表 1 入力の拒否確認のみ |
| サンプル結果画面での再クロールボタンの実クリック | クリックすると死にホストへの実行ジョブが走り、共有の実行履歴を汚染して V01/V02 の検証を妨げるため。導線実装と `/api/site` 応答から到達性を判定し「部分確認」と明記 |
| 結果閲覧タブ群の詳細機能（テストケース表編集・遷移表編集・新旧比較） | 計画書 §2.2 範囲外（存在と整合まで） |
| auth.json・reference_docs/・doc_fusion.json の生成 | T02（ログイン）・T05（参考資料）の担当。本クロールは認証・参考資料なしで実行 |
