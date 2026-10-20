# 配布済み JS からの route / API 抽出 評価データ

## 目的

配布済み SPA（ビルド済みバンドル）の JS から、画面 route と API endpoint を抽出する機能の精度（再現率・適合率）を測る。
`site/` を静的配信し、解析結果を `expected.json` と突き合わせる。

- measured commit: main 261a053 ＋ 本 PR の作業ツリー（2026-10-20 計測。結果は同じディレクトリの result.json）
- 測定日: （未記入）

## 規模

n = 42（should_detect=true: 34 / false: 8）。kind は route と api の 2 種。

| category | 件数 |
|---|---|
| comment | 2 |
| concat_api | 1 |
| dead_code | 2 |
| delete_api | 1 |
| duplicate | 2 |
| dynamic_route | 4 |
| external | 2 |
| get_api | 5 |
| js_navigation | 3 |
| not_found | 1 |
| patch_api | 1 |
| post_api | 3 |
| put_api | 1 |
| redirect | 3 |
| static_route | 5 |
| template_api | 2 |
| unreachable | 2 |
| unused_string | 2 |

## 構成

- `site/index.html` と `site/assets/{router,api,app,extra}.js`。自前ルータ、フレームワークなし、minify なし、外部 CDN なし。
- `expected.json`: 各 case は id / kind / method / path / should_detect / category / file / note。

## 正解の作り方

正解は、`site/` の JS を書いた人間が、書いた内容そのものから決めた。製品コード（src/, web/, static/js/）は参照していない。
製品も解析ツールも実行していない。note 列に根拠（該当コード）を残してある。

- 定義または呼び出しとして実在するもの（到達不能な route / 未呼び出し関数内の fetch を含む）は `should_detect=true`。
- デッドコード（`if (false)`）、コメント内の URL、ログ文言・未使用定数だけに出る文字列、外部 origin の URL は `false`。
- 重複定義・重複呼び出し（`/about`、`GET /api/notifications`）は 1 件として扱う。
- `method` は route では null。API は fetch のオプション・XHR・ヘルパー（`apiPost`）から決めた。不明・無関係なものは null。

## 正規化の規則

比較前に両側へ次を適用する。

- 動的セグメントは `:param` に寄せる（`/products/:id`、テンプレート文字列 `` `/api/items/${id}` `` も `/api/items/:id`）。
  文字列連結による動的部分（`'/api/orders/' + orderId + '/cancel'`）も `/api/orders/:id/cancel` とする。パラメータ名の差は無視してよい。
- 末尾スラッシュは除く（`/` 自体を除く）。
- クエリ文字列・フラグメントは除く（`/api/search?q=` は `/api/search`）。
- catch-all は `*`。
- 外部 URL は origin 付きのまま保持し、`should_detect=false` として扱う（検出されたら偽陽性）。

## 限界

- 手書きの小規模サイト（n=42）。実サイトのバンドラ出力（難読化・チャンク分割・動的 import・変数経由のパス）は含まない。
- 動的パスの連結は 1 例のみ。変数にパスを入れて後から fetch するパターンは含まない。
- `/cart` `/help` `/account/settings` はナビゲーション先として存在するが router 定義は無い（サーバ側ページ想定）。評価で route に数えるかは category=js_navigation で切り分けられる。
- `apiPost('/api/feedback')` の method はヘルパー実装（api.js）を読まないと決まらない。静的解析の難所として意図的に入れた。
- `site/assets/router.js` の `'*'` 判定などルータ内部の文字列は case に含めていない。
- 単一の作成者による正解で、第三者レビューは未実施。
