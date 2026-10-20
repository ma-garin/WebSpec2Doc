最終判定用 holdout。改善に使っていない。製品コードを参照していない。

# holdout_v5 / routes

配布済み JS から API 呼び出し先（method + path）を抽出する機能の評価用データ。

## 題材と規模

- 題材: 自治体の粗大ごみ収集の申込ポータル（住民向け申込・手数料支払い・運営担当者画面）。
- site/index.html と site/assets/ の 6 ファイル（非 minify・外部 CDN なし）。
  index.html が `<script src="/assets/xxx.js">` で全部を読み込み、大域スコープを共有する。
  読み込み順: config.js, http.js, apply.js, operator.js, legacy.js, mocks.js
- expected.json: kind=api の 50 件（should_detect=true 31 件、false 19 件）。
  うち 1 件（api-031）は `exclude_from_metrics: true`（宛先が実行時入力のため静的に決まらない）。
  指標に入るのは true 30 件 + false 19 件。

## カテゴリ別件数（category は各ケースの主な書き方）

true（31）:
helper 2 / helper_2level 3 / helper_method_arg 1 / string_concat 2 / template_literal 2 /
multi_stage_const 2 / cross_file_base_const 2 / options_method 3 / local_var 2 / iife_local_var 1 /
object_method 2 / arrow_function 1 / xhr 4 / literal_string 2 / method_unknown 1 / dynamic_url 1（除外）

false（19）:
unused_string 2 / dead_code_if_false 1 / dead_code_after_return 1 / comment 2 / mock_data 4 /
non_url_string 2 / external_origin 2 / console_log_only 2 / error_message_text 1 / page_route 1 / static_file 1

補足: category は主たる書き方 1 つだけ。実際には複数が重なる（例: COLLECTION_BASE を使う呼び出しは
すべて API_PREFIX/API_VERSION -> API_BASE -> COLLECTION_BASE の多段定数で、別ファイルの config.js に定義がある）。
method 省略の fetch（GET）は api-005, 006, 007, 009, 015, 017, 019, 022 など 8 件超。
fetch の method が小文字（`"post"`）の例は api-013（正解は大文字）。

## 判断基準

- path は先頭 `/`。変数部分は `:param`（変数名があればその名前）。クエリ文字列は含めない。
- method は大文字。静的に不明なら null（api-024: init を引数で受ける）。
- 外部オリジンは path に origin を含めず note に書く。
- should_detect=true: このサイトの API として実行時に呼ばれうる呼び出し。
  関数が定義されているだけで画面から呼ばれていなくても、到達可能な通常の関数なら true とした。
- should_detect=false: 到達不能（`if (false)`・return の後ろ）、コメント内、使われない定数、ダミーデータ、
  fetch/XHR に渡されず値として存在するだけの文字列、URL ではない似た文字列、外部オリジン、
  console.log に出すだけの URL、ページ遷移用 path、静的ファイル。
- 正解は、作成者が JS を読んで決めた。製品・評価器・既存の評価データは参照も実行もしていない。
  node --check で構文のみ確認した。

## 限界

- 1 サイト・約 330 行の小規模データ。統計的な精度評価ではなく、書き方の網羅確認向け。
- ヘルパー内部の `fetch(API_BASE + path)` のように path が引数のまま残る呼び出しは、ケースに含めていない
  （呼び出し側で解決された結果を評価する前提）。
- 外部オリジンの path（`/v1/search` など）は、本サイトの API ではないので false にしてある。
  外部 API も抽出対象とする運用なら、この 2 件の扱いを変えること。
- 到達可能性が実行時の状態に依存するもの（機能フラグなど）は入れていない。
- 実際のブラウザでの実行検証は未実施。

## measured commit
main d60258e に Final Accuracy Closure の変更を載せた作業ツリーで、2026-10-20 に 1 回だけ測定した。結果は `result.json`。
