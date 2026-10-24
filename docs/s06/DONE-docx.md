# DONE: 指摘書の Word／Excel 出力（feat/s06-docx）

## 変更
- 新規 `web/services/docverify/pair_report.py`: report.md と同じデータ源（summary・gate・findings・decisions・trail・settings_store.effective）から docx／xlsx を生成
- `web/routes/doc_verify_pair.py`: `GET /api/docverify/<iid>/pair/report.docx`・`report.xlsx` を追加（エラーは report.md と同じ形）
- `static/js/docverify-cases.js`: 「指摘書を出力」を形式選択メニュー（Markdown／Word／Excel）に変更。Esc・外側クリックで閉じる

## 検証（8773・データは本線 data/docverify/v1-a-order-payment の複製を WEBSPEC2DOC_DATA_DIR で使用）
- ダウンロード: md 200（13,036 B）／docx 200（41,212 B）／xlsx 200（8,995 B）。存在しない iid の docx は 404 JSON
- docx（python-docx）: 段落 170・表 6（行数 7／5／5／13／19／7 = 表紙／要約全体／要約変更分／指摘一覧 12 件＋見出し／証跡 18 件＋見出し／判定基準）。Heading 1 は 1〜4 と付録の 5 本。Normal は游ゴシック（eastAsia も設定）、表は Table Grid
- xlsx（openpyxl）: 指摘一覧 13 行×9 列（枠固定 A2・フィルタ A1:I13）／証跡 19 行×5 列（同）／判定 22 行×3 列
- 未検証: 画面のメニュー（ブラウザでの操作・表示）、Word／Excel 実アプリでの見た目、pytest（禁止のため未実行）

## 要判断
- 出力ボタンの処理は `static/js/docverify-pair.js` ではなく `static/js/docverify-cases.js`（`[data-dv-report]` の click）にあったため、そちらを最小差分で変更した
- seed: 投入元（A_order_payment の known_defects.jsonl）が見つからず seed スクリプトは未実行。本線の取り込み済みデータの複製で代用
- 区分（仕様／観測／推論）の付け方: 要件・設計の両引用あり→仕様、自動検査の検出→観測、それ以外→推論、と 1 指摘 1 区分で定義した（report.md は 1 指摘内に 3 区分を併記する形）
- 作成者は summary の assignee（起票者）、承認者は trail の最後の approved。ログインなしの記録者（_none）は「未ログインの利用者」と表示
