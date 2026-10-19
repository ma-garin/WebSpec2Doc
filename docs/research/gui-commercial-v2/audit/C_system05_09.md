# C 監査: System05〜09（オートヒーリング / ドキュメント検証 / バッチ・スクリプト / バッチ・バックエンド / 影響度分析）

対象: origin/main 0efbd20 の worktree と http://127.0.0.1:8768（認証オフ）。ブラウザ実機操作はしていない。根拠は file:line か curl。推測は「未検証」。
共通: 5 System とも `tokens.css / app.css / app-components.css / components.css / user-menu.css` と `partials/topbar.html` を使う独自シェル（`app-shell` + `app-sidebar`、固定メニュー、skip-link あり）。8768 で 5 画面とも curl 200。

## System別の事実

### System05 オートヒーリング
- entry `/healing`（報告書一覧）と `/healing/settings`（接続先・実行）。直リンク `/healing/runs/<id>`、`/healing/reports/<id>`（web/routes/healing.py:333-426）。
- template healing.html / healing_reports.html / healing_report.html / healing_report_print.html。CSS healing.css(917)・healing-reports.css(469)。JS healing.js(2622)・healing-reports.js(1023)。
- 主要 API `/api/healing/projects|runs|reports|bundles`（healing.py:427-1210）。shell は `partials/healing-sidebar.html`（報告書/設定の 2 項目）+ 共通 topbar。
- primary action「ヒーリングを開始」。golden path: 接続先登録 → 接続を確認 → 開始(確認行) → 周回/ログ → PR 作成 → 承認 → マージ。実行ビューが「設定」ページ内にある（healing.html:41-46 の注記）のは IA 上の癖。
- 状態: empty(`hl-projects-empty` `hl-runs-empty` `hl-loop-empty`)、error(`#hl-error` role=alert)、permission(管理者以外は操作を描画しない)。報告書側の loading/partial は未検証。
- 破壊操作は全てインライン確認行: 開始/マージ/却下/中止/接続削除。confirm() 不使用（healing.html:112-157、healing.js:154-186）。承認・再検証・PR 作成は確認なし（healing.js:2588-2590）。
- evidence: リスク要約・高リスク先頭表示（healing.js:1498-1554）、報告書スクリーンショット `/api/healing/reports/<id>/screenshot`。
- responsive: width 系 @media なし。healing.css:532 は reduced-motion のみ（app.css 側の共通対応は未検証）。tests: `tests/healing_demo` のみ、route/UI テストは tests 直下に無し(grep)。
- 実態: implemented（接続した実リポジトリのファイルを書き換える）。

### System06 ドキュメント検証
- entry `/docverify`（doc_verify.py:61）。サイドバー 5 項目(レビュー/トレーサビリティ/指標/観点/設定)は doc_verify.html:26-37 に内蔵。`#hash` + pushState/popstate で deep-link 可（docverify-core.js:129-166）。
- template doc_verify.html + docverify/_global・_review・_tier(+_1〜_3)・_r3・_r4・_r5。CSS 7 本(docverify.css 359 他)。JS 12 本。API 5 系統（無印・r2・r3・r4・tier）。
- golden path: レビュー作成 → 文書取込 → 指摘 → 質問票 → 判定。別系統のトレーサビリティは 文書登録 → AI が検査 → つながりとレポート（_tier.html:7-9）。
- 状態: dv-banner(role=alert)、dv-toast(role=status)、aria-live（_global.html:12）、精度ページは未測定を「未測定」と出す（_r5.html）。
- 安全: AI 送信前に `DV.modal`（送る/取りやめる, docverify-r2.js:50）、未保存離脱（viewpoints.js:199）、文書削除は取消通知つき遅延削除（tier-1.js:112-116）。**検査のやり直しは確認なし**: tier-2.js:262、tier-3.js:250 が `tier/reset` を 1 クリック POST。to=1 は findings/reports/conclusion を空にする（doc_verify_tier.py:249-262）。同ファイルに権限処理 0 件。
- responsive: @media 計 4 本(各 CSS に 1 本)。tests: docverify_r1〜r5 の 7 ファイル約 150 件。実態: implemented。
- 内部世代名は採点表の下に全数。

