# インシデントレポート（ISO/IEC/IEEE 29119-3 準拠）— E2E システムテスト全件実行 2026-08-23

| 項目 | 内容 |
|---|---|
| 対象テスト実行 | L3 E2E 全件（15 failed / 127 passed / 2 skipped / 480 秒）、L1・L2（2 failed / 3266 passed） |
| 一次データ | `scratchpad/testrun/L3-e2e.log`、`scratchpad/testrun/L1L2-unit-integration.log` |
| 判定方法 | 静的読解（テストコード・実装コード・ログの断定行）のみ。**テスト再実行・サーバ起動・git 操作は行っていない** |
| 報告日 | 2026-08-23 |
| 状態 | Open（対処未着手） |

**本レポートの重要な結論: 17 件の失敗のうち、製品欠陥と断定できたものは 0 件。** 主因はテスト側の陳腐化（仕様変更への未追随）と前提データ未整備である。ただし「製品欠陥が無い」ことの証明ではない。下記 7 件は検証が空白のままであり、当該機能の健全性は**未検証**である。

---

## 1. サマリ表

| ID | テスト | 分類 | 重大度 | 判定根拠（file:line） |
|---|---|---|---|---|
| INC-01 | ST-008 test_st008_syscard_opens_autorun | テスト陳腐化 | 中 | 検証マーカー不適切。AutoRun 画面自体は描画済み（L3-e2e.log:11-107 の aria snapshot に受付画面全体）。`#autorun-leadbar` は状態駆動で、状態が無いとき `hide()` が `display:none` にする（static/js/autorun-leadbar.js:30-34）。tests/e2e/system/test_st2_navigation.py:48 |
| INC-02 | ST-031 test_st031_all_nav_views_render_without_js_errors | テスト陳腐化 | 中 | docs 系ナビでは `data-system="autorun"` の項目を system-scope.js が非表示化する（static/js/system-scope.js:58-62、templates/partials/nav.html:10）。テストは docs 系のまま `auto-run` をクリックしようとする（tests/e2e/system/helpers.py:52、test_st2_navigation.py:73）。**JS エラーの assert には到達していない**（L3-e2e.log:111-128 は Locator.click タイムアウト） |
| INC-03 | ST-010 test_st010_generate_starts_with_valid_url | テスト陳腐化（手順欠落） | 重大 | `#url-input` は `#view-generate` 内（templates/partials/view-generate.html:2,33）。テストは `/`（dashboard）を開いたまま generate ビューへ遷移せずに fill する（test_st3_docgen.py:26-27）。仕様は「generate画面で対象URLを入力し実行する」（docs/system_test_cases.csv:11） |
| INC-04 | ST-011 test_st011_invalid_url_shows_validation_message | テスト陳腐化（手順欠落） | 中 | INC-03 と同一原因。test_st3_docgen.py:44 |
| INC-05 | ST-012 test_st012_run_history_shows_past_run | **判定不能** | 中 | `POST /api/sample-report` は成功（assert 通過）だが実行履歴が「実行履歴がありません」（L3-e2e.log:303）。サンプル出力先と run-history の読み取り元のテナントスコープ一致は**未検証**。test_st3_docgen.py:64 |
| INC-06 | ST-014 test_st014_approval_decisions_ui_is_operable | 環境・データ依存（前提未整備） | 重大 | 前提「AutoRun対象の設定が完了している」（csv:15）を fixture が作らない。`#autorun-leadbar button` は実行状態が無いと出ない（autorun-leadbar.js:30-34,45-49）。L3-e2e.log:305-308 |
| INC-07 | ST-016 test_st016_report_page_loads | テスト陳腐化（URL 不整合） | 中 | `/autorun-report` は未定義。実装のルートは `/autorun/report/<domain>`（web/routes/autorun_report.py:217）。404 応答（L3-e2e.log:310-312） |
| INC-08 | ST-017 test_st017_pending_approval_survives_navigation | 環境・データ依存（前提未整備） | 中 | 前提「承認待ちステップが存在する」（csv:18）を fixture が作らない。INC-06 と同一機構。L3-e2e.log:313-316 |
| INC-09 | ST-020 test_st020_traceability_page_loads | テスト陳腐化（URL 不整合） | 中 | `/traceability` は未定義。実装は `/traceability/matrix`・`/traceability/view`（web/routes/traceability.py:38,94）。404 応答（L3-e2e.log:317-320） |
| INC-10 | ST-029 test_st029_change_own_password | **判定不能** | 中 | `.sysselect-account` クリック後も `/systems` に留まり `#view-account` が DOM に存在しない（L3-e2e.log:327-346 の aria snapshot はシステム選択画面。「個人設定 → /account」リンクは存在する）。同一操作の ST-009（MEMBER）は PASS。再現条件が特定できないため憶測で分類しない。test_st5_member_views.py:60 |
| INC-11 | ST-030 test_st030_usage_view_renders | テスト陳腐化 | 軽微 | `templates/index.html` に `view-usage` の include が無い（index.html:73-106）。使用量は独立ページ `/usage` が `partials/view-usage.html` を単体レンダリングする（web/routes/usage.py:27-30）。テストは SPA 内 `switchView('usage')` を前提（helpers.py:64） |
| INC-12 | ST-026 test_st026_role_change_grants_admin_access | テスト陳腐化（セレクタ消滅） | 中 | `#uadm-tenant-form` は `templates/`・`static/js/` に**1 件も存在しない**（grep 0 件）。ロール変更 API 自体は成功している（test_st6_admin.py:118 の assert を通過）。test_st6_admin.py:124 |
| INC-13 | ST-027 test_st027_last_owner_cannot_be_demoted | テスト陳腐化（仕様変更） | 中 | owner ロールは廃止され admin に統合済み（web/services/auth_store.py:37-43 `_LEGACY_ROLE_ALIASES = {"owner": ROLE_ADMIN}`）。不変条件は「テナントの管理者を 0 人にしない」に再定義（auth_store.py:713-716, 873-893）。ST fixture は admin が 2 名いるため降格は**正しく許可される**。詳細は §3.1 |
| INC-14 | ST-028 test_st028_api_token_issue_and_revoke | テスト陳腐化（契約差） | 中 | 実装は論理削除。`revoke_api_token` は `revoked_at` を設定するのみ（auth_store.py:1255-1262）、`list_api_tokens` は `revoked_at` で絞り込まない（auth_store.py:1245-1253）。仕様の合否基準は「削除後はそのトークンでのAPIアクセスが拒否される」（csv:29）であり、一覧からの消失ではない。詳細は §3.2 |
| INC-15 | test_completed_results_survive_leaving | 環境依存 | 中 | 解析対象 `DEMO_URL = http://127.0.0.1:8767/index.html`（tests/e2e/test_stale_state_e2e.py:34）。`tests/e2e/*.py` と `Makefile` に 8767 を**起動する処理が無い**（grep で参照のみ 6 件）。到達不能→解析 0 件。test_stale_state_e2e.py:116 |
| INC-16 | test_ui_contract.py::TestSystemSelect::test_offers_exactly_three_systems | テスト陳腐化（仕様変更） | 中 | 実装は 4 システム（templates/system-select.html:38「4 つは独立したシステムです」、syscard-doc/test/run/cli）。System 02「テスト活動支援」が追加済み。tests/test_ui_contract.py:123-126 |
| INC-17 | test_ui_contract.py::TestSystemSelect::test_names_all_systems | テスト陳腐化（文言変更） | 軽微 | 実装の System 04 の表示名は「CLI / API」（system-select.html、L3-e2e.log:344 の aria snapshot で確認）。テストは「CLI モード」を期待（tests/test_ui_contract.py:138） |

