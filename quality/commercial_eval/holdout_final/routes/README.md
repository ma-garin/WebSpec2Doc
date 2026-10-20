# 最終判定用 holdout: 配布済み JS からの route / API 抽出

**最終判定用の holdout。改善に使っていない。** 開発セット（`quality/commercial_eval/routes/`）とは題材（予約管理 SPA）・ファイル構成・コードの書き方を変えてあり、ケースは重ならない。
**製品コード（src/, web/, static/, scripts/）を参照していない。** 製品も解析ツールも実行していない。形式を合わせるために読んだのは、開発セットの README・expected.json・app.js の先頭のみ。

## 目的
配布済み SPA の JS から画面 route と API endpoint を抽出する機能の、最終的な再現率・適合率を一度だけ測る。`site/` を静的配信し、解析結果を `expected.json` と突き合わせる。このセットを見て製品を調整したら、holdout としては失効する。

## 規模
n = 43（should_detect=true: 31 / false: 12）。kind は route と api。

| category | 件数 |
|---|---|
| comment | 3 |
| console_log | 1 |
| dead_code | 2 |
| delete_api | 1 |
| dynamic_route | 2 |
| external | 3 |
| get_api | 1 |
| js_navigation | 2 |
| nested_route | 4 |
| not_found | 1 |
| patch_api | 1 |
| post_api | 1 |
| put_api | 2 |
| query_api | 2 |
| redirect | 3 |
| static_route | 6 |
| template_api | 3 |
| test_mock | 2 |
| unreachable | 2 |
| unused_string | 1 |

## 構成
- `site/index.html` と `site/assets/{config,router,api,app}.js`。自前ルータ、フレームワークなし、minify なし、外部 CDN なし。
- `expected.json`: 各 case は id / kind / method / path / should_detect / category / file / note（開発セットと同じ形式。id は `H01`〜）。
- 開発セットとの違い: ベース URL 定数（`API_BASE = '/api/v2'` を `config.js` に置き、`api.js` で連結・テンプレート展開）、メソッドを第 1 引数に取る `http(method, url, body)` ヘルパー、ナビゲーション関数の別名（`goTo = Router.navigate`）、ネストした route（動的セグメントが 2 つ）、`Router.notFound(fn)` 形式の 404、`TEST_MOCKS` のモック定義、`console.log` 内の URL。

## 正解の作り方
正解は `site/` の JS を書いた人間が、書いた内容から決めた。note 列に根拠を残した。

- 定義または呼び出しとして実在するもの（到達不能な route、未呼び出し関数内の fetch を含む）は `should_detect=true`。
- コメント内、`if (false)` 内、`return` 後、未使用定数・未使用配列、`console.log` 内の文字列、外部 origin の URL、モック定義は `false`。
- 同一 method・path の重複呼び出しは 1 件（`GET /api/v2/bookings`）。同じ path でも method が違えば別件（`GET` と `POST /api/v2/bookings`）。

## 正規化の規則
- 動的セグメントは `:param`（テンプレート `${id}`・文字列連結による動的部分も同様）。パラメータ名の差は無視してよい。
- 末尾スラッシュ・クエリ・フラグメントは除く。
- ベース URL 定数は値に解決して比較する（`API_BASE + '/bookings'` は `/api/v2/bookings`）。解決しない実装の場合の扱いは評価側で別途記録する。
- `Router.notFound(fn)` は catch-all `*` として扱う。外部 URL は origin 付きのまま `should_detect=false`。
- js_navigation（`/receipts/print`, `/support`）は Router.add が無いが、遷移先として実在する route として数える。評価時は category で切り分けて報告できる。

## 限界
- 手書きの小規模サイト（n=43）。実サイトのバンドラ出力（難読化・チャンク分割・動的 import・変数経由のパス）は含まない。
- 作成者は 1 名。正解の判断は第三者のレビューを受けていない（裁定なし）。`Router.notFound` を `*` と数えるか、js_navigation を route に数えるかは判断が分かれうる。
- ベース URL 定数の解決は 1 つの定数のみ。多段の定数参照や環境変数経由は含まない。
- 構文は node の `--check` 相当で確認する程度で、ブラウザでの実行は未実施（未検証）。

## measured commit
main 48c97cb に Commercial Accuracy Finalization の変更を載せた作業ツリーで、2026-10-20 に 1 回だけ測定した（改善はすべて開発セットで行い、このセットの結果を見た後に製品は変更していない）。結果は `result.json`。
