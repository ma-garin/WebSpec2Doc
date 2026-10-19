# GUI 現状監査（2026-10-20・origin/main 0efbd20）

コード読みと curl（監査用サーバ 8768）による静的監査。実ブラウザでの操作確認は本文中で「未検証」と明記した箇所を除き行っていない。
各節は並列監査（A〜E）の原文。採点の集約は UI_MATURITY_MATRIX.md。


---

## A. Global IA / Shell 監査（origin/main 0efbd20・監査サーバ 8768）

根拠は file:line か curl。コードから読んだだけで実行していないものは「未検証」と書く。

## 事実

### 1. /systems（System 一覧）

- ルートは `web/routes/pages.py:143-146` が `system-select.html` を返すだけ。データは渡さない。
- **正本は無い。** カードは `templates/system-select.html` に手書き（行 50-270）。数・番号・名称・権限は次の 4 箇所に別々に書かれている。
  - カード本体: system-select.html
  - サイドバーの切替名（8 テンプレートに直書き）
  - `static/js/system-scope.js` の SYSTEM_LABEL
  - 各テンプレートの kicker・docstring
- カード数は 11 枚（指揮・01・01 app・02・03・04・05・06・07・08・09）。
- 一般利用者に出るのは 9 枚。02 と 05 は管理者のみ（system-select.html:109、170）。認証オフ時は全部出る。
- 状態バッジ: 新規（指揮・02・05・06・07・08・09）／モック（01 app）／独立システム（03）／画面なし（04）。01 だけバッジが無い。
- 権限は `auth_user.role == 'admin'` のカード単位。画面側の 403 判定は `_may_use_testlab`（pages.py:122）。
- 古い数・番号の食い違い（全数 grep）:
  - system-select.html:43 は「8 つは独立したシステム」。実際は 01〜09 の番号つきが 10 枚、指揮を含めて 11 枚。
  - system-select.html:61 は「6 つのシステムを 1 本につなぐ」。同ファイル :48 のコメントは「5 つ」。
  - `templates/cli.html:27` の kicker は「System 03」。カードは System 04（:157）で、03 は AutoRun（:139）。
  - `web/routes/pages.py:162` の docstring も「System 03」。
- 接続している System の数を `/api` 等から導いた形跡は無い（未検証）。

### 2. 共通シェルの使用状況（本体は `templates/partials/topbar.html`）

| 入口 | topbar | sidebar | 切替 |
|---|---|---|---|
| /dashboard /doc-app /auto-run | 使う | 共通(nav.html) | 共通(index.html:40) |
| /test-automation | 使う | 独自(workspace.html:33) | 無し(brand のみ) |
| /sites/d/spec・/team | 使う | 独自(同上) | 無し |
| /healing 系(3 本) | 使う | 共通(healing-sidebar) | 共通 |
| /orchestration | 使う | 共通(conductor-sidebar) | 共通 |
| orchestration_b / _d | 使う | 無し | 無し(crumb リンク) |
| /docverify | 使う | 独自 aside | 直書き(doc_verify.html:27) |
| /batch-test | 使う | 独自 aside | 直書き(batch_test.html:27) |
| /backend-test | 使う | 独自 aside | 直書き(backend_test.html:26) |
| /impact | 使う | 独自 aside | 直書き(impact_analysis.html:27) |
| /cli | 無し | 無し | 戻るリンク(cli.html:21) |

- topbar の中身: パンくず（:9）、タイトル、テナントチップ（認証時のみ・/auth/tenant へ）、アカウントメニュー（個人設定・ユーザー管理・テナント管理・ユーザーガイド・フィードバック）。
- ヘルプ専用の入口は無く、アカウントメニュー内の「ユーザーガイド」だけ。
- パンくず先頭の「WebSpec2Doc」はリンクではない（topbar.html:9）。`core.js:171` の setHeader は先頭を `<a>` にする。画面で挙動が違う。
- 認証オフではテナントチップが出ない（auth_user が必要）。実機は未検証。

### 3. URL・戻る・リロード（コードから判断。実機は未検証）

