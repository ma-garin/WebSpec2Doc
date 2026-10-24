# S00 指揮ホーム 完了記録（2026-10-24）

## 通した経路（実データ・ポート 8770・認証オフ）
- /orchestration → GET /api/home/cases → orchestration.api_home_cases → case_overview.build → JSON（orchestration.cases/1）→ 保存なし（読み取りのみ）→ 失敗時「案件の状況を読み込めませんでした。再読み込みしてください。」(502)
- 源: output/.orchestration/runs/20261024-170000.json（指揮 run・run 段 failed）、output/shop.example.test/report.json・testcases/cases.json・testcases/playwright_report.json（3 件中 1 失敗・1 飛ばし）、data/docverify/a1b2c3d4e5f6/inspection.json（重大 1・要確認 1）
- 結果: 案件 2 件。サイト案件=実行・欠陥が要判断、失敗テスト名「カートに商品を入れて決済できる」を重大で名指し、判定=不合格。仕様評価案件=仕様評価が要判断、V3-A-01 を重大で名指し、判定=不合格。今回の変更分=未判定（理由表示）
- 案件の行を選ぶ → URL に ?case= を付与 → 再読込で同じ案件を復元（restored 表示を確認）
- 段の入口リンク: 仕様評価 /docverify、テスト設計 /sites/<d>/tests、実行 /auto-run?site=、欠陥 /healing?site=
- /systems → 上部「QA 案件から始める」→ /orchestration（カードは「システムを直接開く」の下に残置）
- 源の一部失敗: サイト一覧の取得失敗を模擬 → partial_errors=["sites"]、検査案件のみ返る（画面はバナーで未検証扱いを明示）

## 確認した状態と幅
- 9 状態（通常/読込中/0件/検索0件/失敗/権限不足/未保存/競合/復元）× 1366×768・1920×1080・1024×660 の 27 通りで data-state の切替と横スクロール 0 を数値で確認（Chrome ヘッドレス）
- 検索 0 件（「zzz」入力）で no-match、?case= 直開きで restored を実操作で確認
- /systems 1366 の横スクロール 0
- 撮影: scratchpad/s00shots/（1366 の全状態・site・systems）

## 未検証
- 実 API の 403（認証オン時）での forbidden 表示。切替ボタンでの表示のみ確認
- 競合（再読込時に内容が変わった場合）は切替ボタンでの表示のみ。実データの差分発生は未検証
- 1366×768 では判定帯が本文スクロールの下端にあり初期表示で見えない（CR-00-002 で殻に固定帯を要求）
- pytest・make test・verify-ui・lint は禁止のため未実行。既存 tests/test_orchestration_home.py 等が旧見出し「指揮ホーム」・ナビ文言「サイト」を検査していれば失敗する可能性あり（未確認）
- 認証オン・複数テナントでの表示
- 検証データ（output/・data/docverify/a1b2c3d4e5f6/）はコミットしていない

## 変更要求
- docs/change-requests/S00-1.md（CR-00-001 案件台帳・対象版の共通 API）
- docs/change-requests/S00-2.md（CR-00-002 右パネル・下部判定帯の殻）