### System07 バッチ・スクリプトのテスト
- entry `/batch-test`（batch_test.py:31）。`?job=<id>#<step>` で deep-link（batch-test.js:76,156）。template batch_test.html(194)、CSS batch-test.css(78)、JS batch-test.js(306)。API `/api/batch-test/jobs/...` 14 本。
- nav 4 工程: 取り込み / 観点とケース表 / テストコード / 書き出し。golden path: 案件作成 → スクリプト/仕様取込 → 読み取る → ケース表 → コード生成 → zip/xlsx/csv 書き出し。
- 状態: empty は各表にあり（batch-test.js:70）。error は日本語文＋再試行案内（batch-test.js:25）。permission/actor: batch_test.py に認証・権限処理 0 件。
- 破壊操作: 案件削除は 2 回押し(`armed`)で確認（batch-test.js:236）。ファイルを外すは確認なし（batch-test.js:243、再取込で戻せる）。
- **Generated/Exported/Executed/Verified**: Generated =「テストコードを生成しました」（batch-test.js:254）。Exported = 書き出し 3 種（batch-test.js:200-205）。Executed/Verified = 画面に存在しない。注記「この画面では実行しません」（batch_test.html:169）、「お使いの環境で 1 回実行して確かめてください」（batch-test.js:199）。完了/成功/合格/検証済みの語は 3 ファイルで 0 件(grep)。
- 紛らわしい点: 生成ファイル一覧が緑の合格アイコン `i-pass`、ケース行「根拠あり」が `p-pass`、KPI「根拠つき」が `ok` 色（batch-test.js renderCode/renderCases）。色だけ見ると合格に見える。
- responsive: @media 1 本(1200px, batch-test.css:59)。tests: test_batchtest.py 6 件。実態: implemented（コード生成まで。実行は範囲外と明示）。

### System08 バッチ・バックエンドのテスト
- entry `/backend-test`（backend_test.py:93）。`#job=..` / `?job=` deep-link（backend-test.js:325-326）、旧 `#s1〜s8` も受理。template backend_test.html(399)、CSS 309、JS backend-test.js(772)+backend-test-run.js(361)。API 約 30 本。
- nav: ホーム/案件/実行履歴/観点カタログ。案件内は 8 段階(目的・範囲/対象の読み取り/観点表/ケース表/テストデータ/テストコード/実行/判定・報告)。
- 承認帯 `#bs-approve`（backend_test.html:128-138）: 承認して次へ / 差し戻す(理由入力) / 前の版に戻す。version を送る楽観ロック（backend-test.js:653-663）。承認できない理由を `bs-approve-lock` に表示。
- KPI: ホーム/事実/ケース/結果で `stat-cards` を共通描画（backend-test.js:105-112）。
- Error + Next Action: `#bs-banner` が title/msg/next と再試行ボタン（backend_test.html:54-56、run.js:30）。API エラー文も再読み込みまで書く（backend_test.py:51,104,186）。
- 書込安全: 本番らしい接続先は読み取り専用帯（backend_test.html:122-125）、書込実行は不可（run.js:157）。テスト用でも書換テーブル一覧+チェックで有効化するモーダル（backend_test.html:373-378、run.js:164-168）。パスワード非保存、キャンセル、実行前状態へ戻す。ケース確定は役割チェック（backend_test_stages.py:335）。
- 判定画面は「事実 — 実行で確かめたこと」「判断 — QA の評価」「未検証 — 確かめていないこと」の 3 分離。機械判定/人が確定を区別。
- 一部未実装: 対象「API」「ジョブネット」は「次の版で対応します」と明示。responsive: @media 1 本（backend-test.css:292）。tests: tests/system08 の 7 ファイル約 47 件。実態: implemented + 一部 partial(明示)。

