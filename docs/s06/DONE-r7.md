# S06 r7 (feat/s06-polish) 8771 / 1366x768 実測
| 画面 | 横 | 縦 | h1 | JSエラー |
|---|---|---|---|---|
| cases | 0 | 0 | 1 | 0 |
| pair | 0 | 0 | 1 | 0 |
| plan | 0 | 0 | 1 | 0 |
| read | 0 | 0 | 1 | 0 |
| questions | 0 | 0 | 1 | 0 |
| followup | 0 | 0 | 1 | 0 (※) |
| gate | 0 | 0 | 1 | 0 |
| settings | 0 | 0 | 1 | 0 |

※ followup は版が 1 つのレビューで GET /pair/diff が 404（想定内の HTTP 応答、JS 例外ではない）。

## 変更
- h1: 全 8 画面で h1 は 1 つ（共通ヘッダー）。レビュー内の h2.dvr-title を span 化し画面内の二重見出しを DOM から除去。
- pair_review._reasons: 合格時の「未判定は合否に影響しません」（_judge が未判定残を判定不能にするため到達不能）を削除。
- 計画: フォームは docverify-review.js の renderPlan2 の 1 系統のみ（目的・出口基準・期限・担当4役割・対象文書と版、保存先 PATCH は既存）。core.js の存在しない「個別レビューを始める」文言を修正。
- Low: D-23 押せない理由の注記（read・followup。followup は選択まで disabled）／D-26 章ごとの「この章で指摘」ボタン／D-22 10・13.5・16px を 11・13・15px へ／D-24 は既存。
## 要判断（所有外のため未変更）
- D-25 gate の絞り込み chip: 証跡の描画は static/js/docverify-cases.js（所有外）。
- D-20 8pt グリッド: 余白の一括置換は docverify-pair.css 等（所有外）に及ぶため未実施。
- cases の h2.dvc-title は templates/docverify/_cases.html（所有外）。視覚的に隠れており h1 は 1 つ。
- 2 系統目の計画フォームは所有ファイル内に見つからず（他ファイルにある可能性）。
