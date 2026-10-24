# S10 DONE（2026-10-24・ポート 8780・認証オフ）

## 通した経路（実データ）
- /settings/audit → GET /api/admin/approval-policy → load_approval_policy → 既定値（禁止）表示
- 画面で例外を有効化・理由入力 → PUT /api/admin/approval-policy → save_approval_policy → instance/approval_policy.json（rev 増）→ instance/admin_audit.jsonl に policy.approval_updated（変更項目・版・理由）→ 表に「承認規則の変更」行
- 理由 2 文字 → 400 →「例外を有効にするには理由を 10 文字以上で入力してください。」が入力欄の下に出る
- 古い rev で保存 → 409 →「他の管理者が先に保存しました…」＋最新値、入力は保持、「最新の値を読み込む」で restored
- GET /api/admin/audit?case=cs_demo → decision.approve 1 件（理由付き・api_key は [REDACTED]）。actor=lead&since=2026-10-24 → review.adopt 1 件。case=none → 0 件（画面は no-match 文言）
- GET /api/admin/audit.csv?case=cs_demo → BOM 付き CSV（日時・利用者ID・利用者・操作・案件・…・理由）
- GET /api/settings → *_masked は空（秘密値の部分表示なし）

## 確認した状態と幅（ヘッドレス Chrome・横スクロール量）
- 1366×768: normal/dirty/invalid/no-match/conflict/restored/保存後 すべて 0px
- 1920×1080・1024×660: normal/dirty/invalid/no-match すべて 0px。JS エラー 0

## 未検証
- forbidden（認証オン・非管理者）と error（通信断）の表示は実機で未確認（コードのみ）
- 監査 empty 状態（記録 0 件）は未撮影
- since/until は UTC の記録時刻と日付文字列の比較。JST 0〜9 時の境界で 1 日ずれる
- pytest は禁止のため未実行。test_settings_* / integrations の *_masked 期待値が変わった可能性
- 設定タブ名は 1024 幅で 2 行に折れる（既存の set-tabs。今回の改名でも同様）
- 承認 API での 403 判定そのもの（CR-10-2）

## 変更要求
- docs/change-requests/S10-1.md（pages.py タブ追加）
- docs/change-requests/S10-2.md（承認 API が規則を読む）