- index.html 系: パスに載る（core.js:228-231 pushState）。リロードで復元（core.js:160）。設定は /settings/<tab>（settings.js:21）。AutoRun 内の細かい状態は URL に載らない。
- workspace（test-automation・sites）: `#/tests/<id>` 等＋パス。**replaceState のみ**（state.js:236-239）。戻るでは遷移前の画面へ行かず、サイト外へ出る。
- healing: ページ単位は /healing・/healing/settings・/healing/reports/<id>。ただし healing.html 内の run/projects/history は変数だけ（healing.js:384）。リロードで初期表示に戻る。
- docverify: `#view` を pushState し hashchange/popstate で復元（docverify-core.js:129-166）。良好。
- batch-test: `?job=&#step` を replaceState（batch-test.js:76、213）。リロード復元は可。戻るで工程は戻れない。
- backend-test: `#job=…` を replaceState（backend-test.js:300）。同上。
- impact: `?view&sys&cr&tab` を pushState＋popstate（impact/app.js:109-121、259）。良好。
- orchestration: `?site=` を replaceState（orchestration.js:138-145）。サイト以外の状態は URL に無い。
- cli・/systems: 状態なし。

### 4. 番号・名称の不一致（/systems のカード名との比較）

| 入口 | カード名 | topbar の画面名 | 差 |
|---|---|---|---|
| /dashboard | ドキュメント作成 | QAドキュメント生成 | 名称違い |
| /doc-app | …(app) | 同上(JS で上書き) | 未検証 |
| /test-automation | テスト自動化 | テスト自動化 | 一致 |
| /auto-run | AutoRun | QAドキュメント生成 | 初期 HTML が別物 |
| /cli | CLI / API | CLI モード（画面なし） | 名称・番号違い |
| /healing | オートヒーリング | 報告書 | 一致(h1 は画面名) |
| /docverify | ドキュメント検証 | ホーム | 一致 |
| /batch-test | バッチ・スクリプトのテスト | 取り込み | 切替名は「バッチのテスト」 |
| /backend-test | バッチ・バックエンドのテスト | パンくず「ホーム」 | 切替名は「バックエンド」 |
| /impact | 影響度分析 | 対象システム一覧 | 一致 |

- ブラウザのタブ名（title）が同一の画面: /dashboard・/test-automation・/doc-app・/auto-run はすべて「WebSpec2Doc」（curl 結果）。
- System 番号を画面に出すのは /systems のカードと cli.html の kicker だけ。サイドバー・パンくず・タイトルには出ない。
- /doc-app と /auto-run の「QAドキュメント生成」は、JS が書き換えるまでの初期 HTML（core.js:175）。JS 前後の見え方は未検証。

### 5. workspace.html の viewport と幅

- `workspace.html:5` は `width=1440` の固定。他の全テンプレートは `device-width`。
- 3 カラム（`.app` の grid）は 3 回上書きされる。
  - ta2.css:18 `56px 280px 1fr`
  - ws.css:221 `84px 280px 1fr`
  - ws.css:295 `var(--sidebar-w) 280px minmax(0,1fr)`。--sidebar-w は app.css:33 で 256px。
- 内側も px 固定: ta2.css:85 `.ed-b 400px 1fr`、ws.css:53 `1fr 380px`、ws.css:83 `1fr 400px`、ws.css:124 `1fr 300px`。
- 実効の最小幅は 256+280=536px の固定列＋右カラム 400px 前後で、約 940px 以上が必要。
- ta2.css:14 は `html,body{overflow:hidden}`。ta2.css と ws.css に @media は無い。
- 狭い窓でどう見えるかは未検証（実機を開いていない）。

## P0 候補

- **A-P0-1** 何が: /systems の説明が「8 つ」、実カードは 11 枚（番号つき 10）。どこで: system-select.html:43。害: 最初の画面で数が合わず信頼を損なう。直し: 数を書かず、一覧データから描く。
- **A-P0-2** 何が: 指揮カードが「6 つのシステム」、同ファイルのコメントは「5 つ」。どこで: system-select.html:61。害: 何を束ねるのか分からない。直し: 束ねる System を一覧で示し、文言から数を消す。
- **A-P0-3** 何が: CLI 画面の kicker が System 03（カードは 04、03 は AutoRun）。どこで: cli.html:27、pages.py:162。害: 番号で話すと取り違える。直し: 番号を正本から出す。
- **A-P0-4** 何が: /test-automation と /sites・/team に「システム切替」が無い。どこで: workspace.html:33-40。害: 他 System へ行くのにロゴを押す必要があり、/sites では /systems に行けない。直し: 共通の切替部品を入れる。
- **A-P0-5** 何が: /backend-test のパンくずが「ホーム」で System 名が無い。切替名も「バックエンド」「バッチのテスト」とカードと違う。どこで: backend_test.html:47、:28、batch_test.html:27。害: 今どの System か読めない。直し: 切替名・パンくず先頭をカード名に揃える。
- **A-P0-6** 何が: タブ名が 4 画面で「WebSpec2Doc」のまま。どこで: workspace.html:7、index.html。害: 複数タブを開くと区別できない。直し: 「画面名 - System 名 - WebSpec2Doc」に統一。
- **A-P0-7** 何が: workspace が `width=1440` 固定で `overflow:hidden`、@media も無い。どこで: workspace.html:5、ta2.css:14。害: 狭い窓で右側が切れて操作できない恐れ（未検証）。直し: 最小幅の実測後、列を minmax と折り返しで可変にする。
- **A-P0-8** 何が: ワークスペース・healing・batch・backend は replaceState か変数のみ。どこで: state.js:236、healing.js:384、batch-test.js:76、backend-test.js:300。害: 戻るボタンで前の画面に戻れず、healing はリロードで初期表示に戻る。直し: 画面切替は pushState、状態は URL に載せる。

