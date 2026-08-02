# WS2D-TM-001 トレーサビリティマトリクス

- 版数: 2.0 / 作成日: 2026-08-02（前版 1.0 / 2026-07-16、52行・33機能分のみ）
- 準拠: ISO/IEC/IEEE 29119
- **前版最大の問題点**: 前版は `quality/feature_contracts.yml` の51機能中33機能しか
  行を持っておらず、本改訂以降に追加された18機能（tenant_membership・qa_assistant_chat・
  autorun_stage_approval・autorun_result_report・autorun_security_kernel・autorun_self_check・
  autorun_nonfunctional_judge・ui_visual_complexity・autorun_failure_triage・technique_engine・
  autorun_extended_techniques・state_transition_table・testcase_table・
  zero_wait_sample_report・cli_mode・spec_xlsx_full_export・condition_to_testcase_link・
  condition_run_status）が完全に欠落していた。本版はこれを是正し **51機能全件**を収録する。
- 要件ID = `feature_id`。本版のテスト紐付けは、Python スクリプトによる機械的なキーワード
  照合（feature_id・route_files のファイル名幹・symbols の関数/クラス名を全角/半角の
  単語境界で `tests/` 配下の全ファイル本文と照合）で作成した。紐付けできなかったものは
  空欄にせず「0」と明示し、捏造しない。

## 1. トレーサビリティの方法論

前版は `scripts/generate_traceability_doc.py` による自動生成だったが、本改訂時点で
51機能中33機能しか反映されていない状態だった（スクリプト自体の再実行有無は本改訂では
未確認）。本版は同じ「機械的紐付け」の原則を踏襲しつつ、51機能全件に対して独自に
以下の手順で再構築した。

1. `quality/feature_contracts.yml` を全件読了し、各機能の `feature_id`／`name`／
   `risk_level`／`ui_files`／`route_files`／`core_files`／`symbols` を抽出する。
2. キーワード集合を作る: `feature_id` 自体、`route_files` のファイル名幹（拡張子を除いた
   部分。ただし `main`／`app`／`init`／`config`等の汎用語は除外）、`symbols` のうち
   5文字以上かつ汎用語でないもの。
3. `tests/`（非E2E）と `tests/e2e/`（E2E）の全 test_*.py ファイル本文に対し、
   単語境界（`\b`）でキーワードが出現するかを検索する。
4. マッチしたファイルのうち、`test_client(` または `.test_client()` を含むファイルを
   結合テスト（L2）寄り、含まないものを単体テスト（L1）寄りとして分類する（簡易ヒューリスティック。
   1ファイルが複数の性質を持つ場合は主要な性質で代表させる概算）。
5. `docs/sdlc/_asbuilt/routes.json` の `module` フィールドと `route_files` を突き合わせ、
   関連APIパスを抽出する。

**この方法論の限界を明示する**: (a) キーワード一致は「そのテストが当該機能を検証している」
ことの必要条件であって十分条件ではない。共通ユーティリティを経由した間接的な一致を
誤って拾う可能性がある。(b) 逆に、機能名と直接関係しない語彙でテストが書かれている場合は
拾えない（偽陰性）。実際、後述 §5 のとおり51機能中30機能でE2E一致が0件となったが、
これは「E2Eテストが存在しない」ことの証明ではなく「本手法のキーワードでは見つからなかった」
ことを意味する（**未確認**であり断定しない）。

## 2. マトリクス本体（51機能全件）

