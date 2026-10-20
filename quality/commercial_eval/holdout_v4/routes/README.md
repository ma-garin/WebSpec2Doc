最終判定用 holdout。改善に使っていない。製品コードを参照していない。

# holdout_v4 / routes: 配布済み JS からの API 呼び出し先抽出

## 目的

配布済みの（非 minify）JavaScript から「このサイトの API として実際に呼ばれうる呼び出し先（method + path）」を
静的に取り出す機能の、最終判定用データ。題材は「病院の外来受付」。

## 規模

- site/index.html と site/assets/*.js の 6 ファイル（config / http / patients / reception / billing / app）。外部 CDN なし。
- expected.json は 46 件。うち `exclude_from_metrics: true` が 2 件（数えない）。
- 集計対象 44 件 = should_detect=true 30 件 + false 14 件。

## カテゴリ別件数（集計対象 44 件）

| 区分 | 件数 | 内容 |
|---|---|---|
| true: ベース URL 定数（別ファイル定義）| 29 | config.js の API_BASE / BILLING_BASE 等を他ファイルから参照（T29 以外はほぼ全件）|
| true: テンプレートリテラル | 7 | T05, T07, T15, T16, T18, T24, T28。途中 / 末尾 param を含む |
| true: 多段の定数 | 7 | API_BASE <- RECEPTION_BASE <- QUEUE_BASE、LAB_ROOT <- LAB_ORDERS（T09, T10, T22 〜 T26）|
| true: ヘルパー経由（fetch）| 6 | アロー関数 req 1 段（T10）、2 段以上 apiPost / apiSend（T08, T11, T21）、3〜4 段 getJson / loadList（T12, T14）|
| true: options の method（直書き）| 9 | POST 3 / PUT 2 / PATCH 2 / DELETE 2（ヘルパー経由の 4 件は別）|
| true: method 省略 fetch（GET）| 9 | T01, T02, T03, T13, T15, T23, T26, T27, T30 |
| true: XMLHttpRequest | 4 | 直接 2（T17, T18）、ヘルパー経由 2（T19, T20）|
| true: オブジェクトのメソッドから | 14 | ReceptionDesk 9 / LabDesk 5。this.queueUrl 経由 1 件（T09）|
| false: 到達しない・コメント | 6 | 未使用文字列、if (false)、return 後、行コメント内の文章、ブロックコメント内 fetch、旧呼び出しのコメント |
| false: データ・文字列 | 4 | モック配列 2、JSON ポインタ、alert 文言中の API 名 |
| false: 外部オリジン | 2 | path は origin を除いて記載、origin は note |
| false: console のみ | 2 | console.log（DEBUG ガード内）、console.warn |

（カテゴリは重なる。1 件が複数の書き方を同時に含む。）

## 判断基準

- 正解は、作成者が JS を人として読んで決めた。実行・ツール判定はしていない。
- should_detect=true: ページ読み込み後の通常の操作で実際に呼ばれうる呼び出し。呼び出し元関数が window 公開されていない／画面から直接配線されていなくても、
  関数・オブジェクトメソッドとして到達可能なものは true とした。
- false: 到達不能、コメント、データとして保持するだけ、API ではない文字列、外部オリジン、console 出力のみ。
- path は先頭 `/`、変数部分は `:param`（param 名は問わない）、クエリは含めない。外部オリジンは path に origin を含めず note に記載。
- method は呼び出しから静的に決まるものを大文字で記載。条件式で決まる T29 は null（path のみ判定対象とする）。method 省略の fetch は GET。
- false 側の method は、コードが示す意図の method（不明なら null）。照合は should_detect=false のものが検出されたら誤検出、という使い方を想定。
- X01, X02 は利用者入力で決まる URL。`exclude_from_metrics: true` で数えない。

## 限界

- 1 サイト・1 業種（外来受付）・1 作者の癖。ES5 / ES2017 の素朴な書き方が中心で、bundler 由来の出力、動的 import、axios / jQuery.ajax / WebSocket、
  GraphQL、class 構文、setter / Proxy 等は含まない。
- `this.queueUrl` のようなプロパティ経由は 1 件のみ。オブジェクトのメソッド呼び出しの追跡一般は薄い。
- T14（ヘルパー内連結を含む 4 段）は難度が高い。解けなくても致命ではないが、集計には含む。
- 同一 path を複数 method で使うケース（lab/orders/:param の PATCH/DELETE）は 1 組のみ。
- コードの規模が小さい（6 ファイル）ため、割合の信頼区間は広い。

## 失効（最終判定に使っていない）
2026-10-20 に 1 回測定し、R 0.704 で基準未達。結果を見て製品を直したため、この holdout は失効した。以後は開発用（原因分析）にだけ使う。最終判定は holdout_v5/routes。