## 共通化の候補

- 「システム切替」を partial 1 つにする。現在は 8 テンプレートに直書きで名前が揃わない。
- System の一覧（番号・名称・入口・権限・状態）を 1 か所の定義にし、/systems・切替・パンくず・CLI kicker がそこから描く。
- パンくずと title を `topbar_system` と `topbar_page` の 2 変数で渡す部品にして、先頭の System 名と戻りリンクを共通にする。
- 画面状態の URL 化（pushState・popstate・hash/query）を共通の小さなヘルパーにする。impact と docverify の方式が既に良好。
- viewport と最小幅の方針を 1 つに決め、workspace だけの固定幅を外す。

---

## Agent B 監査: System01 / System01 app / System02 / System03 / System04

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

---

## C 監査: System05〜09（オートヒーリング / ドキュメント検証 / バッチ・スクリプト / バッチ・バックエンド / 影響度分析）

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

---

## Agent D 監査: /orchestration（指揮）

対象: worktree wt-gui（origin/main 0efbd20）。根拠は file:line か curl（監査サーバ 8768）。ブラウザ未使用のため見た目・実機の挙動は「未検証」。

## 事実

### 入口と 3 画面の関係
- `/orchestration` は `orchestration.html`（5 工程ステッパー + 1 枚のカード）を返す。`web/routes/orchestration.py:189-199`
- `/orchestration/<variant>` で旧案 `b`（一覧）と `d`（サイト別の記録）が残る。`orchestration.py:203-209`。docstring は「開発・比較用」。
- 正本は `/orchestration`（`orchestration.html` + `orchestration.js` 998 行 + `/api/orchestration/workflow`）。ただし `d` は左メニュー「実行履歴」の遷移先（`partials/conductor-sidebar.html`、href=/orchestration/d）で、事実上の本番画面。`b` はどこからもリンク無し（未検証: 他テンプレのリンク全数は grep していない）。
- 3 画面は別々の殻。新画面は conductor-sidebar + topbar、`d` は topbar のみ（サイドバー無し、`orchestration_d.html:21-24`）、`b` は独自 `cb-shell`。ナビが画面ごとに変わる。
- `ASSET_VERSION` が不揃い。`/orchestration` と `/d` は `?v=1`、`/b` は `?v=1792447684`（curl）。`b` は `_ver` を set していない（`orchestration_b.html` 冒頭に `{% set %}` 無し）。

### 現行 5 工程（`workflow_view.py:37-43`）
- 解析 / テスト設計 / 実行 / 分析して直す / 判断。1 サイトずつ、現在の 1 工程だけをカードに出す。
- データ源: 実データ。conductor の run 記録（`run_store`）、healing の project・報告書、`autorun_bridge.load_failures`（失敗件数）。見本（mock）ではない。
- `current.text_source` で measured / user / llm / unverified を区別（`workflow_view.py:60-72`）。出所表示の仕組みはある。
- 応答キー: `domain, sites[{domain,label}], repos, rounds, steps[{key,label,no,state,summary}], current{key,state,headline,text,text_source,elapsed_sec,error,action}, run_id, updated_at`（curl）。
- 操作 API: `POST /api/orchestration/workflow/actions` は `require_admin`（`orchestration.py:421-426`）。閲覧 API は無認可で読める。
- 更新: 実行中のみ 5 秒ポーリング、タブ非表示で停止（`orchestration.js:958-972`）。

### 実測した不整合
- サイトが 2 件（`/api/healing/sites`: demo.realworld.show, localhost:8792）あるのに、`/api/orchestration/workflow` は `key=setup`「まだサイトが登録されていません」を返す。healing の project が 0 件（`/api/healing/projects` が空）のとき観測済みサイトを無視する。ユーザーには「登録済みなのに未登録」と見える。
- `/orchestration/d` の JS は起動時に sites / projects / runs(400) / reports(200) の 4 本を取る（`orchestration-d.js:27-39`）。集計はすべてクライアント側で、他画面から再利用できない。
- 存在しない API: `/api/sites` `/api/dashboard` は 404、`/api/snapshot-diff-summary` `/api/autorun/status` も 404（パス違いの可能性。正しいパスは未特定）。

