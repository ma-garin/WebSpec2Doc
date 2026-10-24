# C2 証跡・判断・承認の共通 API と機能契約（2026-10-24）

## 変更
- 新規 web/services/common/evidence.py（証跡 audit.jsonl・seq＋SHA-256 連鎖・追記/読取/検算のみ。C2 の最小ストアとエラー型 CommonError も同居）
- 新規 web/services/common/decisions.py（decisions.jsonl に drafted/approved/revoked を追記。状態は畳み込み）
- 新規 web/services/common/risks.py（risks/<rk>.json・rev・数値スコア拒否・severity/priority 別欄）
- 新規 web/routes/common_decisions_api.py（/api/common/v1/cases/<cid>/risks・decisions・approve・revoke・evidence）
- 新規 tests/test_common_decisions_api.py（4 件。未実行）
- quality/feature_contracts.yml: document_inspection の persistence を実装（{iid}/inspection.json・assurance.json・sys09_impact.json・_audit/_r4_audit）に是正し、required_test_ids を実在 node id で追加。他 72 件は required_test_ids:{} で形式だけ揃えた。common_case（high・partial）を登録
- scripts/quality_harness.py: required_test_ids の node id 実在（tests/ のファイル＋def 名）と、required_tests の各語に 1 件以上を照合。不在は NG。空の high/critical は test_id_unverified として件数表示

## 通した経路（Flask test client・実データ・2026-10-24 17:48）
- POST decisions → decisions.draft → decisions.jsonl・audit.jsonl → 201。同じ Idempotency-Key は同じ id
- approve 起票者本人 → 403「起票した本人は承認できません…」／ゲスト → 403「承認はログインした利用者だけ…」／gate.passed=false → 403「合格していない判断は…」／rev 不一致 → 409 conflict（actual_rev）
- approve 別人 → 200 approved（by.user_id=u_b）→ revoke → 200 revoked（削除せず追記）
- 他テナント参照 → 404／Idempotency-Key 無し → 400／risk score 付き → 400／risk PATCH rev 古い → 409／未知の案件 → 404
- GET evidence → 6 行・連鎖 ok。2 行目を書き換えると line=2 で検出
- harness 1 回実行: PASS・validated_features=73（その後 test_id_checked の数え方を 1 行修正。修正後は未実行）

## 未検証
- pytest（tests/test_common_decisions_api.py・S06 の node id の実行結果）: 未実行
- 認証オン（実セッション・auth_store の users 行）での主体取得: 未検証（test client で g.auth_user を差し込んで確認）
- 実サーバ 8783 での起動: 未実行（下記 CR のとおり blueprint が未登録のため）

## 要判断
1. 「未合格」の定義: 判断本文の gate.passed（起票時に結果の合否を持たせる）が false なら承認 403 と解釈した。合否を参照先（06 の判定等）から自動で引くかは未決
2. 保存先: 契約 §1.3 は data/common/<t>/ と scoped_output_dir 経由の両方を書くが、後者は data/common/tenants/<slug>/ になる。scoped_output_dir を正とし、テナント無しだけ data/common/_none/ にした
3. 案件の役割（閲覧・編集・承認）による認可は未実装。現状は認証済み・別人・合格の 3 条件のみ。stakeholders の形が C1 で決まってから足す
4. tests/test_common_decisions_api.py は所有パス外の新規作成（common_case の required_test_ids を実在させるため）
5. 取消は認証済みなら誰でも可（起票者・承認者に限定していない）

## 変更要求
### CR-C2-1
- 対象ファイル: web/__init__.py（共通）
- 要求: `from web.routes import common_decisions_api` と `app.register_blueprint(common_decisions_api.bp)` を追加
- 根拠: 契約 A2 §3.2。未登録のため /api/common/v1/cases/<cid>/decisions 等が 404
- 最小差分: import 1 行・登録 1 行（既存の削除・改名なし）
- 互換性: 無し（新しい接頭 /api/common/v1/ のみ）
- 依存先: C1 の cases（cases/<cid>.json）。C2 は保存先規約どおりのファイルの有無だけを見る
- 検証: tests/test_common_decisions_api.py 4 件、実サーバで POST decisions → approve → GET evidence
- 期限・優先度: 統合時（C1 と同時）