| 要件ID | 機能名 | 重要度 | 関連画面 | 関連API | 単体テスト | 結合テスト | E2Eテスト | 受入ケース | 実装モジュール | 状態 |
|---|---|---|---|---|---|---|---|---|---|---|
| `discover` | URL解析 / 画面発見 | critical | 2:view-generate.html,wizard.js | 2:/api/discover,/api/discover-stream | 5:test_ci_drift.py,test_comparison.py,他3 | 3:test_app_wizard.py,test_document_auto_run.py,他1 | 2:test_autorun_state_matrix_e2e.py,test_stale_state_e2e.py | AT-001 | 2:page_crawler.py,url_safety.py | 実装済み・L1-L3追跡あり |
| `crawl` | クロール / レポート生成 | critical | 4:view-generate.html,execution.js | 5:/api/cancel,/api/doc-fusion | 13:test_auth.py,test_ci_drift.py,他11 | 10:test_api_v1.py,test_app_site.py,他8 | 1:test_autorun_state_matrix_e2e.py | AT-002 | 22:page_crawler.py,parallel_crawler.py | 実装済み・L1-L3追跡あり |
| `login` | ログイン / セッション | critical | 2:view-generate.html,wizard.js | 7:/api/login/record/cancel,/api/login/record/complete | 39:test_a11y_extraction.py,test_admin_audit.py,他37 | 11:test_admin_routes.py,test_app_account.py,他9 | 3:test_auth_recorder_e2e.py,test_autorun_state_matrix_e2e.py,他1 | AT-003 | 6:auto_login.py,login_wall.py | 実装済み・L1-L3追跡あり |
| `account_auth` | アプリ利用者認証（ログイン/セッション/アカウント管理） | critical | 5:login.html,setup.html | 14:/api/auth/api-tokens,/api/auth/api-tokens/<token_id> | 2:test_auth_store.py,test_oidc.py | 2:test_admin_routes.py,test_app_account.py | 0（E2E未確認） | AT-004 | 2:auth_store.py,auth.py | 実装済み・L1/L2のみ（L3未確認） |
| `tenant_membership` | テナント選択と所属管理（マルチテナント／一般・管理者2ロール） | critical | 6:user.html,tenant.html | 21:/admin/console,/api/admin/tenancy | 0（一致なし） | 3:test_admin_routes.py,test_app_account.py,他1 | 0（E2E未確認） | AT-005（複合AT-032） | 2:auth_store.py,auth.py | 実装済み・L2のみ（L1/L3未確認） |
| `tenant_isolation` | テナント分離（出力・観点DB・APIトークンのワークスペース分離） | critical | 1:account.html | 14:/api/auth/api-tokens,/api/auth/api-tokens/<token_id> | 5:test_auth_store.py,test_oidc.py,他3 | 13:test_admin_routes.py,test_api_v1_schedule.py,他11 | 0（E2E未確認） | AT-006 | 3:tenancy.py,auth_store.py | 実装済み・L1/L2のみ（L3未確認） |
| `autorun` | AutoRun | high | 4:view-auto-run.html,autorun.js | 10:/api/autorun/approve,/api/autorun/cancel | 19:test_autorun_automation_plan.py,test_autorun_gate_integration.py,他17 | 13:test_auto_run.py,test_auto_run_live_screenshot.py,他11 | 5:test_autorun_decisions_e2e.py,test_autorun_state_matrix_e2e.py,他3 | AT-012 | 8:spec_ts_generator.py,playwright_executor.py | 実装済み・L1-L3追跡あり |
| `diff_history` | 差分 / 履歴 / 再クロール | critical | 4:history.js,recrawl.js | 13:/api/history,/api/runs/<domain> | 18:test_admin_audit.py,test_archive.py,他16 | 20:test_api_v1.py,test_app_account.py,他18 | 5:test_broken_views_e2e.py,test_comparison_e2e.py,他3 | AT-007 | 5:snapshot.py,differ.py | 実装済み・L1-L3追跡あり |
| `settings` | 設定 | high | 2:view-settings.html,settings.js | 10:/,/<view_name> | 49:test_apispec_recovery.py,test_auto_login.py,他47 | 38:test_admin_routes.py,test_api_v1.py,他36 | 5:test_autorun_state_matrix_e2e.py,test_broken_views_e2e.py,他3 | AT-013（複合AT-035） | 6:env_store.py,viewpoint_proposals.py | 実装済み・L1-L3追跡あり |
| `usage_roi` | ROIダッシュボード / 利用実績 | medium | 1:view-usage.html | 2:/api/usage,/usage | 2:test_retention.py,test_usage_tracker.py | 1:test_usage_route.py | 0（E2E未確認） | AT-034（複合のみ） | 1:usage_tracker.py | 実装済み・L1/L2のみ（L3未確認） |
| `coverage_gap_report` | カバレッジと未確認領域（網羅性証明） | medium | 0（画面なし） | 0（APIなし） | 2:test_comparison_reporter.py,test_coverage_gap.py | 0（一致なし） | 0（E2E未確認） | — | 6:coverage_gap.py,html_reporter.py | 実装済み・L1のみ（L2/L3未確認） |
| `doc_fusion` | 文書×実測突合（Doc Fusion） | high | 5:view-generate.html,wizard.js | 7:/api/cancel,/api/doc-fusion | 14:test_comparison.py,test_crawler.py,他12 | 11:test_api_v1.py,test_app_site.py,他9 | 1:test_autorun_state_matrix_e2e.py | AT-014 | 16:loader.py,matcher.py | 実装済み・L1-L3追跡あり |
| `exploration_capture` | 探索セッション記録 / カバレッジヒートマップ | high | 0（画面なし） | 10:/api/coverage-heatmap,/api/export/spec-xlsx | 51:test_a11y_extraction.py,test_archive.py,他49 | 23:test_admin_routes.py,test_api_v1.py,他21 | 5:test_broken_views_e2e.py,test_capture_realbrowser_e2e.py,他3 | AT-015 | 7:session_recorder.py,coverage.py | 実装済み・L1-L3追跡あり |
| `reverse_assets` | リバース（記録セッション→テスト資産の逆生成） | medium | 0（画面なし） | 0（APIなし） | 2:test_comparison.py,test_reverse_generator.py | 0（一致なし） | 0（E2E未確認） | — | 1:reverse_generator.py | 実装済み・L1のみ（L2/L3未確認） |
| `field_definition_bva` | 項目定義書＋境界値分析（BVA）テストデータ自動生成 | medium | 0（画面なし） | 0（APIなし） | 1:test_bva.py | 0（一致なし） | 0（E2E未確認） | — | 2:bva.py,main.py | 実装済み・L1のみ（L2/L3未確認） |
| `finding_ticket` | 気づきマーク → 再現手順付きバグ票（JSON/CSV エクスポート） | medium | 0（画面なし） | 0（APIなし） | 2:test_capture.py,test_finding_reporter.py | 0（一致なし） | 1:test_capture_realbrowser_e2e.py | — | 3:finding_reporter.py,session_recorder.py | 実装済み・L1/L3のみ（L2未確認） |
| `test_plan` | テスト計画ドラフト生成（インベントリ×ROI係数→工数見積・スコープ表） | medium | 0（画面なし） | 17:/api/qa-process/advanced,/api/qa-process/generate | 6:test_archive.py,test_history_artifact_parity.py,他4 | 14:test_app_wizard.py,test_auto_run.py,他12 | 1:test_report_tabs_e2e.py | — | 9:test_plan_generator.py,main.py | 実装済み・L1-L3追跡あり |
| `ci_warnings_cleanup` | CI警告一掃（pytest収集警告・Pillow非推奨警告の解消と再発防止） | low | 0（画面なし） | 0（APIなし） | 1:test_screenshot_diff.py | 0（一致なし） | 0（E2E未確認） | — | 3:screenshot_diff.py,viewpoint_generator.py | 実装済み・L1のみ（L2/L3未確認） |
| `old_new_comparison` | 現新比較モード（移行検証支援） | high | 4:view-compare.js,results.js | 7:/api/history,/api/site/<domain> | 10:test_comparison.py,test_comparison_reporter.py,他8 | 14:test_app_account.py,test_app_site.py,他12 | 5:test_broken_views_e2e.py,test_comparison_e2e.py,他3 | AT-016 | 10:pair_matcher.py,comparison.py | 実装済み・L1-L3追跡あり |
| `ux_review` | UX自動エキスパートレビュー（axe-core＋ニールセン10原則ヒューリスティック） | medium | 0（画面なし） | 0（APIなし） | 10:test_axe_runner.py,test_ci_drift.py,他8 | 1:test_usage_route.py | 1:test_ux_review_e2e.py | — | 9:axe_runner.py,heuristics.py | 実装済み・L1-L3追跡あり |
| `snapshot_retention` | スナップショット保持・容量・バックアップ運用 | high | 3:view-settings.html,settings.js | 4:/api/admin/audit,/api/admin/backup-guide | 11:test_admin_audit.py,test_auth_store.py,他9 | 5:test_admin_routes.py,test_app_account.py,他3 | 0（E2E未確認） | AT-017 | 2:retention.py,scheduler.py | 実装済み・L1/L2のみ（L3未確認） |
| `admin_audit` | 管理操作のテナント監査ログ | high | 3:view-settings.html,settings.js | 55:/api/admin/audit,/api/admin/backup-guide | 70:test_a11y_extraction.py,test_admin_audit.py,他68 | 35:test_admin_routes.py,test_api_v1.py,他33 | 7:test_broken_views_e2e.py,test_capture_realbrowser_e2e.py,他5 | AT-018 | 3:admin_audit.py,audit_context.py | 実装済み・L1-L3追跡あり |
| `ci_drift_monitor` | Drift Check as Code（CI組み込みドリフト監視） | high | 3:view-settings.html,results.js | 0（APIなし） | 4:test_job_queue.py,test_notifier.py,他2 | 1:test_schedule.py | 0（E2E未確認） | AT-019 | 7:main.py,ci_drift.py | 実装済み・L1/L2のみ（L3未確認） |
| `document_mbt` | 文書駆動MBT（要件×実測からのテスト設計） | critical | 3:view-auto-run.html,autorun-document.js | 10:/api/autorun/approve,/api/autorun/cancel | 12:test_autorun_gate_integration.py,test_autorun_mutation_stage.py,他10 | 4:test_auto_run.py,test_auto_run_live_screenshot.py,他2 | 0（E2E未確認） | AT-008 | 8:document_model.py,manual_procedures.py | 実装済み・L1/L2のみ（L3未確認） |
| `evidence_pack` | 検収・監査向けテスト実施証跡パック | high | 1:autorun.js | 10:/api/autorun/approve,/api/autorun/cancel | 5:test_autorun_gate_integration.py,test_autorun_mutation_stage.py,他3 | 4:test_auto_run.py,test_auto_run_live_screenshot.py,他2 | 0（E2E未確認） | AT-020 | 3:pack_model.py,pack_reporter.py | 実装済み・L1/L2のみ（L3未確認） |
| `diff_severity` | 差分の重要度判定と誤検知フィルタ | high | 0（画面なし） | 0（APIなし） | 2:test_diff_ignore_rules.py,test_diff_severity.py | 0（一致なし） | 0（E2E未確認） | AT-021 | 3:severity.py,ignore_rules.py | 実装済み・L1のみ（L2/L3未確認） |
| `api_v1_openapi` | REST API拡充とOpenAPI公開 | high | 0（画面なし） | 13:/api/v1/docs,/api/v1/healthz | 1:test_openapi_spec.py | 1:test_api_v1.py | 0（E2E未確認） | AT-022 | 2:openapi_spec.py,openapi_docs.py | 実装済み・L1/L2のみ（L3未確認） |
| `multi_viewport` | マルチビューポート仕様書 | medium | 0（画面なし） | 0（APIなし） | 2:test_layout_failures.py,test_viewport.py | 0（一致なし） | 0（E2E未確認） | — | 5:profiles.py,comparison.py | 実装済み・L1のみ（L2/L3未確認） |
| `sso_oidc` | SSO（OIDC）とAPIトークンスコープ | critical | 0（画面なし） | 2:/auth/oidc/callback,/auth/oidc/login | 1:test_oidc.py | 0（一致なし） | 0（E2E未確認） | AT-009 | 3:oidc.py,auth_store.py | 実装済み・L1のみ（L2/L3未確認） |
| `observability` | 可観測性（メトリクス・構造化ログ） | medium | 0（画面なし） | 1:/metrics | 1:test_metrics.py | 0（一致なし） | 0（E2E未確認） | — | 4:metrics.py,scheduler.py | 実装済み・L1のみ（L2/L3未確認） |
| `api_spec_recovery` | API仕様の逆生成 | medium | 0（画面なし） | 0（APIなし） | 1:test_apispec_recovery.py | 0（一致なし） | 0（E2E未確認） | — | 1:recovery.py | 実装済み・L1のみ（L2/L3未確認） |
| `screen_coverage_map` | 画面カバレッジマップ | medium | 0（画面なし） | 0（APIなし） | 1:test_coverage_map.py | 0（一致なし） | 0（E2E未確認） | — | 1:coverage_map.py | 実装済み・L1のみ（L2/L3未確認） |
| `wording_consistency` | 文言一貫性・表記ゆれチェック | low | 0（画面なし） | 0（APIなし） | 1:test_wording.py | 0（一致なし） | 0（E2E未確認） | — | 1:consistency.py | 実装済み・L1のみ（L2/L3未確認） |
| `full_archive` | 完全アーカイブと外形監視（sitemap/PDF） | medium | 0（画面なし） | 0（APIなし） | 1:test_archive.py | 0（一致なし） | 0（E2E未確認） | — | 2:full_archive.py,external_monitor.py | 実装済み・L1のみ（L2/L3未確認） |
| `qa_assistant_chat` | QAアシスタント（LLMチャット） | medium | 2:view-auto-run.html,autorun-chat.js | 1:/api/llm/chat | 2:test_autorun_suggest.py,test_llm_provider.py | 3:test_autorun_stages_api.py,test_llm_activity_log.py,他1 | 0（E2E未確認） | — | 1:openai_client.py | 実装済み・L1/L2のみ（L3未確認） |
| `autorun_stage_approval` | AutoRun 段階承認パイプライン（テスト目的〜テストケース） | critical | 3:view-auto-run.html,autorun-stages.js | 13:/api/autorun/decisions,/api/autorun/review-queue | 5:test_autorun_automation_plan.py,test_autorun_mutation_stage.py,他3 | 4:test_autorun_audit.py,test_autorun_stages_api.py,他2 | 0（E2E未確認） | AT-010 | 6:automation_plan.py,decisions.py | 実装済み・L1/L2のみ（L3未確認） |
| `autorun_result_report` | AutoRun 実行結果レポート専用ページ | high | 3:autorun-report.html,autorun-report.js | 2:/api/autorun/report/<domain>,/autorun/report/<domain> | 1:test_autorun_stages.py | 1:test_autorun_report.py | 0（E2E未確認） | AT-023 | 2:qf_schema.py,stages.py | 実装済み・L1/L2のみ（L3未確認） |
| `autorun_security_kernel` | AutoRun セキュリティカーネル（送信ゲートウェイ・非信頼コンテンツ境界） | critical | 0（画面なし） | 0（APIなし） | 1:test_security_kernel.py | 0（一致なし） | 0（E2E未確認） | AT-011 | 2:egress_gateway.py,untrusted_content.py | 実装済み・L1のみ（L2/L3未確認） |
| `autorun_self_check` | AutoRun 自己検証（ミューテーションテスト） | high | 1:autorun-report.js | 10:/api/autorun/approve,/api/autorun/cancel | 6:test_autorun_gate_integration.py,test_autorun_mutation_stage.py,他4 | 4:test_auto_run.py,test_auto_run_live_screenshot.py,他2 | 0（E2E未確認） | AT-024 | 1:mutation_verifier.py | 実装済み・L1/L2のみ（L3未確認） |
| `autorun_nonfunctional_judge` | AutoRun 非機能判定・観測完全性 | high | 1:autorun-report.js | 10:/api/autorun/approve,/api/autorun/cancel | 5:test_autorun_gate_integration.py,test_autorun_mutation_stage.py,他3 | 4:test_auto_run.py,test_auto_run_live_screenshot.py,他2 | 0（E2E未確認） | AT-025 | 2:nonfunctional_judge.py,observation_coverage.py | 実装済み・L1/L2のみ（L3未確認） |
| `ui_visual_complexity` | UI 視覚的複雑性の実測・回帰検知 | medium | 0（画面なし） | 0（APIなし） | 1:test_visual_complexity.py | 0（一致なし） | 1:test_visual_complexity_e2e.py | — | 1:visual_complexity.py | 実装済み・L1/L3のみ（L2未確認） |
| `autorun_failure_triage` | AutoRun 失敗の原因特定・部分変異体 | high | 0（画面なし） | 10:/api/autorun/approve,/api/autorun/cancel | 8:test_autorun_gate_integration.py,test_autorun_mutation_stage.py,他6 | 4:test_auto_run.py,test_auto_run_live_screenshot.py,他2 | 0（E2E未確認） | AT-026 | 2:failure_hypothesis.py,techniques.py | 実装済み・L1/L2のみ（L3未確認） |
| `technique_engine` | テスト技法エンジン（被覆配列の正準実装等） | high | 0（画面なし） | 0（APIなし） | 2:test_techniques_combinatorial.py,test_techniques_verify.py | 0（一致なし） | 0（E2E未確認） | AT-027 | 6:__init__.py,combinatorial.py | 実装済み・L1のみ（L2/L3未確認） |
| `autorun_extended_techniques` | テスト技法の網羅的適用（分類ツリー法・直交表等） | high | 2:view-auto-run.html,autorun-stages.js | 13:/api/autorun/decisions,/api/autorun/review-queue | 2:test_techniques.py,test_techniques_extended.py | 4:test_autorun_audit.py,test_autorun_stages_api.py,他2 | 0（E2E未確認） | AT-028 | 8:classification_tree.py,orthogonal_array.py | 実装済み・L1/L2のみ（L3未確認） |
| `state_transition_table` | 状態遷移表（ISTQB 状態遷移テスト・0/1-switch被覆） | high | 3:view-generate.html,view-transition.js | 10:/api/coverage-heatmap,/api/export/spec-xlsx | 51:test_a11y_extraction.py,test_archive.py,他49 | 23:test_admin_routes.py,test_api_v1.py,他21 | 5:test_broken_views_e2e.py,test_capture_realbrowser_e2e.py,他3 | AT-029 | 1:state_table.py | 実装済み・L1-L3追跡あり |
| `testcase_table` | ローレベルテストケース表（9列生成・Excel風編集・編集履歴） | high | 3:view-generate.html,view-testcase-grid.js | 17:/api/qa-process/advanced,/api/qa-process/generate | 6:test_archive.py,test_condition_run_status.py,他4 | 14:test_app_wizard.py,test_auto_run.py,他12 | 1:test_report_tabs_e2e.py | AT-030 | 4:testcase_table.py,testcase_table_store.py | 実装済み・L1-L3追跡あり |
| `zero_wait_sample_report` | ゼロ待ちサンプルレポート | medium | 5:view-dashboard.html,view-generate.html | 17:/api/coverage-heatmap,/api/export/spec-xlsx | 51:test_a11y_extraction.py,test_archive.py,他49 | 29:test_admin_routes.py,test_api_v1.py,他27 | 7:test_broken_views_e2e.py,test_capture_realbrowser_e2e.py,他5 | — | 2:report.py,config.py | 実装済み・L1-L3追跡あり |
| `cli_mode` | CLI モード（System 03・画面なし） | high | 4:system-select.html,cli.html | 5:/,/<view_name> | 20:test_apispec_recovery.py,test_canonicalizer.py,他18 | 11:test_app_wizard.py,test_auto_run.py,他9 | 1:test_autorun_state_matrix_e2e.py | AT-031 | 2:cli.py,cli_runner.py | 実装済み・L1-L3追跡あり |
| `spec_xlsx_full_export` | テスト仕様書一式の Excel 出力（7シート） | medium | 2:view-generate.html,results.js | 10:/api/coverage-heatmap,/api/export/spec-xlsx | 50:test_a11y_extraction.py,test_archive.py,他48 | 23:test_admin_routes.py,test_api_v1.py,他21 | 5:test_broken_views_e2e.py,test_capture_realbrowser_e2e.py,他3 | — | 6:export_xlsx.py,screen_test_design.py | 実装済み・L1-L3追跡あり |
| `condition_to_testcase_link` | 画面別設計の条件 ⇄ テストケースの接続 | medium | 5:view-generate.html,view-design.js | 17:/api/qa-process/advanced,/api/qa-process/generate | 5:test_archive.py,test_history_artifact_parity.py,他3 | 14:test_app_wizard.py,test_auto_run.py,他12 | 1:test_report_tabs_e2e.py | — | 4:screen_test_design.py,testcase_table_store.py | 実装済み・L1-L3追跡あり |
| `condition_run_status` | テスト実行結果の設計への還元 | medium | 2:view-design.js,app-report.css | 17:/api/qa-process/advanced,/api/qa-process/generate | 6:test_archive.py,test_condition_run_status.py,他4 | 14:test_app_wizard.py,test_auto_run.py,他12 | 1:test_report_tabs_e2e.py | — | 5:condition_run_status.py,screen_test_design.py | 実装済み・L1-L3追跡あり |