### shell・状態・a11y・responsive・deep-link
- shell: 新画面は `app-shell` + sidebar（7 項目: サイト/実行履歴/報告書/見張り/コードの場所/ガイド/設定）+ topbar。`skip-link` あり（`orchestration.html:19`）。
- 状態: 読込み中は「読み込み中…」固定文、失敗は `renderLoadError`（`orchestration.js:166-174`）で再試行ボタン無し（開き直し案内のみ）。empty は setup カード。partial（一部 API 失敗）の扱いは無い（1 API のため）。`d` は `role=alert` のバナー 1 枚（`orchestration_d.html:26`）。
- a11y: `aria-live="polite"` はカード 1 つ。JS 内の aria/role/focus は `orchestration.js` 1 箇所・`-d.js` 3 箇所・`-b.js` 4 箇所のみ。状態遷移時のフォーカス移動は無い（`.focus()` は textarea 1 箇所 `orchestration.js:849`）。ステッパーは `<ol aria-label>` だが `aria-current` は未確認。
- responsive: `orchestration.css` の `@media` は `prefers-reduced-motion` のみ（`orchestration.css:256`）。幅の分岐は無し。`-d.css` `-b.css` に `@media` 無し（grep 0 件）。親 CSS（app.css/ta2.css）の効果は未検証。
- deep-link: `?site=` を `replaceState` で更新（`orchestration.js:142-146`）。履歴に積まないため戻るボタンでサイト切替は戻れない。工程・run_id への deep link は無い。
- テスト: tests/ に orchestration / workflow を名に持つファイルは 0 件（`ls tests | grep`）。内容 grep では参照ファイル 0 件。JS は `window.__cw` で露出するが対応テストは見当たらない。

## 日常運用ホームとの差（表 1 個）

判定: ある / 部分 / 無し。

| 要素 | 判定 | 根拠 |
|---|---|---|
| 全サイト数 | 部分 | workflow.sites 配列 |
| 正常 / 失敗 / 実行中 件数 | 無し | 集計 API 無し、d は 14 日帯のみ |
| 確認待ち・承認待ち件数 | 部分 | /api/healing/reports/count |
| 未確認・今日の変更件数 | 無し | 集計 API 無し |
| テスト・修正・報告 件数 | 無し | 件数集計の API 無し |
| 一覧の latest status | 部分 | d の run 状態をクライアント集計 |
| current stage | 部分 | workflow は 1 サイトのみ |
| last run | 部分 | d が runs から導出 |
| evidence health | 無し | 実測/AI/未検証は 1 文単位のみ |
| pending human action | 部分 | run.human_action |
| latest change / failure | 無し | 失敗件数は選択サイトのみ |
| 各 System 結果 deep link | 部分 | 報告書リンクのみ |

補足:
- 「部分」は 1 サイト単位、または画面ごとに別実装で、全サイト横断の一覧が 1 回の呼び出しで取れない。
- 現行入口は「1 サイトを 5 工程で進める作業画面」で、日常運用ホームではない。

## 使える既存 API

- `GET /api/healing/sites`: `domain, title, screens, observed, updated_at`（全サイトの最小一覧。状態は無い）
- `GET /api/healing/projects`: 保守下のサイト（`monitor_enabled` 等。件数 0 のときが多い）
- `GET /api/orchestration/runs?limit=N`: ConductorRun 全体。`run_id, domain, goal, status, step_index, steps[], human_action, error, started_at, finished_at`（last run・実行中・失敗・人の判断待ちの源）
- `GET /api/healing/reports?status=awaiting&limit=N` と `/count`: 承認待ち報告書と件数
- `GET /api/healing/runs`: 修正実行の一覧
- `GET /api/history/runs`: `stats{total,complete,failed,cancelled}` を既に返す（テスト実行の件数源。ドメイン別かは未検証）
- `GET /api/runs/<domain>`: `current_run_id, runs, total`（サイト別実行）
- `GET /api/orchestration/workflow?site=`: 1 サイトの現在工程・次の操作
- `GET /api/orchestration/goals`: 目標（daily/onboard/continue）と工程名
- `GET /api/snapshot-diff`（pages 系、`/api/snapshot-diff-summary` は 404）: 今日の変更の源候補。返却項目は未検証

