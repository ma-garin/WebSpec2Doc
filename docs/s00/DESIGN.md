# S00 指揮ホーム 設計（2026-10-24）

## 目的
指揮ホーム（/orchestration）を「案件概況」を入口にし、QA 案件ごとに
仕様評価(06) → リスク → テスト設計(02) → 実行(03/07/08) → 欠陥(05/09) → 判定 の段と状態、
未解消の重大・欠落・未検証を名指しで出す。/systems は案件概況への導線を主にし、カードは副に置く。

## 画面一覧 × 状態 9 種

| 画面 | 状態 | 出すもの | 文言の要点 |
|---|---|---|---|
| 案件概況 | 通常 | 一覧・段・名指し | 判定帯 2 行 |
| 案件概況 | 0件 | 空表示＋2 入口 | 何をすれば並ぶか |
| 案件概況 | 検索0件 | 条件解除ボタン | 文字を消せば戻る |
| 案件概況 | 読込中 | 枠を薄く表示 | 読み込み中 |
| 案件概況 | 失敗 | バナー＋再読込 | 次の行動を 1 行 |
| 案件概況 | 権限不足 | バナー | 閲覧の役割を依頼 |
| 案件概況 | 未保存 | バナー | 読み取りのみと明示 |
| 案件概況 | 競合 | バナー＋再読込 | 再読込で最新へ |
| 案件概況 | 復元 | バナー | ?case= の案件を復元 |
| システム選択 | 通常 | 案件導線＋カード | 案件から始める |

- 状態は #cs-root の data-state（normal/empty/no-match/loading/error/forbidden/dirty/conflict/restored）。
- 画面上部の「表示確認」切替、または ?state=<名> で全状態を撮れる。
- 一部の源が読めないとき（partial_errors）は該当段を「未検証」として扱う旨のバナーを出す。

## 業務フロー
入口 /orchestration → GET /api/home/cases → web/routes/orchestration.py api_home_cases
→ web/services/orchestration/case_overview.build(out_dir)
→ 読む源: workflow_view._list_sites / _latest_run（output/.orchestration/runs/*.json）、
  output/<domain>/testcases/*.json、output/<domain>/{qa_process,testcases}/playwright_report.json、
  healing の承認待ち報告書（project_store / report_doc）、docverify の検査（data/docverify/<iid>/inspection.json）
→ 出力 JSON schema "orchestration.cases/1"（cases[].stages[6]・named[]・verdict{overall,changed}）
→ 保存なし（読み取りのみ）
→ エラー: 502 {"error":{"code":"upstream_failed","message":"案件の状況を読み込めませんでした。再読み込みしてください。"}}

## 案件の暫定定義（共通の案件台帳が無いため）
- サイト案件: 解析済み・接続・実行中の指揮があるサイト 1 つ = 1 案件。
- 仕様評価案件: System 06 の検査 1 件 = 1 案件（サイトへの紐づけ情報が無いため単独）。
- 共通 API（/api/common/v1/cases）が入ったら、案件の正本をそちらへ切り替える（CR-00-001）。

## 段の状態の決め方（未着手/進行中/要判断/完了）
- 仕様評価: 文書も指摘も無い=未着手、未解消の重大または採否未決あり=要判断、終了かつ承認者あり=完了、それ以外=進行中。
- リスク: 台帳が無いので常に未着手＋「欠落」を名指し（数値スコアは作らない）。
- テスト設計: 指揮の tests 段の状態を優先、無ければ testcases の成果物の有無。
- 実行: 指揮の run 段が実行中なら進行中。結果の失敗あり=要判断（失敗テスト名を重大として名指し）、0 件=要判断（未検証）、全件成功=完了。
- 欠陥: 承認待ち報告書あり=要判断、失敗が残り対処記録なし=要判断、実行前=未着手。
- 判定: 共通語彙（合格／不合格／判定不能／未判定）。重大あり=不合格、未完了の段あり=判定不能。
  人の判断（decision）が未記録である旨を必ず併記。「今回の変更分」は対象版が無いので未判定と理由を出す。

## 今回変える点
- /orchestration の home を案件概況に置換。旧サイト一覧（件数中心）は折りたたみの「サイト別の運用状況」に退避（削除しない）。
- サイドバーの第 1 項目名「サイト」→「案件概況」（項目は固定のまま）。
- /systems の上部に「QA 案件から始める」導線を置き、カードは「システムを直接開く」へ格下げ。

## 変えない点
- 個別実行詳細（?site= / mode=detail）、/orchestration/d、既存 API（/api/home/summary ほか）。
- 共通ファイル（殻・topbar・共通 CSS/JS・system_registry）。

## 共通への変更要求
- CR-00-001 案件台帳（common.case）と対象版の API: docs/change-requests/S00-1.md
- CR-00-002 右パネル・下部判定帯の殻への新設: docs/change-requests/S00-2.md