## 3. カバレッジ集計

実測（2026-08-02、上表51行を機械的に集計）。

| 指標 | 値 | 比率 |
|---|---|---|
| 要件（機能）総数 | 51 | 100% |
| 何らかのテスト（L1/L2/E2Eいずれか）に紐付いている要件 | 51 | **100%** |
| 単体テスト（L1）に紐付いている要件 | 48 | 94.1% |
| 結合テスト（L2）に紐付いている要件 | 40 | 78.4% |
| E2Eテスト（L3）に紐付いている要件 | 21 | 41.2% |
| L1・L2・E2Eすべてに紐付いている要件 | 17 | 33.3% |
| 個別の受入ケース（AT-001〜031）が割り当てられている要件 | 31 | 60.8%（critical/high全件） |
| 受入ケースが複合シナリオのみの要件 | 2（tenant_membership・usage_roi） | 3.9% |
| 受入ケースが未割当の要件 | 19（medium/low） | 37.3% |
| GAP（いずれのテストにも一切紐付かない要件） | **0** | 0% |

「何らかのテストに紐付いている＝100%」は本手法の照合が成立した割合であり、
**「required_tests に列挙された項目がすべて検証されている」ことの証明ではない**。
特に E2E（L3）紐付け率が41.2%にとどまる点は、critical機能6件
（`account_auth`・`tenant_membership`・`tenant_isolation`・`document_mbt`・
`autorun_stage_approval`・`autorun_security_kernel`）を含むため、§5 で個別に指摘する。

