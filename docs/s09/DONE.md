# S09 DONE（2026-10-24・ポート 8779）

## 通した経路（実データ）
1. POST /api/impact/v2/sample → 見本システム（設計・画面・テスト・つながり）を impact.db に作成
2. links_sys09.submit_changes(iid=a1b2c3d4e5f6, REQ-0001 変更) → crs.create → run.analyze → CR-002（題名「System06 要件変更 a1b2c3d4e5f6」）・impacts 5 件 → impact.db／sys09_impact.json
3. POST /systems/<sid>/documents（要件定義書_会員管理.md）→ requirement 項目 5 件
4. POST /impacts/<id>/resolve（DSN-0003 を対応要）
5. GET /impact?sys=<sid>&cr=CR-002 → GET …/crs/CR-002/decision → decision.build → 影響 5 件リスク順（12,12,6,6,2）・再テスト 4 件（新規 2・再実行 2）・欠落 REQ-0001〜0005・判定 全体=不合格／今回=不合格（DSN-0003 名指し）
6. エラー: GET …/crs/CR-999/decision → 404、画面「変更要求が見つかりません。一覧から選び直してください。」＋再読込
7. 一覧 GET …/crs → S06 起票 2 件に「ドキュメント検証から受領」

## 確認した状態と幅（ヘッドレス Chrome）
- 1366×768・1920×1080・1024×660 × 通常／失敗／一覧／手動 CR: 文書・本文とも横スクロール 0
- 撮影: scratchpad/s09_normal.png ほか

## 未検証
- 0件（未分析 CR）・権限不足・競合の各表示、読込中の撮影
- 判定帯は sticky のため全ページ撮影で本文に重なって写る（スクロール時の実害は未検証）
- pytest 未実行（指示どおり）

## 変更要求
- docs/change-requests/S09-1.md（S06: CR 重複起票の防止）