### 分類別件数

| 分類 | 件数 | ID |
|---|---|---|
| 製品欠陥 | **0** | — |
| テスト陳腐化 | 11 | INC-01,02,03,04,07,09,11,12,13,14,16,17 のうち 12 件（うち INC-17 は軽微文言）→ 実数 12 |
| 環境・データ依存 | 3 | INC-06, INC-08, INC-15 |
| flaky | 0（断定できたもの） | — |
| 判定不能 | 2 | INC-05, INC-10 |

（内訳の合計は 17。テスト陳腐化 12・環境依存 3・判定不能 2。）

---

## 2. 最優先 3 件の結論

### 2.1 ST-031 は本日の変更による回帰か → **回帰と断定できない（否定側の根拠あり）**

- 失敗の断定行は `Locator.click: Timeout` であり、`assert not errors`（JS エラー検査）には**到達していない**（L3-e2e.log:111-128）。すなわち**本日の JS 変更に起因する pageerror は 1 件も観測されていない**。
- 失敗した要素は `<button class="app-nav-item" data-view="auto-run" data-system="autorun">`。これを非表示にするのは `static/js/system-scope.js:58-62`（`belongs()` が false の要素へ `display:none`）。同ファイルは本日の変更対象（`ta-design.js` / `ta-execution.js` / `ta-analysis.js` / `view-testcase-grid.js` / `view-ta-*.html`）に含まれない。
- 本日追加された testlab 系ナビ項目（nav.html:26-65）は `data-system="testlab"` であり、autorun 項目の可視性に影響しない。
- **未検証**: 変更前リビジョンでの当該テストの合否は git 参照を禁止されているため確認していない。「本日以前から失敗していた」ことまでは証明していない。

