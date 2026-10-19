# Agent B 監査: System01 / System01 app / System02 / System03 / System04

対象: wt-gui（origin/main 0efbd20）、監査用サーバ 127.0.0.1:8768（認証オフ）。
方法: コード読み + curl。ブラウザ未使用のため、実描画・キーボード操作・狭幅の挙動は「未検証」。視覚系の軸はコード根拠のみ。
curl: /dashboard /generate /doc-app /test-automation /auto-run /cli /systems /sites/demo.realworld.show/{spec,tests} /sites/localhost:8792/spec は 200。未解析ドメインの /sites/nonexist.example/spec は 302 で "/" へ。

## System別の事実

### System01 ドキュメント作成（/dashboard・/generate・/sites/<d>/spec の REA タブ）
- entry: `/` -> 302 `/dashboard`（pages.py:90-95）。route: `web/routes/pages.py`。template: `index.html` + `partials/view-dashboard.html`・`view-generate.html`。REA は `workspace.html:235`（seg `data-m="reverse"`）と :246（`#spec-reverse`）。
- JS: `static/js/ta2/ws-reverse.js`（442 行）、`ws-spec.js:360-371` が REA タブを出し分け。CSS: `static/css/reverse-analysis.css`。API: `GET /api/reverse-analysis?domain=`、`POST /api/sites/<d>/reverse-analysis/run`（`web/routes/reverse_analysis.py:340,360`）。
- shell: dashboard/generate は旧シェル（`partials/topbar.html`）、REA は workspace シェル（`workspace.html:152` が同じ topbar を include）。nav は `partials/nav.html`（ダッシュボード・実行履歴・品質観点・観点管理）。
- primary action: dashboard は「解析を始める」、REA は「リバース解析を実行 / 再実行」（ws-reverse.js:105）。golden path: URL 入力 -> 画面解析 -> 実行 -> レポート -> 仕様タブ「リバース解析」-> 実行 -> 根拠タブ。
- REA の状態: loading（:47 role=status + aria-busy）/ empty（:323）/ provider_unavailable（:324、HTTP 422 `reverse_analysis.py:356`）/ error（:325）/ partial（`partialHtml` :177「一部のみ取得しました」+次の行動）/ busy 409 / no_runtime 422。permission: `site_workspace` が admin 以外に 403（pages.py:129）。
- Before/After: `summaryHtml` :187-214。数値が無いと「未確認」、追加解析時間は「未計測」、`measured_once` で「単発測定」。実測 curl（demo.realworld.show）: 静的候補 0->62、Route 0->10、API(実測) 17->17、Module 依存 0->51、「QA に答えられる問い」は null で未確認表示、provider は REA 6.7.0 available。
- Evidence state: 実測/静的/推論/曖昧/未確認/利用不可の 6 値（:16）。根拠表の行は tabindex=0 + aria-label、詳細は `role=dialog aria-modal`（:360）でフォーカストラップ・Escape あり（:53-60）、tablist は roving tabindex（:226-227）。
- destructive: 無し（失敗時は「結果は更新していません」`reverse_analysis.py:369`）。dashboard 履歴の削除系は未検証。
- deep-link: `/sites/<d>/spec` は有効。REA タブ単位の URL は未検証。dashboard は `VIEW_PATHS`/`popstate`（core.js:122-156）。
- tests: `test_reverse_analysis_{gui_api,adapter,normalize,reconcile,runtime,real,cli}.py`、`test_rea_impact_layer.py`、`test_pages_routes.py`、`test_app_wizard.py`、e2e `test_workspace_shell_e2e.py`。実態: **implemented**（実 REA 実行に接続、curl で実データ確認）。