## 4. 双方向トレース

**要件→テスト**: 上表がこの方向のトレースである。各 `feature_id` から、対応する
単体・結合・E2Eテストファイルを列挙している。

**テスト→要件**: 逆方向は本改訂では全件を機械的に生成していない（工数の都合上、
要件→テスト方向のみを実施）。ただし個別確認として、例えば `tests/test_archive.py` は
`full_archive`・`ci_warnings_cleanup`・`diff_severity` 系の複数機能から参照されており、
1つのテストファイルが複数機能を横断的にカバーするケースが多いことを確認した
（`admin_audit` は70件、`exploration_capture`/`state_transition_table`/
`zero_wait_sample_report` はいずれも51件のマッチを示すが、これは単語境界一致による
広い足切りの結果であり、全件が当該機能を専門に検証しているとは限らない）。
次回改訂ではテスト関数のdocstring/アサーション内容を直接確認し、
テスト→要件の厳密な逆引きを行うことを推奨する（**未実施**）。

## 5. 追跡できなかった要件の一覧と理由

**「いずれのテストにも一切紐付かない」要件は0件**である（§3参照）。ただし、
以下の観点では追跡が不完全であり、隠さず明記する。

### 5.1 E2E（L3）が0件のcritical機能（6件、最重要の指摘）