### 2.2 ST-027 最後のオーナー降格ガードは存在するか → **存在する（別の形で）。製品欠陥ではない**

- ロールモデルは 2 値（member / admin）に統合済みで、`owner` は入力時に admin へ読み替えられる（auth_store.py:37-43）。したがって「最後のオーナー」という概念は現行仕様に存在しない。
- 現行の不変条件は「テナントの管理者を 0 人にしない」。`update_user` は降格・無効化時に `_assert_admin_remains` を呼び（auth_store.py:713-716）、対象を除いた有効な admin が 0 人なら `AuthError("last_admin")` を送出する（auth_store.py:873-893）。
- ST fixture は owner（=admin として作成）に加えて `st-admin@example.com` を admin として作る。よって降格後も admin が 1 名残るため、**この降格が成功するのは仕様どおりの正しい挙動**である。
- 結論: セキュリティ／インテグリティ欠陥ではない。テスト側が旧ロールモデルのままである（§3.1 に修正方針）。

### 2.3 ST-028 は論理削除 vs 物理削除か → **実装は論理削除（revoke）。テストが物理削除を期待している**

- `revoke_api_token` は `UPDATE api_tokens SET revoked_at = ...`（auth_store.py:1255-1262）。物理削除は行わない。
- `list_api_tokens` は `revoked_at` で絞らず全件返す（auth_store.py:1245-1253）。ログの残存トークンも `revoked_at` が設定済みであり、実装は意図どおり動作している。
- 仕様（csv:29）の合否基準は「削除後はそのトークンでのAPIアクセスが拒否される」。一覧からの消失は仕様が要求していない。
- **未検証**: 失効済みトークンで実際に API アクセスが拒否されるか、および UI（`static/js/account-view.js:55` の `token-rows` 描画）が失効状態を利用者に区別表示するかは確認していない。

---

## 3. 製品欠陥と判定したもの

**該当なし（0 件）。**

静的読解の範囲で、15 件の E2E 失敗と 2 件の単体失敗いずれについても、実装側の不具合を断定できる根拠は得られなかった。ただし以下 2 点は「欠陥が無い」ことの証明ではない。

- INC-05・INC-10 は判定不能であり、製品欠陥である可能性を排除していない。
- INC-06・INC-08・INC-14 が本来検証するはずだった機能（AutoRun 段階承認の操作性、承認待ちの保持、失効トークンの拒否）は、今回**一度も実行されていない＝未検証**である。

---

## 4. テスト陳腐化: テストと実装のどちらを直すか

