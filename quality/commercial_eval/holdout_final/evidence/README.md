# 画面仕様・Evidence 抽出 最終判定用 holdout

最終判定用の holdout。**改善に使っていない**。製品の出力はこのデータと突き合わせて採点するだけで、結果を見て製品を直し、このデータを直す、という往復には使わない。

## 目的
WebSpec2Doc の「画面仕様・Evidence 抽出」(見出し・ボタン・入力項目・リンク・表・エラー文言・API・取得不能の判別)の最終判定用の独立した正解。開発セット (`quality/commercial_eval/evidence/`) とドメイン・画面を重ねていない (保険見積・学習管理・物流追跡・自治体の申請・SaaS の請求管理)。

## 独立性
- 製品コード (src/, web/, static/, scripts/) は参照していない (読んでも grep してもいない)。製品も実行していない。git・pytest も使っていない。
- 開発セットから借りたのは形式 (README の構成と expected.json のキー) だけ。
- 正解は `build_holdout.py` のヘルパが「HTML を 1 要素書く」と同時に記録した。製品の抽出ロジックは使っていない。

## 構成
- `site/` : コンテンツページ **n = 17** (`h01.html`〜`h17.html`) + `index.html`。外部 CDN・外部フォント不使用。JS はインライン。サーバは無く `/api/...` は 404 になる前提。
- `expected.json` : `{"pages": {"h01.html": {...}}}`。`index.html` を含む (全 18 ページ)。キーは開発セットと同じ。
- `build_holdout.py` : site/・expected.json・README (evidence と viewpoints の両方) を再生成する。標準ライブラリのみ。

## 定義 (開発セットと同じ。判断が分かれる所だけ追記)
- headings: 見えている h1〜h3。非表示ラッパー内・閉じた details 内は含めない。文書順・重複はそのまま。
- buttons: 見えている `<button>` と `input[type=submit/button]`。重複は個数分。`<a class="btn">` は link であり button ではない。
- fields: 見えている入力項目。`type=hidden` は含めない。**disabled / readonly の入力は見えているので含める**。表の中・form の外の入力も含める。radio / checkbox は 1 個 1 エントリで、label は各自の `label for` の文言 (fieldset の legend は label ではない)。aria-label も label とみなす。placeholder だけのものは label = null。
- links: 内部リンク (クエリ付きはそのまま・重複 href は 1 回・初出順)。外部 URL は external_links、`#` は anchor_links。
- error_messages: 初期表示で見えるもののみ。JS 中にしか無い文言 (送信・blur・API 失敗時) は deferred_error_messages。
- must_not_appear: 非表示要素内の文言。どの種別としても抽出されたら誤検出。hidden_fields: `type=hidden` の name。
- 非表示の種類: `style="display:none"`、`hidden` 属性、`aria-hidden="true"` + display:none、CSS クラス (`css/h.css` の `.gone`)、`visibility:hidden`、閉じた `<details>`。
- unavailable: iframe の中身・ログイン必須領域・API/canvas に依存する内容。

## 件数 (コンテンツページ 17 件中)
| 観点 | ページ数 |
|---|---|
| 非表示 (hidden 系) を含む | 14 |
| 閉じた details を含む | 1 |
| type=hidden の入力を含む | 7 |
| 同じ文言 (見出し・ボタン・ラベル) の重複を含む | 8 |
| form 外の入力 (表の中など) を含む | 2 (h06, h13) |
| radio / checkbox のグループを含む | 11 |
| JS が読み込み後に追加する要素を含む | 4 |
| disabled / readonly の入力を含む | 3 (h02, h11, h15) |
| ラベルが placeholder だけの入力を含む | 3 (h03, h06, h14) |
| aria-label でラベル付けした入力を含む | 3 (h06, h12, h13) |
| 送信・blur・API 失敗で初めて出るエラー (deferred) を含む | 16 |
| 初期表示で見えているエラーを含む | 2 (h05, h11) |
| API 通信 (fetch) を含む | 17 |
| 取得できない情報 (unavailable) を含む | 6 |
| iframe を含む | 1 (h09) |

## 限界
- 作成者は 1 名で、第三者による裁定は行っていない。
- 静的な HTML と素朴な JS だけ。SPA フレームワーク・Shadow DOM・動的に変わる URL・実在するバックエンドは扱わない。
- 文言は日本語のみ。ページ数 (17) は少なく、1 ページの誤りが数 % に響く。
- disabled の扱いなど、定義が分かれる所は上記で決めた。別の定義で採点すると差が出る。

## measured commit
main 48c97cb に Commercial Accuracy Finalization の変更を載せた作業ツリーで、2026-10-20 に 1 回だけ測定した（改善はすべて開発セットで行い、このセットの結果を見た後に製品は変更していない）。結果は `result.json`。