### 新しい集計 API の最小形（提案）
`GET /api/home/summary` 1 本。サーバ側で上の API 群を束ね、次を返す。
- `counts`: `sites, ok, running, failed, awaiting_confirm, awaiting_approval, unverified, changes_today, tests, fixes, reports`
- `sites[]`: `domain, label, status, stage, last_run{id,at,status}, evidence{measured,llm,unverified}, human_action, latest_change{at,text,href}, latest_failure{at,text,href}, links{docs,tests,autorun,healing,reports}`
- `partial_errors[]`: 取得に失敗した源の名前（画面側で部分表示にする）
既存関数 `workflow_view._list_sites` `_latest_run` `_failure_count` `_awaiting_reports` を流用できる（`workflow_view.py:130,181,347,361`）。

## 採点（0〜4）

| 軸 | 点 | 根拠 |
|---|---|---|
| 1 IA | 1 | 3 画面が別殻でサイドバー有無が違い、ホームが無い |
| 2 Golden Path | 2 | 5 工程の誘導は明快。ただし未登録誤判定と全体俯瞰が無い |
| 3 Loading・Empty・Error・Recovery | 1 | 読込み固定文、失敗に再試行ボタン無し、partial 無し |
| 4 Product Truth・Evidence | 3 | 実データで出所区分あり。ただし件数の集計が無い |
| 5 Permission・Safety | 3 | 操作系は require_admin、audit 記録あり。閲覧は無認可（未検証: ロール別の見え方） |
| 6 Accessibility | 1 | live 領域 1 つ、フォーカス管理無し、aria 記述が少ない |
| 7 Responsive・Browser Navigation | 1 | 幅の分岐無し、replaceState で戻れない |
| 8 Visual Consistency | 2 | 画面ごとに CSS が別（3 本）。見た目は未検証 |
| 9 Performance・Feedback | 2 | workflow は 32ms（curl）。d は 4 本取得 + 400 件を全部クライアント集計 |
| 10 Maintainability・Testability | 1 | JS 3 本 2,300 行超、旧案 b 残置、専用テスト 0 件 |

## P0 候補

- D-P0-1: 日常運用ホームを新設する。`/api/home/summary`（上記）と、件数 8 項目 + サイト一覧 + 各 System への deep link を 1 画面にする。`/orchestration` の入口を置換し、現行 5 工程は `?site=` の詳細へ下げる。
- D-P0-2: 観測済みサイトがあるのに「まだサイトが登録されていません」と出る誤判定を直す（`workflow_view.py:462` 周辺。project 0 件のとき `sites` を見る）。
- D-P0-3: 3 画面の殻を 1 つに揃える（`d` にサイドバー追加、`b` は削除または廃止）。ASSET_VERSION も統一する。
- D-P0-4: 状態表示を揃える。loading のスケルトン、error の再試行ボタン、一部取得失敗の partial バナー、empty の次の行動。
- D-P0-5: a11y と戻る操作。状態更新時の `aria-live` と見出しへのフォーカス移動、`?site=` を `pushState` にして戻るで復元、幅の分岐（狭幅）を追加する。
- D-P0-6: `/orchestration` と workflow API のテストを新設する（setup 誤判定・admin 以外の操作拒否・日次ホームの件数）。

---

## Agent E: Design System / CSS 監査

対象: origin/main 0efbd20（worktree wt-gui）。静的 grep/wc のみ。実画面は未確認。

## 事実（数値つき）

### 1. トークンが 2 系統ある（最大の構造欠陥）
- 正本 `static/tokens.css`（87 行・変数 68）: `--color-*`（primary/critical/high/medium/low/info とその -bg/-border）・`--text-xs..2xl`・`--space-1..12`・`--radius-*`・`--shadow-*`・`--motion-*`・`--font-main/mono`
- 別系統 `static/css/ta2.css:2-12` の `:root`: `--bg --sf --line --tx --ac --ok --ng --wa --sans --mono`。primary は tokens `#1976D2` に対し ta2 `#2563EB`。フォントは tokens `Noto Sans JP` 先頭に対し ta2 `Inter` 先頭
- さらに `static/app.css` に別名 31 本（`--text-muted --border --primary --surface --critical --info-bg --radius` 等）。参照数は `--text-muted` 327・`--border` 276・`--primary` 143
- 参照量: `var(--color-*)` 1177 回 / ta2 短縮名 `var(--bg|--tx|--ac|--ok|--ng|--wa…)` 1313 回。ワークスペース・システム選択・healing・impact・orchestration・docverify は ta2 系、index.html（旧ビュー）・components.css は `--color-*` 系
- tokens.css に意味色 success / warning / error が無い。critical/high/medium/low/info を「重大度」と「状態」で兼用している
- ダークテーマ定義 0 件（`prefers-color-scheme` / `data-theme` が CSS 全体で 0。tokens.css のコメントは「light/dark 両テーマ」と書くが :root 1 つのみ）
- 未定義変数の参照 28 種: `--success --warn --danger --er-bg --wn-bg --high-bg --color-success --color-text-tertiary --primary-border --surface-2 --surface-alt --hl-*` 等（viewpoints.css・components.css・healing*.css・app-report.css・view-settings.html）。フォールバック有無は未確認