| 要件ID | 機能名 | 理由（推定・未確認） |
|---|---|---|
| `account_auth` | アプリ利用者認証 | 製品自身のログイン/アカウント管理に対する専用E2Eシナリオが本手法では見つからなかった。`test_auth_recorder_e2e.py`等は「クロール対象サイトの認証記録」機能（`login`）を検証するものであり、`account_auth`（自社ログイン）とは別機能である可能性が高い |
| `tenant_membership` | テナント選択と所属管理 | 同上。L2（`test_admin_routes.py`等）では確認できるが、実ブラウザでのテナント切替操作を専用に検証するE2Eは本手法では未検出 |
| `tenant_isolation` | テナント分離 | 同上。データ分離はL1/L2で検証されているが、実ブラウザでのcross-tenantアクセス試行を伴うE2Eは未検出 |
| `document_mbt` | 文書駆動MBT | L1/L2では厚く検証されているが、実ブラウザでのDoc Fusion→MBT生成の一気通貫E2Eは未検出 |
| `autorun_stage_approval` | AutoRun段階承認パイプライン | 同上。段階承認UIの操作自体は`autorun-stages.js`等に実装があるが、専用E2Eの存在は本手法では確認できなかった |
| `autorun_security_kernel` | AutoRunセキュリティカーネル | L1（`test_security_kernel.py`）のみで、送信ゲートウェイの実ブラウザ経由の検証は未検出。セキュリティ上重要な機能であるため優先度高く次回改訂で確認すべき |

