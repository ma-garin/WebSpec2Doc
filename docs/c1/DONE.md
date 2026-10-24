# C1 共通サービス・共通 API v1 土台 — DONE（2026-10-24）

## 実装
- web/services/common/store.py（テナント解決・原子的書込み・Idempotency-Key・共通エラー）
- web/services/common/cases.py（案件 CRUD・rev 409・参照付け外し・逆引き索引 index/<type>.json）
- web/services/common/versions.py（対象版 tv の固定・207 部分成功・古さ判定）
- web/services/common/refs.py（ref 検証・型別の解決）
- web/routes/common_api.py（/api/common/v1 の 7 エンドポイント＋GET 一覧）
- web/__init__.py（Blueprint 登録。import 1 行＋register 1 行＋注釈 1 行）
- web/system_registry.py は変更不要のため未変更

## 通した経路（curl 実測。全量 docs/c1/curl-log.txt）
| 呼び出し | 結果 |
|---|---|
| POST cases 鍵なし | 400 bad_request |
| POST cases 鍵 k1 | 201・再送で同 id |
| GET cases / cases/<cid> | 200 |
| GET cases/<存在しない> | 404 not_found |
| PATCH rev=1 → 再 rev=1 | 200 → 409 conflict |
| POST refs 実在 2 件 | 201 |
| POST refs 不在・未対応型 | 404・400 |
| GET refs/resolve | 200（全 ok） |
| POST versions 実在＋不在 | 207（固定/失敗を分離） |
| GET versions/<tv> | 200 fresh=true |
| 参照先を更新後 resolve | 207 stale |
| 同 GET versions/<tv> | 200 fresh=false |
| DELETE refs → 再 DELETE | 200 → 404 |

- 経路: /api/common/v1/… → common_api.py → services/common/* → data/common/<t>/{cases,versions,idem,index}/ → 失敗時 {"schema":"common.error/1","error":{code,message,detail,retryable}}
- 解決は既存ローダを読むだけ: docverify store.load / doc_dir、run_store.run_exists、healing project_store.get_project、batchtest・backendtest store.job_dir/job.json、output/<domain>/report.json
- 解決済みの型: docverify.inspection/document/finding、site.domain/run、healing.project、batchtest.job、backendtest.job

## 移行試験（§5.2。全量 docs/c1/migration-log.txt。検証用ヘッダで g.tenant を差し込む試験スクリプト）
- 類型1 同名異テナント: t1・t2 に同名 inspection と example.com の run を作成。t1 から t2 の iid（tenant=t2 / tenant=t1 偽装）・_none の iid を参照 → いずれも 404。t2 から t1 の案件 → 404。一覧は自テナントのみ、_none に t1/t2 は出ない。同じ Idempotency-Key でもテナント別に作成。合格
- 類型3 欠けた参照: inspection フォルダと run の meta.json を mv で退避 → resolve 207・missing 2（current=null、0 件扱いにしない）。同状態で versions → 207・version=null。戻すと ok 2。合格
- 契約の「tests.json 退避 → s06/status」は s06 系が C1 範囲外のため、同じ判定を refs/resolve で確認した

## 未検証・未実装
- pytest・lint は未実行（禁止のため）
- 認証オン（実ログイン）での実行は未検証。テナントは試験用 before_request で g.tenant を設定して確認
- 案件の役割（閲覧・編集・承認）による認可は未実装（§3.1）
- 未対応型（docassure.analysis, ta2.test, ta.*, autorun.run, healing.run, impact.*, orchestration.run）は 400 で受け付けない
- audit.jsonl（§4.2）への証跡記録は未実装（C1 範囲外と判断）
- 並行書込みはプロセス内ロックのみ。複数プロセス間の排他は未対応

## 要判断
- 保存先: 契約は data/common/<t>/ だが「scoped_output_dir を通す」と矛盾する。後者に従い data/common/tenants/<t>/、テナント無しは data/common/_none/ にした
- docverify の inspection.json に rev キーが無い（save 後も None）。古さ判定は sha256 と mtime で行う。§1.2 の「inspection は rev」の前提と違う
- 想定外の例外は 500 で返し、code は語彙内の upstream_failed を流用した（語彙に internal が無い）
- POST refs は Idempotency-Key 不要（rev 必須で二重付けは 409）とした

## 変更要求
- なし