### System01 app ドキュメント作成(app)（/doc-app）
- entry `/doc-app`（pages.py:149-157）、`index.html` を `app_mode=True` で共用（:26,:36,:56,:230）。入力は `view-generate.html:31-51` の差し替えブロック、JS は `static/js/doc-app-mode.js`。API は URL 版と同じ `/api/discover-stream`・`/run`（`discover.py:54`・`crawl.py:133` が `app_mock.is_app_target` で分岐）。
- 実態は **mock**: `web/services/app_mock.py` は固定 6 画面（SampleShop、:21-28）を返し、成果物は `demo/sample_report_app` を `copytree`（:119）するだけ。APK/.app の解析・エミュレータ探索・未到達 Activity 解析は存在しない。
- `#app-file`（APK 選択）と `#app-device`（実行先）は `doc-app-mode.js` が accept/option を差し替えるだけで、値はどこにも送信されない（grep: 参照は doc-app-mode.js のみ）。パッケージ select も `com.example.sampleshop` の 1 択（view-generate.html:42）。
- 誤認文言は「P0 候補」参照。モックの開示は system-select のカードのバッジ「モック」（:92）と HTML コメント（:89）だけで、/doc-app 画面内には無い（curl で "モック" 0 件）。
- shell/nav は System01 と同一。loading/empty/error は URL 版の流用（模擬のため実失敗系は発生しない）。permission は未検証。destructive 無し。
- tests: `/doc-app`・`app_mock` を参照するテストは 0 件（grep）。

### System02 テスト自動化（/test-automation・/sites/<d>/tests）
- entry: `/test-automation` は `workspace.html` を `mode=test-only` で返す（pages.py:137-140）。サイト内は `/sites/<d>/tests`。template `workspace.html`（475 行）、JS `static/js/ta2/*.js`、API `web/routes/ta2.py`。
- shell: 共通 topbar を include（`workspace.html:152`）。nav は rail（ホーム・仕様・テスト・変更・定期・報告・チーム、:41-80）。nav 2 つに aria-label、user menu に aria-haspopup/expanded、一覧に listbox ロール。
- primary action: 「＋ 新しいテスト」`#new-btn`、「▶ 全件実行」`#run-all-btn`（:140）。golden path: サイト選択 -> 仕様/テスト -> テスト実行 -> 実行と結果。
- REA 連携: `ws-rea-viewpoints.js` が「実行と結果」ビュー（`#run-reaview`、workspace.html:258）で `GET /api/sites/<d>/rea-test-viewpoints`（ta2.py:970）を描く。タイルは「テスト候補数 / 新規観点数 / Evidence 付き候補数 / 実行対象（実測で到達）」（:54-57）、リードに「到達・実行は未確認のものを含みます」（:52）、0 件時は「0 件（未確認）」+次の操作（:42-44）、各行に「根拠」「到達」「位置: 未確認」。実測 curl: demo.realworld.show は 40->57（新規 17、実行対象 3、探索済み 8）。
- 区別の実態: 「実行対象（実測で到達）」は"実行できる"の意味で、"実行した"件数・合否はこの画面に並ばない。ラベルは正確だが「実行済み 0 件」の明示が無い。
- 状態: loading（rv-loading role=status）/ error / empty あり。permission: `/test-automation` 自体は `_may_use_testlab` を呼ばず（pages.py:137-140）、`/sites/<d>/*` だけ admin 制限（:129）。カードは admin 以外に出さない設計（system-select.html:108）。
- tests: `test_rea_test_viewpoints.py`、`test_ta2_api.py`、`test_ta2_store.py`、`test_ta2_recrawl_domain.py`、`test_comparison_workspace.py`、e2e `test_workspace_shell_e2e.py`。実態: **implemented**。

### System03 AutoRun（/auto-run）
- entry `/auto-run`（`_VIEW_NAMES`、pages.py:21）-> `index.html` の `partials/view-auto-run.html`。JS `static/js/autorun*.js`（autorun.js 1290 行・autorun-stages.js 844 行ほか）。API `web/routes/auto_run.py`・`autorun_stages.py`・`autorun_report.py`。shell は旧シェル（共通 topbar、nav は「受付」「過去履歴」）。
- 静的候補の探索: `view-auto-run.html:174-175`（`#autorun-static-routes`）+ `autorun-static-routes.js`（251 行）+ `static_route_probe.py`（POST/GET `/api/sites/<d>/static-routes/probe`）。GET の遷移だけで送信・入力・削除はしない旨をリード文に明記（js:204）。
- 状態: ドメイン未選択（:183）/ 読み込み中（:184）/ error（role=alert :180,:186）/ REA 未実行（「System01 でリバース解析を実行すると候補が入ります」:191）/ 未探索（:194）/ 探索中（ボタン「探索中…」+ aria-busy :207 + aria-live=polite :107）。
- Evidence 表示: 実測で到達（認証済み/未認証を分離、:74-75,:130-131）、未到達、認証等で未確認、System02 で実行対象になった観点の件数（:138）。注記「到達＝GET で留まっただけ。画面の正しさの証明ではない」（:173-174）。
- destructive: 無し（GET のみ）。permission: ドメイン入力に `aria-label`（:97）。サーバ側のロール制限は未検証。
- tests: `test_static_route_probe.py`、`test_auto_run.py`、`test_autorun_*.py`、e2e `test_autorun_{decisions,security,state_matrix}_e2e.py`。実態: **implemented**。