| ID | 直す対象 | 判断根拠 |
|---|---|---|
| INC-01 (ST-008) | **テスト** | csv:9 の期待結果は「AutoRunシステムへ遷移する」。aria snapshot で遷移は成立している。マーカーを `#autorun-leadbar` から AutoRun 受付画面の恒常要素（例 `#autorun-url` / `#autorun-start-btn`。tests/test_ui_contract.py:156-157 が存在を保証）へ変更する |
| INC-02 (ST-031) | **テスト** | システム分離（docs / testlab / autorun）は system-scope.js の明示的な設計意図（同ファイル冒頭コメント）。docs 系の網羅対象から `auto-run` を外し、AutoRun 系ビューは `/auto-run` を開いた状態で別途巡回する |
| INC-03/04 (ST-010/011) | **テスト** | 仕様（csv:11）が「generate画面で」と明記。`#add-site-btn`（templates/index.html:46）または `switchView('generate')` で generate ビューを開く手順を追加する |
| INC-07 (ST-016) | **テスト（第一選択）** | 実装ルートは `/autorun/report/<domain>`。`domain` を持つ実行結果を作ってから開く。※「ドメイン非依存の `/autorun-report` 入口が製品として必要か」は仕様判断であり、必要と決まればその時点で製品側課題に格上げする（現時点では**未決**） |
| INC-09 (ST-020) | **テスト** | 実装ルートは `/traceability/view`。テストの URL を修正する |
| INC-11 (ST-030) | **テスト** | 使用量は SPA 内ビューではなく独立ページ `/usage`。`page.goto(f"{base}/usage")` に変更する。併せて helpers.py:64 の docstring から「usage」の記述を除く |
| INC-12 (ST-026) | **テスト** | `#uadm-tenant-form` は実装から消滅済み。`/user-management` の現行の恒常要素を実測して差し替える（helpers.py 冒頭「推測セレクタを追加しない」という自ルールの違反事例） |
| INC-13 (ST-027) | **テストと仕様書の双方** | ロールモデル変更（owner 廃止）が csv:28 に未反映。テストは「唯一の admin を降格しようとして拒否される」形へ書き換え、fixture で他の admin を残さない条件を作る |
| INC-14 (ST-028) | **テスト** | 合否基準を仕様（csv:29）に合わせ、「失効後にそのトークンで API を叩くと拒否される」を検証する。一覧の消失は要求されていない |
| INC-16/17 (UI 契約) | **テスト** | System 02 追加と System 04 の名称「CLI / API」は実装側の意図（system-select.html:38, 63-78）。テストを 4 システムへ更新する。併せて `web/routes/pages.py:57` の docstring「CLI モード（System 03）」が旧番号のまま（**軽微な文書不整合**） |

---

## 5. 環境・データ依存 / flaky の根拠

| ID | 分類 | 断定根拠 |
|---|---|---|
| INC-06 (ST-014) | 環境・データ依存 | csv:15 の前提「AutoRun対象の設定が完了している」を `tests/e2e/system/conftest.py` の `system_server` fixture が作らない（fixture はテナントと owner/admin/member の作成のみ）。leadbar はランタイム状態が無ければ描画されない |
| INC-08 (ST-017) | 環境・データ依存 | csv:18 の前提「承認待ちステップが存在する」を fixture が作らない。同上 |
| INC-15 (stale_state) | 環境依存 | `127.0.0.1:8767` のモックサイトが必要だが、`tests/e2e/*.py` と `Makefile` に起動処理が存在しない（参照のみ） |
| — | flaky | **今回 flaky と断定できた失敗は 0 件。** 隔離機構は生きているが `_QUARANTINED_TESTS` は空（tests/e2e/conftest.py:56）であり、今回の 15 件はいずれも隔離対象外（＝スキップされずに実行された） |
| INC-05・INC-10 | 判定不能 | 断定に足る根拠が無い。flaky・製品欠陥のいずれとも決めない |

**環境の共通前提（誤検知の排除）**: システムテストは専用ポート・専用 DB（`auth.e2e-system-<runid>.db` / `viewpoints.e2e-system-<runid>.db`）でサーバを起動し、テスト後に破棄する（tests/e2e/system/conftest.py:72-115）。開発用 DB や既存サーバへの相乗りは親 conftest が阻止する（tests/e2e/conftest.py:63-83）。よって**「他プロセスとのデータ共有」に起因する失敗は想定しにくい**。

---

## 6. 未判定の残件

| # | 残件 | 理由 |
|---|---|---|
| R-1 | INC-05（ST-012）の真因 | `/api/sample-report` の出力先と run-history の読み取り元のテナントスコープ一致を未確認。ツール実行上限のため未着手 |
| R-2 | INC-10（ST-029）の再現条件 | 同一操作の ST-009 が PASS のため単発事象の可能性があるが、trace / video を確認していない。`e2e/artifacts/videos` に記録がある想定（未確認） |
| R-3 | 失効済み API トークンでの認証拒否 | §2.3。`revoked_at` を認証時に検査しているかを未確認 |
| R-4 | 失効トークンの UI 表示 | `static/js/account-view.js:55` 付近の描画で失効状態を区別しているかを未確認 |
| R-5 | ST-026 のロール昇格後の実アクセス可否 | セレクタが陳腐化しているため、admin 昇格が実際に権限に反映されるかは**未検証**のまま |
| R-6 | 変更前リビジョンでの ST-031 の合否 | git 参照が禁止のため未確認。§2.1 は「本日の変更ファイルが失敗経路上に無い」ことまでしか示していない |
| R-7 | 失敗 15 件以外（passed 127 件）の妥当性 | 本レポートの対象外。PASS が実質的な検証になっているかは検査していない |

