最終判定用 holdout。改善に使っていない。製品コードを参照していない。

# holdout_v3 / routes（図書館ポータル SPA）

## 目的
配布済み JS から「このサイトが実際に呼ぶ API の method + path」を抽出する機能の最終判定用データ。
題材は図書館の蔵書・会員・貸出・延滞料管理 SPA（Maple Library Portal）。正解は作成者が JS を人として読んで決めた。

## 構成と規模
- `site/index.html` と `site/assets/{config,http,catalog,members,circulation}.js`（5 ファイル、非 minify、外部 CDN なし）。
- index.html は 5 本の `<script src="/assets/...">` を順に読み込む。script は大域スコープを共有する（config.js の const が他ファイルから参照される）。
- `expected.json`: 54 ケース。kind=api 50 件（should_detect=true 31 / false 19）、kind=route 4 件（評価外でもよい）。

## カテゴリ別件数（kind=api）
true 31:
helper 7 / fetch_method_option 6 / multilevel_const 4 / template_literal 3 / helper_chain 3 / const_concat 2 / xhr_open 2 / xhr_helper 1 / literal 1 / dynamic_partial 1 / dynamic_unresolvable 1。
補足: カテゴリは主たる書き方 1 つ。path パラメータ（:param）は true 側 15 件が持つ。method 省略の fetch（GET）は 6 件（catalog 2、members 2、circulation 2）。config.js 定義の定数を使うものが 20 件以上。

false 19:
mock_data 4 / external_origin 3 / non_url_text 3 / unused_string 2 / comment_line 2 / dead_if_false 2 / dead_after_return 2 / comment_block 1。

## 判断基準
- should_detect=true: 実行時にそのサイト自身の API として呼ばれうる呼び出し。ボタン等から到達できる関数内の fetch / XMLHttpRequest / helper 経由の呼び出し。
- should_detect=false: 呼び出されない文字列（オブジェクトに置いただけ、モック・フィクスチャ配列、コメント、if (false) / if (0) の中、return 後の到達不能文）、URL ではない説明文・エラー文言、外部オリジン（他社ドメイン）への fetch。外部オリジンは実際には呼ばれるが「このサイトの API」ではないので false。path にはオリジンを含めず note に書いた。
- path は先頭 `/`。変数部分は `:param`。クエリ文字列は含めない。定数は解決後の値（`API + "/catalog"` → `/api/v2/catalog`）。
- method は fetch の options / helper の第 1 引数 / `xhr.open` の第 1 引数から決める。method 省略の fetch は GET。コメントや未使用文字列など method が存在しないものは null。
- 動的ケース（2 件）:
  - `dynamic_partial` `GET /api/v2/:param/count`: 一部が入力由来。固定部分 `/api/v2` と `/count` が分かるので true、可変部分を `:param` とする。可変セグメントを含む path として出せば検出、出せなければ未検出。
  - `dynamic_unresolvable` `GET /:param`: `fetch(<入力欄の値>)`。path は静的に決まらず判断不能。should_detect は true とするが、適合率・再現率の分母から除外して別枠で見ること。「動的・未解決」として報告するか黙って無視すれば合格、誤った具体 path を捏造したら不合格。
- helper 経由の呼び出しは、helper 内部の `fetch(url, opts)`（url・method が変数）自体は単独ケースにしない。呼び出し側ごとに 1 件。
- route（kind=route）はハッシュルーティング表の 4 件。API 評価には含めない。

## 限界
- 規模は小さい（50 件）。1 件の差が約 2 ポイントになるので、有意差の判定には使えず、合否の足切り用。
- 1 サイト・1 題材・1 作成者の書き癖に偏る。axios / jQuery.ajax / WebSocket / GraphQL / `new Request()` / `navigator.sendBeacon` / import 構文 / minify・難読化は含まない。
- 作成者が自分で書いたため、到達可能性（ボタンから呼ばれるか）の判断に主観が残る。`legacyCheckout` など「関数は定義されるが呼ばれない」ケースは判断が割れるので、dead_after_return では return 後の文だけを false にした（関数自体の呼び出し有無は問わない）。
- 外部オリジンの path（`/covers/:param`、`/pixel`、`/v1/collect`）は、オリジン判定ができれば除外できる前提で false にした。
- 実サーバでは動かしていない（静的な JS 読解のみ）。

## 失効（最終判定に使っていない）
2026-10-20 に 1 回測定し、R 0.808 で基準未達。結果を見て製品を直したため、この holdout は失効した。以後は開発用（原因分析）にだけ使う。最終判定は holdout_v5/routes。