### System04 CLI / API（/cli）
- entry `/cli`（pages.py:160-179）、template `templates/cli.html`（130 行）、CSS `css/cli-mode.css`、JS `static/js/cli-mode.js`。**共通 topbar を使わない**独自ヘッダ `sysselect-topbar`（cli.html:14-23、戻るリンクのみ。アカウント・テナント表示無し）。
- 案内のみで実行しない（:31）。コマンドビルダー（select + 入力 -> コピー可能な文字列）。primary action は「コピー」（成功/失敗の文言あり、cli-mode.js:55-60）。REST API の案内節は cli.html に無い（API はカードのチップ（system-select.html:161）だけ）。
- ドメイン候補は出力先から生成（`<datalist>`、cli.html:67-69）。0 件時の案内は無い。
- **番号の誤り（全数）**: cli.html:27 kicker「System 03」（正: System 04）、:53「02 AutoRun」（正: 03）、:93 表の GUI 対応「02 AutoRun」（正: 03）、pages.py:162 docstring「System 03」、tests/test_cli_mode.py:1「System 03」。:52「01 ドキュメント作成」は合うが他の選択肢に番号が無く不揃い。正の対応は system-select.html:78,98,119,139,157（01・01·app・02・03 AutoRun・04 CLI/API）。
- 内容の欠落: `src/cli.py` には `ci gate`（:843-856）・`review`（:825）等があるが、案内表（cli.html:92-98）に CI 合否判定（`ci gate`）が無い。CI 組み込みを売りにする（system-select.html:159）のに主用途が載らない。
- responsive: `.cli-table` は 4 列（cli.html:90）で横スクロールのラッパー無し、cli-mode.css に `@media` 0 件。`.cli-stage` は max-width 1000px。PC 専用方針のため軽微。
- tests: `test_cli_mode.py`・`test_main_cli.py`（CLI 本体）。`/cli` 画面（テンプレート・番号）を検証するテストは未確認。実態: **implemented**（案内ページ）。

## 採点表

| System | 1 IA | 2 GP | 3 状態 | 4 Truth | 5 Perm | 6 A11y | 7 Resp | 8 Visual | 9 Perf | 10 Maint | 平均 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| System01 | 3 | 3 | 3 | 3 | 3 | 3 | 2 | 3 | 3 | 3 | 2.9 |
| System01 app | 2 | 2 | 2 | 1 | 2 | 3 | 3 | 3 | 3 | 1 | 2.2 |
| System02 | 3 | 3 | 3 | 3 | 2 | 3 | 3 | 3 | 3 | 3 | 2.9 |
| System03 | 3 | 3 | 3 | 4 | 3 | 3 | 3 | 3 | 3 | 3 | 3.1 |
| System04 | 2 | 3 | 3 | 2 | 3 | 3 | 2 | 2 | 3 | 2 | 2.5 |

