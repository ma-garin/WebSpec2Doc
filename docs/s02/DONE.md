# System 02 DONE（2026-10-24・ポート 8772・認証オフ）

## 通した経路（実データ 1 本）
1. POST /api/docverify/inspections → 検査 3a2636cdeb1e → data/docverify/3a2636cdeb1e/inspection.json
2. POST /api/docassure/inspections/<iid>/analyze（要件 4 件の文書）→ assurance.json
3. POST /api/docassure/inspections/<iid>/system02/push → links_sys02.push_candidates → output/docassure-<iid>/ta2/tests.json（9 件作成、REQ-004 は要明確化で未登録）
4. GET /test-automation?design=docassure-<iid>&case=PW-0001 → 200、ボードに「ドキュメント検証から受領（検証 3a2636cdeb1e）」
5. GET /api/ta2/design/sources → ta2_design.sources → 1 件（S06 由来を先頭）
6. GET /api/ta2/design?domain=… → ta2_design.board → 9 ケース（根拠要件・要件本文・観点・期待結果・状態）。全体=判定不能（要確認 4・未実行 5・欠落リンク REQ-004 を名指し）
7. POST /api/ta2/design/baseline → design_baseline.json（記録者「ゲスト」・時刻）
8. PUT /api/ta2/tests/PW-0001（名前変更）→ 再取得で「今回の変更分」1 件・判定不能（要確認 1 を名指し）
9. エラー: expected_at 不一致 → 409「他の人が先に基準を記録しました。画面を再読み込みしてから記録してください。」／domain=../x → 400／存在しない設計 → 404「このテスト設計はまだありません。一覧から別の設計を選んでください。」

## 確認した状態と幅（ヘッドレス Chrome）
- 1366×768・1920×1080・1024×660 × 通常／読込中／0 件／失敗／競合／検索 0 件 = 18 通り。文書横スクロール 0・区画横はみ出し 0・内部の見切れ 0（数値で確認）
- 撮影: scratchpad の s02_<幅>_<状態>.png と s02_full_1366.png（サイドバー・上部バー込み）
- 復元: ?design=&case= の直開きで選択ケースが右パネルに出ることを確認

## 未検証
- 合格・失敗の状態表示: docassure 由来ケースは実行手段が無く、実データでは未実行・要確認だけを確認（判定規則はコード上のみ）
- 認証オンでの記録者名（認証済み利用者）: 認証オフのため「ゲスト」で記録。オン時は current_user() の名前になる想定で未検証
- 403 表示: 管理者以外での画面確認は未実行（文言のみ実装）
- 指摘（findings）の紐付け表示: 今回の文書では指摘 0 件で、表示は「結びつく指摘はありません」のみ確認
- pytest・make test・verify-ui・lint: ブリーフにより未実行
- 廃止候補 7 ルート: 未変更（DESIGN.md に扱いを記載）

## 変更要求
- CR-02-001（docs/change-requests/S02-1.md）: /sites/docassure-<iid>/tests を開けるようにする（pages.py・S00 所有）
