# S06 第 2 周 設計（案件一覧・判定と記録・指摘書）

## 画面 × 状態
| 画面 | 状態 | 出し方 |
|---|---|---|
| 案件一覧 | 読込中・0件・検索0件 | data-state＋UIStates |
| 案件一覧 | 失敗・権限なし | 文言＋再読み込み |
| 案件一覧 | 作成中・作成失敗 | 送信ボタン無効・赤字 |
| 判定と記録 | 読込中・0件・失敗 | data-state＋UIStates |
| 判定と記録 | 承認不可・承認済み | 承認ボタン無効＋理由 |

- UIStates は共通 ui-states.js にあれば使い、無い版では同じ文言を自前の枠に描く。

## 業務フロー
- 作成: 案件一覧のフォーム → POST /api/docverify/pair/cases（multipart: name・requirements・design・due）→ pair_cases.create → pair/docs・findings.json・trail.json → engine.inspect（analyze）→ register_inspection → 対検査を開く。エラー: 名前なし・ファイル不足・空・2MB 超・UTF-8 でない を日本語 1 文で返す。
- 一覧: GET /api/docverify/pair/cases → pair_cases.cases（各案件の gate・trail から工程・判定を算出）。
- 判定と記録: GET /<iid>/pair/findings（gate 同梱）＋/trail → 全体／今回の変更分 の合否・名指し・根拠 3 文。承認は POST /<iid>/pair/approve（403 の文言は API の message をそのまま出す）。
- 指摘書: GET /<iid>/pair/report.md（text/markdown・添付）→ pair_cases.report_md。

## 工程と判定の算出（要判断の既定）
- 工程: 承認の証跡あり→承認／全件採否済みかつ全体合格→判定／要確認あり→質問／採否が 1 件でもある→対検査／それ以外→計画。
- 判定: 全件未判定→判定不能／gate 全体の合否→合格・不合格。

## 変えた点・変えない点
- 変えた: サイドバーの入口を案件一覧へ、旧 #reviews は案件一覧へ読み替え。判定と記録は旧 process.js・review.js の独自判定を外し Gate API に一本化。指摘の検討は対検査へ誘導する 1 行。対検査に「指摘書を出力」。
- 変えない: 計画・文書を読む・質問票・修正版の確認の中身（骨格の統一は未着手）。設定タブ担当のファイル、共通ファイル。
- 共通への変更要求: なし。
