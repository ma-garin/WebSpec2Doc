# S05 DONE（2026-10-24）

## 通した経路（ポート 8775・LLM は OpenAIAgent._call のスタブ・外部送信なし）
起動: scratchpad の s05_launch.py（tests/test_healing_native_agents.py と同じく OpenAIAgent._call だけ差し替え）。検証対象は scratchpad/s05demo/repo（add が減算になっている 2 ケースの小リポジトリ）。
1. POST /api/healing/projects → project_store → .healing/projects（201、project_id 発行）
2. POST /api/healing/runs → orchestrator.start_run → 検証 2 件中 1 件失敗 → 欠陥 1 件 → 修正（差分 calc.py 1 行）→ 再検証 2 件中 0 件失敗 → status=awaiting_human（202）
3. GET /api/healing/runs/<id>/trace → trace.build_trace → 工程 6 個・欠陥 1 件（根拠 test_calc.py::test_add と assert ログ／差分／再検証で通過／要確認）・判定帯 全体=合格・今回の変更分=合格（200）
4. POST /api/healing/runs/<id>/decision approve → run.decisions 追記 → trace の判断=採用・判断の記録に「日時・利用者名の記録なし・採用（理由）」（200）
5. エラー: GET /api/healing/runs/20990101-000000/trace → 404「実行が見つかりません。一覧から開き直してください。」
6. 実行前に止まった run（worktree 作成失敗）: 工程「検証＝失敗・検証の前に止まりました」、全体=判定不能（1 回目の試行の実データ。修正後の規則で再取得はしていない）。

## 確認した状態と幅（ヘッドレス Chrome・/healing/runs/<id>[?hl_state=]）
- 1366×768・1920×1080・1024×660 × 通常／読込中／0件／失敗 = 12 通り。文書・#hl-trace・#hl-steps・#hl-view-run の横スクロールはすべて 0、pageerror 0。
- 証跡領域の高さ 481px（3 幅とも）。修正前は 1024×660 で 111px、1366×768 は画面外だった。
- 画像: scratchpad/s05shots/（run-<幅>-<状態>.png, view-<幅>.png, steps-<幅>.png）

## 未検証
- 権限不足・未保存・競合・復元の 4 状態（共通 ui-states.js の関数待ち）。認証オン時の利用者名の表示（AUTH_MODE=off のため「利用者名の記録なし」で確認）。
- PR 作成後の工程「PR」（リモート送信禁止のため未実行）。不合格（再検証でも失敗）の実データ通し（規則は trace.py に実装、データでは未通過）。
- 0件・失敗・読込中は ?hl_state= による表示固定で撮影（実データの 0 件 run は未通過）。
- pytest・make test・verify-ui・check_clipping は未実行（禁止）。

## 発見（既存の挙動・今回は変更せず）
- 実行が preparing のうちに POST decision approve が 200 で受理された（orchestrator.record_decision が状態を見ていない）。要判断。
- auth off では decisions.actor が空。認証済み利用者の証跡は認証オン環境でのみ成立。

## 変更要求
- なし