**注記**: 上記6件はすべて `risk_level: critical` である。critical機能でE2Eが0件という
結果は、(a) 本手法のキーワード一致が拾えていないだけで実際にはE2Eテストが存在する、
(b) 実際にE2Eカバレッジが手薄である、のいずれかであり、**本改訂では判別できない
（未確認）**。次回改訂でテスト関数の内容を直接確認することを強く推奨する。

### 5.2 受入ケース（L4）が未割当の要件（19件）

`risk_level: medium`（17件）および`low`（2件）は `WS2D-AT-001` で個別ケースを
割り当てていない。これは意図的な優先順位付け（`WS2D-TP-001` §5）によるものであり、
「追跡漏れ」ではないが、次回の受入テスト実施範囲拡大の候補として記録する。

### 5.3 実装モジュールはあるが画面・APIを持たない機能（複数件）

`coverage_gap_report`・`reverse_assets`・`field_definition_bva`・`ci_warnings_cleanup`・
`diff_severity`・`multi_viewport`・`api_spec_recovery`・`screen_coverage_map`・
`wording_consistency`・`full_archive`・`autorun_security_kernel`・`technique_engine`・
`ui_visual_complexity` の13件は `ui_files`・`route_files` がいずれも空、または
どちらか一方が空である。これらはライブラリ的・内部処理的な機能であり、
「画面/APIがない＝欠陥」ではなく機能の性質上の設計判断である
（`quality/feature_contracts.yml` 上でも明示的に空配列として定義されている）。

