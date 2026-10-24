# System 01 ドキュメント作成 — 設計（波 B）

## 画面 × 状態（対象: 結果パネルの「対象と版」判定帯 `#s01-versions`）

| 状態 | 表示 | 次の行動の文 | 実装 |
|---|---|---|---|
| 通常 | 対象・版・判定帯・区分表 | 失敗行に添える | 済 |
| 0件 | 解析画面 0 の失敗文 | URL を確かめ再解析 | 済 |
| 検索0件 | 対象外（検索なし） | — | 対象外 |
| 読込中 | 読み込み中の文 | — | 済 |
| 失敗 | API の日本語文 | 再読み込み | 済 |
| 権限不足 | 共通 403 | — | 共通側 |
| 未保存 | 対象外（編集なし） | — | 対象外 |
| 競合 | 対象外（編集なし） | — | 対象外 |
| 復元 | 対象外 | — | 対象外 |

- 0件は「解析できた画面が 1 件もない」で、参照切れ（API 404）は失敗として別に出す（common-contract §2.3）。

## 業務フロー（クロール→生成→結果→実行履歴を版で束ねる）

1. 入口: /dashboard の URL 入力 → POST /run（web/routes/crawl.py、変更なし）→ src/main.py
2. 出力: output/<domain>/report.json・snapshots/<時刻>.json（1 版）・audit.jsonl（記録）・drift_summary.json
3. 結果: showResults(domain) が #r-domain を書く → s01-versions.js が GET /api/s01/versions
4. service: web/services/s01_versions.py `build_site_versions`（読むだけ。保存しない）
   - 版 = snapshots の各ファイル（新しい順。最新が「今回」）
   - 今回の変更分 = 最新と 1 つ前を compute_diff。項目名で名指し
   - 区分 = 画面一覧/仕様書/遷移は「観測」、テストケースは「推論」、取得できない画面は「未確認」
   - 失敗 = audit.jsonl の最後のクロール分（ログイン壁・robots・unsafe_url・page_skipped）と、応答 4xx/5xx の画面
5. 判定帯（共通語彙のみ）
   - 全体: 未確認が 1 件でもあれば「判定不能」＋URL と理由を名指し。無ければ「合格」
   - 今回の変更分: 前回版なし→「未判定」、差分あり→「未判定」＋変更を名指し（人の確認待ち）、差分なし→「合格」、比較失敗→「判定不能」
6. エラー文言: 400「対象サイトの指定が正しくありません。一覧から選び直してください。」／404「まだ解析されていません。URL を入れて解析してください。」／500「少し待ってから再読み込みしてください。」

## 変える点
- 結果パネル上部に「対象と版」判定帯を追加（result-panel.html・s01-versions.js・report-v2.css 末尾）
- /api/s01/versions を新設（web/routes/site.py）
- 404 等のエラーページを「取得済み」と数えない（旧 /api/snapshots は画面数に含めていた）

## 変えない点
- /run・ウィザード・既存タブ・/api/snapshot-diff*（既存 E2E が参照）
- 版の選択で過去版どうしを比べる操作（判定帯の select は一覧表示のみで無効化。比較は既存「変更」タブ）
- /sites/<domain>/<ws> は templates/workspace.html（S02 所有）で描くため今回は触らない

## S01·app（/doc-app 試作）の扱い — 残す（主導線から外す）
- 判断: 削除しない。主導線（/dashboard の新規解析）には既に出ていない（app_mode のときだけ描画）
- 根拠: ①実解析は未対応で、出力はサンプル固定（web/services/app_mock.py）＝商用の主導線に置くと「観測」と誤認させる ②一方で tests/test_doc_app_truth.py が「試作であることを明示する」振る舞いを固定しており、削除は他担当と利用者の参照を切る ③入口カードは共通の web/system_registry.py にあり S01 からは外せない
- 対応: 入口カードを主導線から外す変更要求を CR-01-1 として出す

## 共通への変更要求
- CR-01-1: web/system_registry.py の /doc-app 入口を一覧の主導線から外す（docs/change-requests/S01-1.md）
