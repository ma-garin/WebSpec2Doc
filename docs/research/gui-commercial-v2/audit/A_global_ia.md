# A. Global IA / Shell 監査（origin/main 0efbd20・監査サーバ 8768）

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