### System09 影響度分析
- entry `/impact`（impact.py:30）。template impact_analysis.html(151)、CSS impact.css(184)、JS は impact/api・graph・app・rea・system・cr を読込（impact_analysis.html:144-149）。API は `/api/impact/v2/*`（impact_api*.py）。
- nav(対象システム内): 概要/文書/ベースライン/つながり/変更要求/コード依存/設定/メンバー/監査。変更要求内: 変更内容/影響/関係図/マトリクス/テスト/承認/改修後レビュー。deep-link は `location.search` + popstate（app.js:109,259）。
- golden path: 対象システム作成 → 文書取込 → ベースライン → 変更要求 → 分析(LLM 送信量を確認 cr.js:85) → 影響 → 承認 → 改修後レビュー。
- 文書依存とコード依存は別タブ。コード依存は「静的依存（実行時の依存ではない）」を固定表示（rea.js:9,41）、状態は 推論/曖昧/未確認、到達は実測した結果にだけ「（実測）」（rea.js:25-29）、認証済み件数を別行（rea.js:21）。
- 弱点: コード依存タブの「対象サイト」は `/api/impact/rea-layer` が返すサイト一覧からの自由選択で、対象システムとの対応づけが無い（rea.js:95、impact.py:300-321）。8768 実測の sites は `demo.realworld.show` `localhost:8792`。文書側 BFS の深さ指定 UI は見当たらない（未検証）。
- 破壊操作: 対象システム/文書/つながり/メンバー削除は `ui.confirm` モーダル（system.js:96,191,293,319）。独り運用時は「本人承認」を監査ログに記録（cr.js:283）。
- 負債: `static/js/impact.js`(388 行)は template から読まれず(grep)、`window.confirm`（impact.js:312,321）と旧 API `/api/impact/jobs`（impact.py:35-300、権限処理 0 件）が残る。
- responsive: @media 2 本(1400/1280px)。tests: test_impact*.py 6 ファイル約 80 件。実態: implemented。

## 採点表

軸: 1 IA / 2 Golden Path / 3 Loading・Empty・Error・Recovery / 4 Product Truth・Evidence / 5 Permission・Safety / 6 Accessibility / 7 Responsive・Browser Navigation / 8 Visual Consistency / 9 Performance・Feedback / 10 Maintainability・Testability

| System | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 平均 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 05 オートヒーリング | 3 | 3 | 3 | 3 | 4 | 3 | 2 | 3 | 3 | 2 | 2.9 |
| 06 ドキュメント検証 | 3 | 3 | 3 | 3 | 2 | 3 | 2 | 2 | 3 | 2 | 2.6 |
| 07 バッチ・スクリプト | 3 | 3 | 3 | 3 | 2 | 3 | 2 | 3 | 3 | 3 | 2.8 |
| 08 バッチ・バックエンド | 3 | 3 | 4 | 4 | 4 | 3 | 2 | 3 | 3 | 3 | 3.2 |
| 09 影響度分析 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 2 | 2.9 |

根拠（1 句ずつ）:
- 05: IA は実行が「設定」配下(healing.html:41)。安全 4 は確認行 + admin 描画 + server require_admin 14 本。Resp 2 は width @media なし。保守 2 は healing.js 2622 行で route テスト無し。
- 06: 安全 2 は reset が無確認・無権限・無取消(doc_verify_tier.py:249)。Visual 2 は世代別 CSS 7 本とカード系の混在。保守 2 は世代名ファイル約 26 本。
- 07: 安全 2 は権限処理 0 件、ファイル外しは無確認。Truth 3 は「実行しない」明記の一方で緑の pass 表示が残る。
- 08: Error+Next Action・事実/判断/未検証・本番読取専用帯・承認/差し戻しで 3・4・5 軸が 4。Resp は 1200px 1 本のみで 2。
- 09: Truth は静的/実測/認証済みを分けるが site と対象システムが未対応づけで 3。保守 2 は旧 impact.js と旧 API の二重残存。
- 全 System: 実機（Chrome）での 6 状態（通常/実行中/失敗/0 件/狭幅/モーダル）確認はしていないため、A11y・Responsive・Visual は静的読みの採点（未検証）。

