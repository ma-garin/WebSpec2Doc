# 画面仕様・Evidence 抽出 評価データ (独立正解)

## 目的

WebSpec2Doc の「画面仕様・Evidence 抽出」(見出し・ボタン・入力項目・リンク・表・エラー文言・API・取得不能の判別)が
どれだけ正確かを測るための、**製品から独立した正解データ**。製品の出力はこのデータと突き合わせて採点する。

- measured commit: main 261a053 ＋ 本 PR の作業ツリー（2026-10-20 計測。結果は同じディレクトリの result.json）
- 測定日: (未記入)

## 構成

- `site/` : 静的サイト。コンテンツページ **n = 22** (`p01.html`〜`p22.html`) + `index.html` (全ページへのリンク)。
  外部 CDN・フォント不使用。JS はインラインまたは `site/js/`。サーバは無く、`/api/...` は 404 になる前提。
- `expected.json` : ページごとの正解 (`{"pages": {"p01.html": {...}}}`)。`index.html` も含む (全 23 ページ)。
- `build_site.py` : site/・expected.json・この README を再生成するスクリプト (標準ライブラリのみ)。

## 正解の作り方

- 正解は、作成者が書いた HTML/JS の内容だけから決めた。**製品コード (src/, web/, static/js/) は読んでいない・実行していない。**
- `build_site.py` の各ヘルパー呼び出しが「HTML を 1 要素書く」と同時に、その要素から人が読み取れる正解を記録する。
  (HTML と正解のずれを防ぐための仕組みであり、製品の抽出ロジックは使っていない。)
- 生成後に別手順 (標準ライブラリ html.parser) で site/ を再パースし、見出し・ボタン・入力項目の数が expected.json と一致することを確認した。

## expected.json の各キーの定義

| キー | 定義 |
|---|---|
| title | `<title>` の文字列 |
| headings | 画面に見えている h1〜h3 (非表示ラッパー内を除く)。文書順・重複はそのまま |
| dynamic_headings | 読み込み後に JS が追加する見出し |
| buttons | 見えている `<button>`・`input[type=submit/button]` の表示文言。重複は個数分。`<a class="btn">` は button ではなく link |
| dynamic_buttons | 読み込み後に JS が追加するボタン |
| fields | 見えている入力項目 (select / textarea / checkbox / radio を含む。radio は 1 個 1 エントリ)。`type=hidden` と display:none の入力は含めない。name 属性が無ければ null。required は真偽値、maxlength/minlength は整数、min/max/pattern は属性の文字列そのまま。label は `label for` / ラベルで囲む / `aria-label` のいずれかの文言、無ければ null (placeholder は使っていない) |
| links | `<a href>` の内部リンク (相対パス・クエリ付きはそのまま)。重複 href は 1 回、初出順。form の action・外部 URL・`#` アンカーは含めない |
| dynamic_links | JS が追加する内部リンク |
| external_links / anchor_links | 外部 URL / ページ内アンカー (links に含めない) |
| tables | 表ごとに `headers` (thead の th) と `rows` (tbody の tr 数、静的 HTML のみ。JS が後で足す行は数えない) |
| error_messages | 初期表示で見えているエラー文言 |
| deferred_error_messages | 送信・blur・API 失敗時に初めて見える文言 (JS 中の文字列。error_messages に出たら誤り) |
| api_endpoints | JS の `fetch` 呼び出し。path はクエリ文字列を除いたリテラル |
| must_not_appear | 非表示要素の文言 (どの種別としても抽出されたら誤検出) |
| hidden_fields | 抽出されたら誤検出になる hidden 入力の name |
| unavailable | 取得できないはずの情報の説明 (iframe の中身・ログイン必須領域・API 依存の内容) |

非表示の種類: `style="display:none"`、`hidden` 属性、`aria-hidden="true"`+display:none、CSS クラス (`css/style.css` の `.is-hidden`)、`visibility:hidden`。
いずれも非表示ラッパー `<div>` で囲んだ要素。

## カテゴリごとの件数 (コンテンツページ 22 件中)

| カテゴリ | ページ数 |
|---|---|
| 紛らわしい要素を含むページ (hidden・重複・動的・ラベルなし のいずれか) | 20 |
| hidden 要素 (display:none / hidden / aria-hidden / class / visibility / type=hidden) を含む | 16 |
| 同じ文言の重複 (ボタン・見出し・ラベル) を含む | 12 |
| JS が読み込み後に追加する見出し・ボタンを含む | 8 |
| ラベルなしの入力を含む | 3 |
| aria-label でラベル付けした入力を含む | 8 |
| 送信するまで出ないエラー文言 (deferred) を含む | 14 |
| 初期表示で見えているエラー文言を含む | 6 |
| fetch による /api/ 通信を含む | 19 |
| 取得できない情報 (iframe・ログイン必須・API 依存) を含む | 5 |
| フォーム入力項目を含む | 16 |
| 表を含む | 9 |

要素の総数 (index.html を除く):

| 項目 | 件数 |
|---|---|
| 見えている見出し (headings) | 66 |
| 動的な見出し (dynamic_headings) | 6 |
| 見えているボタン (buttons) | 49 |
| 動的なボタン (dynamic_buttons) | 7 |
| 入力項目 (fields) | 97 |
| 内部リンク (links, 重複除外) | 63 |
| 表 (tables) | 10 |
| 初期表示エラー (error_messages) | 6 |
| 遅延エラー (deferred_error_messages) | 36 |
| API (api_endpoints) | 19 |
| 誤検出監視文字列 (must_not_appear) | 17 |
| hidden 入力 (hidden_fields) | 7 |
| 取得不能 (unavailable) | 6 |

## 限界

- 作成者 1 名。裁定 (第三者による正解の見直し) は未実施。曖昧な定義は上の表のとおり作成者が決めた。
- 日本語のみ。静的 HTML + インライン JS のみ。SPA フレームワーク、Shadow DOM、canvas、実サーバ応答は対象外。
- サイト規模は小さい (22 ページ)。要素数が少なく、率の信頼区間は広い。
- 動的要素は「読み込み時に無条件で追加されるもの」に限る。API 成功時だけ出る内容は unavailable として扱い、dynamic には入れていない。
- 画面の「見えている」判定は HTML/CSS の記述から人が決めたもので、実ブラウザでの描画確認は未実施 (未検証)。
