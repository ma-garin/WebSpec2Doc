# S06 第 2 周 完了記録

## 通した経路（8768・認証オフ・ヘッドレス Chrome）
- 作成: curl multipart → POST /api/docverify/pair/cases → pair_cases.create → data/docverify/r-dd9e087846/pair/{docs,findings.json,trail.json} → 201（指摘 1 件・LLM 検査は「未実行」として errors に返る）。ファイル 1 つだけ → 400「要件定義書と基本設計書の 2 つのファイルを選んでください。」
- 一覧: /docverify#cases → GET /api/docverify/pair/cases → 2 行（7 列: レビュー名／対象文書と版／工程／期限／指摘／判定／担当）。
- 行クリック → DV.openReview(inspection_id) → 対検査 data-state=normal（inspection id → pair iid の読み替え resolve_iid、main 469f415 と同内容）。
- 採否: POST /<iid>/pair/findings/AI-01/decide → 200 → 判定と記録に「採否を記録」が証跡として出る。
- 判定と記録: GET /<iid>/pair/findings・/trail → 全体 不合格（欠落リンク REQ-MEM-002 を名指し）／今回の変更分 合格・根拠 3 文。
- 承認: POST /<iid>/pair/approve（未ログイン）→ 403「承認にはログインが必要です。ログインしてから承認してください。」
- 指摘書: 判定と記録の「指摘書を出力」→ GET /<iid>/pair/report.md → ダウンロード（種別・重大度・状態・要件/設計の引用・事実/観測/推論・確認手順・証跡。未判定は「未確認」）。存在しない iid → 404「レビューが見つかりません。…」
- 旧入口: DV.show('reviews') → cases に読み替え。指摘の検討 → 対検査へ誘導の 1 行。

## 確認した状態と幅
- 案件一覧: 通常・検索 0 件（search-empty）。判定と記録: 通常・承認不可。
- 横スクロール: 案件一覧・判定と記録 × 1366/1920/1024 すべて 0（documentElement.scrollWidth − clientWidth）。JS エラー 0。

## 未検証
- 案件一覧の 0 件・失敗・権限なし、判定と記録の 0 件・失敗、作成失敗の画面表示（文言はコードのみ確認）。
- ログイン済み利用者での承認成功（認証オフのため）・起票者本人の 403・409 競合。
- UIStates.set 経由の描画（この worktree の ui-states.js に UIStates が無く、自前の枠で表示）。
- 8766 への反映（マージ後に要確認）。pytest は未実行（禁止）。

## 残り
- 計画・文書を読む・質問票・修正版の確認を p1-* 骨格に揃える（未着手）。指摘の検討の下に旧表がまだ出る。
- ページ見出しの状態（「準備中・計画」）は旧 inspection の phase 由来で、案件一覧の工程と食い違う。
- 1024 幅で上部タブ（判定と記録・実画面との照合）が帯の中で見切れる（横スクロールは 0）。
- 要判断: 「判定不能」= 全件未判定 とした。工程の算出規則は DESIGN-r2.md の既定。

## 所要時間
- 開始 18:06 ／ 終了 18:13（ツール 34 回）。