---

## 7. 推奨する対処順序

1. **INC-03（ST-010・Critical）と INC-06（ST-014・Critical）** — 最も重要な機能の検証が空白。テスト手順の修正と前提データ生成を最優先。
2. **INC-13 / INC-16 / INC-17** — 仕様変更（owner 廃止・System 02 追加）に対する契約テストと `docs/system_test_cases.csv` の同期。仕様書側の陳腐化を放置すると同種の誤検知が再発する。
3. **INC-15** — 8767 のモックサイトを fixture 化するか、当該テストを対象外にする（現状は毎回赤になる）。
4. **R-1 / R-2** — 判定不能 2 件の追跡調査。
5. **R-3** — 失効トークンの拒否は**セキュリティ上の実質要件**であり、テスト書き換え時に必ず含める。

---

## 追補: 本サイクルで新規検出した製品欠陥（INC-P01）

E2E の失敗切り分けとは別に、**応答時間ベースライン測定**（本サイクルで新設）により製品欠陥を 1 件検出した。
既存の自動テストでは検出できない種類のため、ここに記録する。

| 項目 | 内容 |
|---|---|
| ID | INC-P01 |
| 分類 | **製品欠陥**（性能効率性・スケーラビリティ） |
| 重大度 | 中（現時点では利用者に見える障害に至らないが、利用に比例して劣化し続ける） |
| 事象 | `GET /api/history/runs` が実行履歴を全件・ページングなしで返す |
| 実測 | **3,770 件 / 1,760,456 bytes / 175〜189 ms**（3 回測定）。同時測定した他 7 エンドポイントは 2〜12 ms |
| 原因 | `web/routes/auto_run.py:199-211` に件数制限・ページング・上限が無い |
| 波及 | 消費側 2 箇所も全件を DOM へ一括描画する: `static/js/ta-execution.js:82`（実行画面・実測 3,728 行）、`static/js/view-run-history.js:119`（System 01 履歴画面） |
| 再現条件 | 実行履歴が蓄積された状態で実行画面または履歴画面を開く。本セッション中も 3,752 → 3,770 件へ増加した |
| 検出できなかった理由 | ISO/IEC 25010 の性能効率性に該当する既存テストは 3,106 件中 **5 件**のみで、応答時間・応答サイズに関する自動検証が存在しない（`iso25010-coverage.md`） |
| 推奨対処 | (1) API に `limit` / `offset` を導入し既定を直近 N 件にする (2) 画面側を追加読み込みにする (3) 応答時間・サイズの回帰テストを追加する |
| 証跡 | `docs/quality/evidence/perf-baseline.csv` |

---

## 追補: R-05（ST-029）の判定

**判定: テスト陳腐化（製品欠陥ではない）。INC-10 / R-2 の「判定不能」を解消する。**

| 項目 | 内容 |
|---|---|
| 事象 | `test_st029_change_own_password` が `#view-account` の `Locator expected to be visible` で失敗 |
| 再現条件 | **単発事象ではなく決定論的に 100% 再現する。**flaky ではない |
| 真因 | テストが `.sysselect-account` を `click()` していた。これは `templates/system-select.html:21` の**コンテナ `div`** であり、クリックしても遷移しない。個人設定への実導線は同 26 行目の `<a class="sysselect-text-btn" href="/account">個人設定</a>` |
| 製品側の健全性 | 導線（`/account`）→ `web/routes/pages.py:23,92`（`account` を許可ビューとして index.html をレンダリング）→ `static/js/core.js:185` が `_viewFromPath` で `account` ビューを開く → `templates/partials/view-account.html:22` の `#password-form` → `web/routes/account.py:322` の `POST /api/auth/password` まで**一気通貫で動作する**。新パスワードでの再ログインまで PASS を確認済み |
| 対処 | テスト側を実導線（`.sysselect-account a[href="/account"]`）へ追随。製品コードは無変更 |

### 併せて確定した 2 件（R-04 の 4）

| ID | 判定 | 真因 / 根拠 |
|---|---|---|
| ST-020 | テスト陳腐化 | テストが叩いていた `/traceability` は存在しない。実ルートは `/traceability/view`（`web/routes/traceability.py:94`）と API の `/traceability/matrix`（同 38）のみ |
| ST-030 | テスト陳腐化 | 使用量ビューは**アプリシェルに含まれない**。`templates/index.html` の include 一覧に `partials/view-usage.html` が無く、`web/routes/usage.py:27-30` の `GET /usage` が当該 partial を単体でレンダリングする。よって `switchView('usage')` では到達できない |