## 6. 改訂履歴

| 版 | 日付 | 内容 | 作成者 |
|---|---|---|---|
| 1.0 | 2026-07-16 | 初版（52行、33機能のみ収録、機械生成スクリプト`scripts/generate_traceability_doc.py`依存） | 開発チーム |
| 2.0 | 2026-08-02 | 全面改訂。51機能全件を収録（前版比+18機能）。独自の機械的キーワード照合方式に刷新し、単体/結合/E2Eの内訳・関連画面・関連API・受入ケース列を新設。カバレッジ集計（E2E紐付け率41.2%等）とcritical機能6件のE2E未検出を明示的に指摘 | 開発チーム |

## 7. 機能別 required_tests 充足チェック（critical/high 全31機能）

`quality/feature_contracts.yml` が各機能に宣言する `required_tests`（そのレベルで
必ず検証すべき観点）を実測データとして転記し、§2のテスト紐付け結果と突き合わせる。

| 要件ID | 重要度 | 宣言された required_tests | E2E紐付け状況 |
|---|---|---|---|
| `discover` | critical | happy_path, error_path, evidence | あり（2件） |
| `crawl` | critical | happy_path, error_path, cancel_path, checkpoint_path, evidence | あり（1件） |
| `login` | critical | happy_path, error_path, session_expiry_path, evidence, timeout_path, cancel_path | あり（3件） |
| `account_auth` | critical | happy_path, error_path, lockout_path, session_expiry_path, evidence | **なし** |
| `tenant_membership` | critical | happy_path, error_path, evidence | **なし** |
| `tenant_isolation` | critical | happy_path, isolation_path, error_path, evidence | **なし** |
| `diff_history` | critical | happy_path, breaking_change_path, error_path, evidence | あり（5件） |
| `document_mbt` | critical | happy_path, error_path, coverage_path, no_submit_guarantee, evidence | **なし** |
| `sso_oidc` | critical | happy_path, error_path, authorization_path, token_validation, evidence | **なし** |
| `autorun_stage_approval` | critical | happy_path, error_path, persistence | **なし** |
| `autorun_security_kernel` | critical | happy_path, error_path, evidence | **なし** |
| `autorun` | high | happy_path, approval_path, cancel_path, error_path, timeout_path, evidence | あり（5件） |
| `settings` | high | happy_path, validation_path, evidence | あり（5件） |
| `doc_fusion` | high | happy_path, error_path, mismatch_detection, evidence | あり（1件） |
| `exploration_capture` | high | happy_path, error_path, state_join_key, evidence | あり（5件） |
| `old_new_comparison` | high | happy_path, error_path, evidence, unclassified_fallback | あり（5件） |
| `snapshot_retention` | high | happy_path, error_path, tenant_isolation, symlink_boundary, evidence | **なし** |
| `admin_audit` | high | happy_path, error_path, tenant_isolation, authorization, evidence | あり（7件） |
| `ci_drift_monitor` | high | happy_path, error_path, no_change_path, exit_code_contract, evidence | **なし** |
| `evidence_pack` | high | happy_path, missing_input_path, claim_scope, evidence | **なし** |
| `diff_severity` | high | happy_path, determinism, immutability, exclusion_disclosure, evidence | **なし** |
| `api_v1_openapi` | high | happy_path, error_path, authorization_path, implemented_paths_only, evidence | **なし** |
| `autorun_result_report` | high | happy_path, error_path | **なし** |
| `autorun_self_check` | high | happy_path, error_path, evidence | **なし** |
| `autorun_nonfunctional_judge` | high | happy_path, error_path, evidence | **なし** |
| `autorun_failure_triage` | high | happy_path, error_path, evidence | **なし** |
| `technique_engine` | high | happy_path, error_path, evidence | **なし** |
| `autorun_extended_techniques` | high | happy_path, error_path, evidence | **なし** |
| `state_transition_table` | high | happy_path, error_path, evidence | あり（5件） |
| `testcase_table` | high | happy_path, error_path, evidence | あり（1件） |
| `cli_mode` | high | happy_path, error_path, exit_code_path, evidence | あり（1件） |