### 2. 生の色（#hex）。CSS 全体で hex 1135 個、var(--) 参照 5275 回
| 順 | ファイル | hex+rgb | var 参照 |
|---|---|---|---|
| 1 | css/healing.css | 170 | 236 |
| 2 | css/healing-reports.css | 112 | 106 |
| 3 | css/ta2.css | 97 | 289 |
| 4 | css/orchestration.css | 74 | 70 |
| 5 | css/docverify-tier-1.css | 72 | 52 |
| 6 | css/docverify-tier-2.css | 72 | 53 |
| 7 | css/system-select.css | 71 | 32 |
| 8 | app-report.css | 55 | 421 |
| 9 | css/impact.css | 54 | 102 |
| 10 | css/components.css | 51 | 824 |
- ta2.css の 97 は `:root` 定義分を含む。他は意味色の直書き（`#FEE4E2 #B42318 #FDA29B` 等 ta2 系の値を hl-badge が再記述）
- templates 内 `<style>` ブロックは 6 ファイル（traceability / healing_report_print / system-select / orchestration_b / view-settings / view-usage）。生色 hex は healing_report_print 13・system-select 9

### 3. inline style・typography・responsive
- templates の `style="` 278 件: view-settings 81 / view-generate 64 / workspace 40 / view-auto-run 19 / modal-autorun-login 14 / view-user-guide 8 / view-qa-quality 7 / view-viewpoints 5 / index 5 / modal-user-admin 4。JS 内 `style="`/cssText 行 169（ws-spec 14・panels 14・view-report 13・results 12・view-overview 10・docverify-review 10）
- font-size: px 直書き 1199 / `var(--text-*)` 357 / rem・em 11。px の種類 29。分布は 12px:286 11px:234 13px:189 12.5px:134 11.5px:78 14px:46 10.5px:46 10px:38 15px:35。トークン段（11/13/14/16/18/22/28）に乗らない px が 675 件。10px 以下 47 件（10px:38・9px:8・8px:1）
- viewport meta: 通常ページは設定済み。欠落は auth/tenant.html（ほか docverify/_*.html 9 本は partial の可能性・未検証）
- `html,body{overflow:hidden}`: ta2.css:14・orchestration-b.css:9・orchestration-d.css:5 と app.css:42 `body.app-page`。system-select.css:181 が「8 枚が 1440x900 に収まらず切れる」ため個別に解除（同種の見切れ再発点）
- `@media` 58 件のうち reduced-motion 10・幅指定 48。幅の閾値は 640/760/820/860/900/1020/1100/1200/1280 と散在（統一ブレークポイント無し）。`min-width:Npx` 直書きは app-report 10・components 8・app 7・viewpoints 5・docverify 5。`width:300px 以上` 固定は ta2 3・docverify-tier-2 3 ほか
- overflow:hidden は components 23・ta2 18・healing 17・app-report 17・app 16（見切れ温床。check_clipping.py の対象）