### 付随して観察した設計上の不整合（製品欠陥とまでは断定しない・未対処）

`GET /usage` は共通レイアウト（`base.html` / ナビ / 共通 CSS）を経由せず `partials/view-usage.html` を直接返す。
描画自体は partial 内のインライン `<style>` / `<script>`（`templates/partials/view-usage.html:59`）で成立するため機能欠陥ではないが、
`web/routes/traceability.py:94-101` の docstring が「以前は partial 断片だけを返しており CSS も JS も読み込まれず表が描画されなかった」として**同型の問題を過去に修正済み**である。
`/usage` は同じ形のまま残っており、ナビからの導線も無い（`/usage` を直接開く以外に到達手段が無い）。**要否の判断は未実施。**

---

## 追補: R-04c で判明した事項（2026-08-23 / ST-014・ST-016・ST-017 の修正時）

`tests/e2e/system/test_st4_autorun.py` の失敗 3 件を現行実装へ追随させる過程で、
実装を読み・実際に叩いて確認した事項を記録する。**製品欠陥と断定できたものは無い。**

### 1. `/autorun-report`（ドメイン非依存の入口）は実装に存在しない — INC-07 の追認

- 実ルートは `/autorun/report/<domain>`（`web/routes/autorun_report.py:217`）と
  `GET /api/autorun/report/<domain>`（同 231）の 2 本のみ。`grep -n "@bp.route\|@bp.get"` で全数確認した。
- 404 の原因は URL 変更であり、テスト側の陳腐化。テストは `/autorun/report/<domain>` へ変更した。
- ただし **404 の条件は 2 つある**: URL 不正だけでなく、
  `_domain_dir(domain).is_dir()` が偽（＝その対象の成果物が 1 つも無い）でも `abort(404)` になる
  （`web/routes/autorun_report.py:221-223`）。成果物が無いときに「まだ実行結果がありません」を
  案内する画面は存在せず、利用者には素の 404 が出る。
  **これを製品欠陥とするかは仕様判断であり、INC-07 と同じく未決のまま据え置く**（本サイクルでは実装に触れていない）。

### 2. 段階承認 UI は「実行中の状態」からしか到達できない（テスト容易性の欠如）

- `#autorun-leadbar` は既定 `display:none`（`templates/partials/view-auto-run.html:6`）で、
  描画するのは `static/js/autorun.js:895` と `static/js/autorun-stages.js:541` の実行時経路だけ。
  よって **AutoRun を実走させない限り `#autorun-leadbar button` は永久に現れない**。
  旧テストの `wait_for_selector` タイムアウトはこれが原因で、実装の欠陥ではない。
- 判断ダイアログ `#autorun-decisions` を開く唯一の呼び出し元も
  `static/js/autorun-stages.js:581-583`（承認待ちステップの検出時）である。
- さらに質問の内容は `qa_process/stages.json` に「前提（`assumed`）」項目が在ることが前提で、
  `Pipeline.initial()`（`src/autorun/stages.py:264-265`）には項目が 1 つも無い。
  すなわち **前提データを置かずに承認 UI を検証する手段が実装側に無い**。
- 対処（テスト側）: `POST /api/autorun/decisions` に stages.json を作らせ、
  `GET /api/autorun/stages` が返す現行スキーマへ `plan-assume-*` 項目を足して置き換え、
  公開 API `window.autorunDecisions.open()` で開く。LLM 実行は行わない。
- **残る弱点**: 「実行中に承認待ちへ遷移し、そこでダイアログが開く」という繋ぎ込み部分
  （`autorun-stages.js:541,581-583`）は**依然として未検証**である。

### 3. テナント別出力ディレクトリはテストから一意に特定できない

- `scoped_output_dir`（`web/tenancy.py:51-56`）の slug は DB 由来で、テストからは決め打ちできない。
- 同一ドメイン名のディレクトリが複数テナント配下に併存する（実測: `output/tenants/` に
  `default` / `e2e-tenant-a` / `st-system-tenant` の 3 つがあり、いずれにも
  `sample.webspec2doc.local` が存在した）。更新時刻でも判別できなかった。
- 対処（テスト側）: 前提データ用のドメインを実行ごとに一意（`st-<uuid8>.example.com`）にし、
  glob の一致が 1 件であることを assert して特定する。