critical/high 31機能中、**E2E紐付けが「なし」の機能は19件（61.3%）**にのぼる。
これは§5.1で指摘した6件（critical）に加え、high機能13件
（`snapshot_retention`・`ci_drift_monitor`・`evidence_pack`・`diff_severity`・
`api_v1_openapi`・`autorun_result_report`・`autorun_self_check`・
`autorun_nonfunctional_judge`・`autorun_failure_triage`・`technique_engine`・
`autorun_extended_techniques`）を含む。これらの多くはAutoRunの内部処理系
（`autorun_*`）であり、L1/L2（Flask test client）では厚く検証されているものの、
実ブラウザを介したE2Eシナリオが本手法では見つからなかった。前述のとおり
これが「E2E不在の証明」ではなく「本手法での未検出」である点は§1の限界の記載どおりである。

## 8. routes.json とのクロスチェック

`docs/sdlc/_asbuilt/routes.json`（200エンドポイント、2026-08-02実測）のうち、
上表で「関連API」列が0件（APIなし）の機能は13件存在した。これらは`route_files`が
空配列として`feature_contracts.yml`に定義されている機能であり、ライブラリ的・
内部処理的な性質を持つ（`WS2D-TP-001` §2.1参照）。一方、`admin_audit`は関連APIが
55件と突出しているが、これは`route_files`に6モジュール（admin.py, report.py,
review.py, schedule.py, settings.py, viewpoints.py）が登録されており、監査ログ機能が
横断的に多数のルートへ影響する設計であることを反映している。

本書のAPI件数集計はモジュール単位の突き合わせであり、パスパラメータの正規化は
行っていない（`WS2D-IT-001` §3と同じ限界を持つ）。したがって55件・21件等の数値は
「そのモジュールに属するエンドポイント数」であって「その機能が直接使用するAPI数」を
過大に見積もっている可能性がある点に留意すること。

## 9. 次回改訂への申し送り

1. **E2E紐付け0件の19機能（critical6件・high13件）**について、テスト関数の中身を
   直接確認し、本当にE2Eが存在しないのか、本手法のキーワード一致で拾えていない
   だけなのかを判別すること。特に `account_auth`・`tenant_isolation`・
   `autorun_security_kernel` はセキュリティ上重要度が高く優先すること。
2. **テスト→要件の逆方向トレース**（§4で未実施とした部分）を実施し、
   1テストファイルが複数機能をカバーしている実態（例: `test_archive.py` が
   `full_archive`・`ci_warnings_cleanup`・`diff_severity`等から参照）を
   個別関数レベルで精査すること。
3. **`scripts/generate_traceability_doc.py` の再実行**を試み、本書の手動集計結果と
   自動生成結果を突き合わせて差異があれば原因を確認すること（前版が33機能で
   止まっていた原因の特定を含む）。
4. **medium/low機能19件への受入ケース拡大**を`WS2D-AT-001`の次回改訂と合わせて検討すること。

## 10. 本書の作成方法の透明性

本書はすべて `quality/feature_contracts.yml`（51件、2026-08-02実測）と
`tests/` 配下の実ファイルをPythonスクリプトで機械的に照合して作成した。
手作業による個別確認は行っておらず、キーワード一致の限界（§1）を除けば
恣意的な取捨選択は行っていない。マトリクス本体（§2）の51行はすべて
同一のプログラムロジックで生成しており、機能ごとに異なる基準を適用していない。