## 部品の重複実装（同じ役割の別実装数）
| 役割 | 実装数 | 代表（file:クラス） |
|---|---|---|
| button | 29 接頭辞 / 58 クラス | ta2 `.btn`（唯一の素の .btn）。ほか arep-btn・dv-btn・hl-btn・rv-btn・cd-btn・pager-btn・btn-primary(app.css, app-components.css 重複) |
| badge/chip/pill | 34 接頭辞 / 78 クラス / 24 ファイル | `.badge`(components) `.pill`(ta2) `.hl-badge`(healing と healing-reports で二重定義) `.rv-badge` `.dv-chip` `.vp-chip` `.arv-badge` `.asr-badge` `.im-rea-b` |
| modal/dialog | 10 実装 | `.cmp-modal` `.autorun-modal` `.dv-modal` `.bs-modal` `.im-modal` `.cd-dialog` `.input-dialog-card` ほか。ta2 系に共通 modal 無し。role="dialog"/aria-modal は templates+js で 21 |
| drawer | 共通 0 | rv 側 2 クラスのみ。drawer の正本無し |
| toast/banner | toast 5 実装 + banner 5 | `.toast`(app-components) `.toast`(ta2.css:242, 406 の二重) `.bt-toast` `.bs-toast` `.dv-toast` `.hl-toast`。banner: `dv- bt- bs- hl- cd-` |
| table | 44 接頭辞 | `.dv-table` `.arep-table` `.hl-*` `.tds-table` `.account-table` `.uadm-table` `.cli-table` `.mbt-table` `.rh-table` `.traceability-table` ほか |
| tabs/seg | 9 実装 | `.result-tab`(app.css と report-v2.css 二重) `.set-tab` `.vp-tab` `.bs-tabs` `.dv-tabs` `.rv-tab` ta2 `.seg` |
| empty | 19 実装 | `.empty` `.dashboard-empty` `.qa-empty-state` `.arep-empty` `.bt-empty` `.hl-empty`(healing と healing-reports) `.dv-empty` `.rv-empty` `.ui-empty`(report-v2) ws `.list-empty` ほか |
| loading | 7 実装 | `.spinner`(app.css) `.arep-loading` `.dv-loading` `.rr-loading` `.rv-loading` `.ui-skeleton` `.discover-loading` |
| KPI/tile | 11 実装 | `.kpi`(ta2) `.stat-card`(app.css と components.css 二重) `.arep-tile` `.rv-tile` `.dvr-kpi` `.dv3-stat` `.kpi-tile` `.runs-stat-card` `.rep-kpi` |
- `ui-empty / ui-skeleton`（report-v2.css:87,114）が唯一「共通部品」を意図した命名だが、ワークスペースの ta2 系ページには読み込まれていない（workspace.html は tokens/app/user-menu/ta2/ws/testcase-grid/reverse-analysis のみ）

## 状態語彙（UI 文言の出現数: templates + static/js）
- 完了 99 / 成功 50 / 合格 22 / 済み 208（全て「うまくいった」の同義）
- 失敗 297 / エラー 79 / 不合格 11 / NG 27 / FAIL 11。失敗文は `失敗しました` 121・`できませんでした` 127・`取得できません` 47・`に失敗` 124 が混在
- 実行中 76 / 読み込み中 44 / 取得中 3 / 生成中 5 / 解析中 9 / 処理中 2 / 準備中 2 / 英語 Loading 28
- 未確認 41 / 未検証 23 / 未実行 29 / 要確認 48 / 確認待ち 11 / 承認待ち 25 / 要対応 8（要確認=人が見る、確認待ち/承認待ち=人の入力待ちが混在）
- キャンセル 24 / 中止 37 / 中断 23（同義の 3 語）。空状態: 「ありません」255・「まだありません」30・「0 件」30 と「0件」17（半角スペース揺れ）・「なし」121・未設定 39・未登録 4
- 英語: NG 27・OK 13・PASS 14・FAIL 11 が日本語 UI に混在