### System06: 内部世代名が通常 UI に出ている箇所（全数）
- 画面テキスト・title・aria-label・placeholder（`/docverify` の初期描画を curl して走査）: r2/r3/r4/r5/tier/世代/Round の出現 **0 件**。
- 動的生成の日本語文（docverify-*.js の grep）: 世代名を含む表示文 **0 件**。ただし「格」(tier)がドメイン語として出る（docverify-tier-1.js:179-180「AI は…と推定」「格を選んでください」）。利用者向けの説明が無いので要用語確認。
- 画面外だが利用者・保守者の目に触れる露出: URL/ネットワーク `/api/docverify/r2|r3|r4/...`・`/inspections/<iid>/tier/...`（doc_verify_r2.py:102、r3.py:74、r4.py:19、tier.py:17）。アセット名 `docverify-r2〜r5.js`・`docverify-tier-1〜3.css/js`（doc_verify.html:15-19,55-66）。DOM id `dvR4*` `dvt*` `data-r2`。サーバログ「R3 の保存に失敗」（doc_verify_r3.py:69,112,200,207）。
- その他の画面内の内部語: 「Ollama の接続先」（docverify-r2.js:140）。ダウンロード名は `trace.xlsx` `review-record-<id>.xlsx` で世代名なし。

## 共通化すべき高成熟パターン

1. インライン確認行 `.hl-confirm` と `setConfirmOpen/openConfirm/closeAllConfirms`（hidden と inert を同時切替、同時に 1 つだけ開く。confirm() 不使用）— healing.html:112-157、healing.js:162-186。
2. 管理者のみ描画 + server 二重化 `hl_admin` / `data-hl-admin` / `IS_ADMIN` / `require_admin()` — healing.html:30-34、healing.js:157-160、healing.py:442-1183。
3. 状態別に出せる操作だけ出す（押せない操作は非表示）、取消不能操作は文字色で danger — healing.js:1643-1717。
4. 判断前のリスク要約（高リスク先頭固定）と実書換の注意文 `.hl-caution` — healing.js:1498-1554、healing.html hero 行。
5. 書込実行モーダル（対象・書換テーブル・「テスト環境である」チェックで有効化）+ 本番読取専用帯 — backend_test.html:122-125,373-378、backend-test-run.js:141-168。
6. 段階承認帯 `#bs-approve`（承認/差し戻し理由/前の版へ/ロック理由/version 楽観ロック）= workflow 型の基準 — backend_test.html:128-138、backend-test.js:653-685、backend_test_stages.py:222,246。
7. エラーバナー title+msg+next+再試行、KPI は `stat-cards` 共通描画 — backend_test.html:54-56、backend-test.js:105-112、impact/rea.js:90 の `ui.failed`。
8. 事実 / 判断 / 未検証 の 3 分離 + 機械判定/人が確定の区別 — backend_test.html 判定段階。
9. Evidence ラベル規律（静的依存の固定注記、実測は実測した結果にだけ付与、認証済みは別カウント）— impact/rea.js:9,21,25-29。
10. 取消つき遅延削除（docverify-tier-1.js:112-116）と 2 回押し削除（batch-test.js:236）は確認行（1）へ統一する対象。

## P0 候補

- C-P0-1 (S06): 「検査をやり直す」が無確認・無権限・無取消で指摘/レポート/結論を消す。tier-2.js:262、tier-3.js:250、doc_verify_tier.py:249-262。確認行（パターン 1）と操作者記録を付ける。取消可否は未検証。
- C-P0-2 (S07/S09旧API): 書込 API に操作者・権限が無い。batch_test.py、impact.py(旧 `/api/impact/jobs`)で actor/role 0 件。旧 API は閉じるか認可を付け、S07 は S08 並みの actor 記録を持つ。
- C-P0-3 (S07): 生成しただけのコード/ケースが緑の合格表示（`i-pass` `p-pass` KPI `ok`）。Generated / Exported / Executed / Verified の 4 状態を画面語彙として分け、実行前は中立色で出す。
- C-P0-4 (S09): コード依存の「対象サイト」が対象システムと無関係に選べ、どのシステムの依存か誤認する。システムへの紐付け、または無関係の明示が要る。
- C-P0-5 (全 System): 狭幅対応が薄い。width 系 @media は S05 0 本、S07/S08 各 1 本(1200px)、S06 計 4 本、S09 2 本。1024px 以下の崩れは実機未検証。商用前に幅別の実機確認が必須。
- C-P0-6 (S05): 承認・再検証・PR 作成は確認なしで実行。PR 作成は外部リポジトリに副作用（healing.py:870）。承認の取消可否と PR 作成の確認要否を基準化する（未検証）。
