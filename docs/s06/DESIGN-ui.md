# S06 対検査レビュー画面 UI 設計（W1・2026-10-24）

基準: 案1 の骨格（左 要件定義書／中央 基本設計書／右 指摘）、案3 の承認・証跡パネル（右上タブ「証跡」）、案5 の判定帯（下部「全体／今回の変更分」）。
契約: docs/s06/CONTRACT.md の API をそのまま fetch する。

## 部品
| 領域 | 中身 | API |
|---|---|---|
| 見出し帯 | 両文書の版・再読み込み | GET /docs |
| 左・中央 | 章ごとの本文・該当箇所の強調 | GET /docs |
| 右「指摘」 | 絞り込み 4 種・カード・採否 4 操作 | GET /findings・POST decide/revoke |
| 右「証跡」 | 承認フォーム・証跡（新しい順） | GET /trail・POST /approve |
| 判定帯 | 全体／今回の変更分の合否・理由 | GET /findings の gate |

## 状態 6 種（data-state。API 応答だけで切り替える）
| 状態 | 発生 | 見せ方 |
|---|---|---|
| 読込中 loading | 表示直後〜応答まで | 本体に骨組みを重ねる |
| 通常 normal | findings 1 件以上 | 3 列＋判定帯 |
| 0 件 empty | findings 0 件 | 一覧に空文言 |
| 失敗 error | findings/docs が失敗 | 本体に文言＋再読込 |
| 未保存 unsaved | 書込の通信断・5xx | 通知帯＋もう一度保存 |
| 競合 conflict | 書込が 409 | 通知帯＋最新を読み込む |

400/403/404 の書込失敗は状態を変えず、API の message を通知（承認は承認欄の下）に出す。

## 業務フロー
レビュー一覧で案件を開く → openReview が pair を表示 → GET findings/docs/trail → 指摘を選ぶ（両文書の quote を強調・中央へスクロール）→ 採用/不採用/要確認/取消 → POST → GET findings・trail で再描画（判定帯が再計算値に変わる）→ 全体合格かつ理由ありで承認 → POST /approve → 証跡に残る。

## 変えた点／変えない点
- 変えた: docverify-core.js に pair を登録（REVIEW_VIEWS・TITLES・PAGE・SECTIONS・STEPS）。一覧から openReview(id,'read') で開いたときは pair を出す（#read 直指定は従来どおり read）。
- 変えない: 既存ビュー・共通ファイル・API・保存形式。
- 共通への変更要求: なし。