根拠（System ごと）:
- System01: IA=旧シェルと workspace シェルの二系統だが topbar 共通で REA は仕様タブ内。GP=URL -> REA 実行 -> 根拠までコードで通り curl で実データ確認。状態=loading/empty/provider/error/partial/busy を文言付きで実装（ws-reverse.js:47,323-325,177）。Truth=Evidence 6 値・未確認/未計測表示。Perm=admin 403、REA 実行は確認なしだが非破壊。A11y=tablist・dialog トラップ・aria-live（dashboard は aria-live 0 件）。Resp=REA タイル/表の狭幅は未検証。Maint=REA 専用テスト 7 本。
- System01 app: IA/GP=カードは明快だが APK・実行先の入力が効かず通しが成立しない。状態=模擬のため実失敗系なし（app_mock.py の固定 sleep）。Truth=1（誤認文言が複数、P0 参照）。Perm=未検証。Maint=1（テスト 0 件、死んだ入力）。
- System02: Perm=2（/test-automation が admin チェックを通らない、pages.py:137-140 対 :129）。Truth=3（観点に根拠・到達・位置未確認を表示、ただし「実行した」件数が並ばない）。他は workspace 共通の品質。
- System03: Truth=4（「GET で留まっただけ」「認証済み/未認証」を分離し、証明でない旨を明記）。状態=7 状態を網羅、専用テストあり。autorun.js 1290 行は大きく Maint は 3 止まり。
- System04: IA/Truth=2（System 番号・AutoRun 番号の誤り、`ci gate` 欠落）。Visual=2（共通 topbar・ユーザーメニューが無く他システムと見た目が分断）。Resp=2（表の横スクロール無し）。Maint=2（番号誤りが docstring・テストにも複製）。GP=3（コピーまでは通る）。
- 共通: 実描画・キーボード操作・狭幅表示は未検証。

## P0 候補

- B-P0-1 `templates/system-select.html:100,103`: 「エミュレータ・シミュレータで探索し、未到達 Activity も洗い出す」とチップ「未到達 Activity」が実装済みに読める。害=APK を渡せば実解析されると誤認（実体は固定 6 画面の模擬、app_mock.py:21-28,119）。直し=説明を「画面の流れの試作（解析は実行しません）」にし、チップを削除。
- B-P0-2 `templates/index.html:56`・`templates/partials/view-generate.html:31-51`: サイドバー説明「APK / .app から画面仕様書…を生成します」と、APK 選択・実行先（エミュレータ Pixel 8 / 実機 adb / iOS シミュレータ）が機能して見えるが値は送信されない。害=選んだファイル・実行先と無関係な結果を「解析結果」と信じる。直し=入力を無効化し、/doc-app 画面に「サンプル（SampleShop）を再生します」の常時表示。
- B-P0-3 `web/services/app_mock.py:87-90`: 実行ログに「対象アプリ: …（エミュレータ）」「アプリをインストールしています…」「起動して初期画面を取得しました」を流す。害=実機・エミュレータ操作が行われたと誤認し、固定の成果物を実アプリの仕様書と信じる。直し=ログを「サンプルデータを再生中（実アプリは解析していません）」に変え、レポート先頭にモック帯を付ける。
- B-P0-4 `templates/partials/view-generate.html:35,42`: 見出し「解析対象アプリ」に対し選択肢は SampleShop の 1 択。害=自分のアプリを選べたと誤認。直し=見出しを「デモ用サンプルアプリ」、選択肢を「サンプル（SampleShop・デモ）」に。
- B-P0-5 `templates/cli.html:27,53,93`（+ `web/routes/pages.py:162`、`tests/test_cli_mode.py:1`）: kicker「System 03」と「02 AutoRun」が `/systems`（system-select.html:139,157）と食い違う。害=System 番号・AutoRun 番号を取り違えて案内。直し=kicker を「System 04」、AutoRun を「03」、選択肢の番号は全項目揃えるか外す。docstring・テスト冒頭も同修正。
- B-P0-6 `web/routes/pages.py:137-140`: `/test-automation` は `_may_use_testlab()` を呼ばない（`/sites/<d>/*` は :129 で 403）。害=認証オン時に非 admin が System02 の画面骨格に入れ、中の API 操作で初めて拒否され権限の挙動が不揃い（認証オンでの実挙動は未検証）。直し=`test_automation()` 冒頭で `_may_use_testlab()` を確認し 403。
- 補足（P0 ではない）: cli.html の案内表に `ci gate` が無い（:92-98）、CLI 表の横スクロール無し（cli.html:90）、System02 の REA タイルに「実行済み 0 件」の明示が無い（ws-rea-viewpoints.js:54-57）、dashboard の `aria-live` 無し（view-dashboard.html:57 の「読み込み中...」）。