## Evidence 状態の表示実装（ファイルとラベル・色の差）
| 実装 file | ラベル | 色 |
|---|---|---|
| js/ta2/ws-reverse.js:16 + css/reverse-analysis.css:65-70 | 実測/静的/推論/曖昧/未確認/利用不可 | 緑/青/黄(文字が #FBC02D)/橙/破線グレー/赤 |
| js/impact/rea.js:7 + css/impact.css:176-184 | 推論/曖昧/未確認 + 到達(実測) | 推論=青 #EFF8FF 直書き、曖昧=黄 ta2、到達 unreached/auth/failed=同一の黄 |
| js/autorun-static-routes.js:70-74 + css/autorun-static-routes.css:34-36 | 実測(認証済み/未認証)・未到達・要認証・曖昧・失敗 | 実測=緑、未到達と失敗=赤、要認証と曖昧=黄 |
| js/view-design.js:400 + components.css:1980 | 実測 1.0 / カタログ | #d7f0dd #fdeecd 直書き |
| js/healing-reports.js:417, js/orchestration.js:31 | 実測/入力/AIの提案/前提/未確認（出所 5 値） | 別体系（出所であって状態ではない。同名 SOURCE_LABELS が 2 ファイルに重複） |
- 差: 「曖昧」は reverse=橙 / impact=黄 / static-routes=黄で 3 色。「推論」は reverse=黄 / impact=青。「未確認」は reverse=破線グレー / impact=グレー実線 / healing=出所ラベル。「認証済み」は autorun-static-routes のみ（reverse・impact に無い）
- `rv-oc-success` は info(青)、`rv-st-observed` は low(緑)。同じ画面内で「成功」の色が 2 つ
- `rv-st-inferred` は色 `--color-medium`(#FBC02D) を文字色に使用。淡黄地で WCAG 1.4.3（4.5:1）を満たさない見込み（未計測）

## 共通 contract に昇格すべき部品（優先順・正本・file）
1. 意味色トークン: `static/tokens.css` に `--color-success/-warning/-error/-info/-neutral`(+ -bg/-border/-text) を追加し、ta2.css の `--ok/--ng/--wa/--ac` と app.css の別名 31 本を tokens への alias 化（正本=tokens.css。値は ta2 の AA 検証済み `-tx` 系を採用）。ダーク定義も同時に
2. StatusBadge(1 部品・語彙固定 enum): 正本=ta2.css `.pill`+`.fchip` を拡張。置換対象は `.hl-badge .rv-badge .asr-badge .im-rea-b .badge .arv-badge .mbt-badge`
3. EvidenceBadge: 正本=reverse-analysis `rv-st-*` の 6 状態 + 認証済みを足す。js/ta2/ws-reverse.js `STATE_LABEL` を共通 JS に移し impact/rea.js・autorun-static-routes.js が参照
4. Button: 正本=ta2.css `.btn`（唯一の素の .btn）。`.arep-btn .dv-btn .hl-btn .rv-btn .cd-btn` を variant（primary/ghost/danger）に寄せる
5. Modal/Dialog + Drawer: 正本は新設（focus trap・Esc・role="dialog" を持つもの）。10 実装を置換。現状は ta2 系に正本無し
6. Toast/Banner: 正本=ta2.css:242 `.toast`（二重定義を 1 本に）。`.bt- .bs- .dv- .hl-` を置換
7. EmptyState/Loading/ErrorState: 正本=report-v2.css `.ui-empty/.ui-skeleton` を ta2 系に読み込む形へ昇格（文言テンプレ: 何が無い・次の行動 1 行）
8. KPI tile: 正本=ta2.css `.kpi`。9 実装を寄せる
9. Tabs/Seg: 正本=ta2.css `.seg`
10. Table: 共通 `.tbl`（sticky head・狭幅時の data-l カード化は reverse-analysis と autorun-static-routes にあり、これを正本の下敷きに）

## 意味色・状態語彙の統一案（表 1 個）
| 意味 | 語彙(固定) | 色トークン | 同義で廃止 |
|---|---|---|---|
| 成功 | 完了 | success | 成功・済み・合格・OK |
| 失敗 | 失敗 | error | エラー・NG・不合格 |
| 実行中 | 実行中 | primary | 処理中・取得中・生成中 |
| 待機 | 確認待ち | warning | 承認待ち・要確認の一部 |
| 要判断 | 要確認 | warning | 要対応 |
| 未実施 | 未実行 | neutral | 未着手 |
| 根拠なし | 未確認 | neutral 破線 | 未検証(結果に限る) |
| 中断 | 中止 | neutral | キャンセル・中断 |
- Evidence 7 状態: 実測=success / 静的=info / 推論=primary 薄 / 曖昧=warning / 未確認=neutral 破線 / 利用不可=error / 認証済み=success 内の「認証済み」修飾（別バッジでなく併記）
- 失敗文は「〇〇に失敗しました。次の行動」1 型、空状態は「〇〇はまだありません」1 型、件数は「0 件」（半角スペース）に統一

## P0 候補
- E-P0-1 トークン 2 系統の統合: `--color-*` と ta2 短縮名が併存（primary #1976D2 と #2563EB、フォント Noto/Inter）。同一アプリ内で画面ごとに青とフォントが違う。tokens.css に集約し alias 化。
- E-P0-2 意味色（success/warning/error）が正本に無く、未定義変数 28 種を参照。参照先が無い箇所は色が付かず成功/失敗が見えない恐れ（フォールバック有無は未確認）。
- E-P0-3 Evidence/Status バッジが 5 実装で色・ラベルが不一致（曖昧が橙/黄、成功が青/緑）。誤読リスクのため共通 EvidenceBadge/StatusBadge を先に作る。
- E-P0-4 `rv-st-inferred` の黄文字（#FBC02D）が淡黄地でコントラスト不足の見込み。実測して `-tx` 系へ。
- E-P0-5 Modal/Dialog が 10 実装で共通 contract 無し（focus trap・Esc の統一が保証できない）。共通 Modal を新設。
- E-P0-6 `html,body{overflow:hidden}` 方式で system-select が切れた実績（system-select.css:181）。ページ別解除でなく共通レイアウト contract に「縦スクロール領域」を定義。
- E-P1 参考: 10px 以下 47 件・tokens 外 px 675 件・inline style 278+169 件・dark 定義 0・viewport 欠落 1 本（auth/tenant.html）。
