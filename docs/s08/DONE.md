# S08 DONE（2026-10-24・ポート 8778・実データ通し）

## 通した経路（tests/system08/conftest.py の DDL と同じ表を ローカル PostgreSQL の s08_e2e に作成）
- POST /api/backend-test/jobs → 201 → data/backendtest/27cfd96e03ae/job.json
- POST …/files（schema.sql）→ 200 → files/ ・facts
- 段階 1〜6 generate/approve → すべて 200 → versions/（ケース 66 件。各ケースに basis・expected・oracle.state あり）
- POST …/envs → 201、…/envs/e1/check → 200（接続可）
- POST …/runs/preview → 200（書き込みあり・確認トークン）→ POST …/runs → 202 → GET …/runs/<rid> 終了 done
- GET …/runs/r20261024-01/results → 200 → evidence/r20261024-01/<case>
- POST …/judge（段階 7 未承認）→ 409「段階 7（実行）が未承認です。先に承認してください。」
- 段階 7 承認 → POST …/judge → 200。全体＝不合格（合格 1・不合格 2・未検証 63）、名指し 128 件中 20 件表示。2 回目の判定で今回の変更分＝未判定（変更 0 件）
- GET …/export/report.xlsx → 200（PK）
- 存在しない案件 #job=000000000000 → 「案件が見つかりません。一覧から選び直してください。」
- スクリプト: scratchpad/s08_through.py・s08_ui.py

## 確認した状態と幅（ヘッドレス Chrome）
- 1366×768・1920×1080・1024×660 × 一覧／実行履歴／カタログ／段階 4・7・8／失敗：文書の横スクロール 0、JS エラー 0
- 1024 幅のカタログと段階 4 は表がはみ出すが内側スクロール（c-table-wrap）で、文書の横スクロールは 0
- 段階 8 判定帯：data-state=normal で 全体・今回の変更分 の 2 行を表示（3 幅）
- 修正: 判定帯の id が既存の id="bs-gate"（実行前の確認リスト）と重複していたため s8-verdict-band に変更

## 未検証
- pytest（禁止のため未実行）。既存 test_judge/test_api との互換は未確認（追加は judgement の bands・case_ids のみ）
- 状態 0件・読込中・権限不足・未保存・競合・復元の画面表示（共通関数待ち・data-state 切替は未実装）
- 今回の変更分が 1 件以上になる経路（ケースを編集して再判定）
- 結果 API の応答に絶対パス（diff_path）が含まれる。画面に出るかは未確認
- 認証オン時の利用者名の証跡（by は認証オフで local）
- 実行結果の案件への紐付（capability-map の新設 1 件）は未着手

## 変更要求
- docs/change-requests/S08-1.md（下部判定帯を殻へ）

## 要判断
- 「今回の変更分」の定義を「前回判定より後に追加・変更されたケース」とした。「直近の実行に含めたケース」とする案もある
- 既存の判定語（保留（未検証 N 件））と共通語彙（判定不能）が並ぶ。既存を共通語彙へ寄せるか
