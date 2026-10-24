# S04 DONE（2026-10-24・ポート 8774・認証オフ）

## 通した経路（実データ・ジョブ 2 件）
- /cli 投入 → POST /api/v1/sites/127.0.0.1/crawl → api_crawl → start_crawl_job → output/127.0.0.1/report.json → job_queue（メモリ）→ 完了・終了コード 0・「結果のレポートを開いて内容を確認してください。」
- /cli 投入 → POST /api/v1/sites/localhost/crawl（http://localhost:9/）→ 同上 → 出力なし → 失敗・終了コード 1・「対象サイトの解析が途中で失敗しました…深さ・最大画面数を減らして再投入してください。」
- 同サイト再投入 → 409 {error:{code:conflict, message, job_id}} → 画面は競合状態＋「動いているジョブを開く」
- GET /api/v1/jobs → api_jobs → list_jobs_in_scope → 一覧・判定帯（全体=不合格で localhost を名指し／今回の投入分）・右パネル証跡（投入者「認証なし（ローカル実行）」・時刻・終了コード・ログ末尾）
- GET /api/v1/schedules（output/127.0.0.1/schedule.json を enabled:false で置いて確認）→ 画面の「停止する」→ DELETE /api/v1/sites/127.0.0.1/schedule → 0 件表示に戻る
- エラー形式: 400 bad_request（bad..x）・404 not_found（jobs/nope）・403 forbidden（他オリジンの POST、本文なし 403 を変換）を curl で確認。全応答に meta{target,version,source}
- GET /api/v1/openapi.json: components Error/Meta/Success、crawl は 202/400/401/403/404/409/500、/jobs・/schedules を掲載

## 確認した状態と幅
- 1366×768・1920×1080・1024×660 × 実データ＋9 状態 = 30 通りで document/body/.app-content の横スクロール 0（ヘッドレス Chrome・scrollWidth − clientWidth）
- スクショ: /private/tmp/claude-501/-Users-fujimagariyuki-dev-active-webspec2doc/453414cb-bd3f-477e-9dd9-f5147cdd8a4a/scratchpad/s04shots/

## 未検証
- pytest 未実行（規約により）。tests/test_api_v1.py:128・test_api_v1_schedule.py:73 の assert をエラー形式に合わせて変更済み・未実行
- 権限不足・未保存・復元の実発生（認証オフのため 403 は CSRF でのみ実発生。非管理者の停止 403 は未検証）
- 認証オン時の投入者名（g.auth_user の display_name/username/email を想定・未検証）
- Bearer トークン経由の /api/v1/jobs のテナント分離（同一 _out() 比較のみ・未検証）
- 外部クライアントへの影響

## 変更要求
- なし

## 要判断
- エラーの形を {error:"文字列"} から {error:{code,message}} に変えた。/api/v1 外部クライアントには破壊的変更（版 v1 固定の方針と衝突）。維持するなら v1 は旧形式に戻し新形式は別版にする
- 「版」を API の版（1.0）と解釈した。データの版（スナップショット時刻）を入れるかは未決
- 500 は共通語彙に無いため internal_error を足した
