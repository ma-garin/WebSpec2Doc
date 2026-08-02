# WS2D-AT-001 受入テスト仕様書（UAT / L4）

- 版数: 2.0 / 作成日: 2026-08-02（前版 1.0 / 2026-07-16、38行）
- 準拠: ISTQB Foundation Level Syllabus v4.0（受入テスト）、ISO/IEC/IEEE 29119-3
- 関連: 基本 UAT シナリオ（UAT-01〜07）は `docs/TESTING_STRATEGY.md` §4 を正とする。
  本書はそれを補完し、`quality/feature_contracts.yml` の `risk_level: critical/high`
  全 31 機能を機械的に洗い出して受入ケース化したものである。
- **実施結果は捏造しない**: 下表「判定」欄はすべて「未実施」とする。実利用者が実施した
  時点で結果（合格/不合格/気づき）を記入すること。本書の作成時点では一切の実施を行っていない。

## 1. 受入の目的と判定基準

受入テスト（L4）の目的は、`docs/TESTING_STRATEGY.md` が定める「L1+L2（コードが壊れていない）」
「L3（ブラウザで動く）」だけでは証明できない「**利用者が実際に価値を受け取れる**」ことを
確認することにある（`docs/DEFINITION_OF_DONE.md` の原則）。

判定基準は次の3点をすべて満たすこととする。

1. 対象シナリオを、初見・マニュアルなしの前提で実施し、迷いなく完了できること
   （`docs/TESTING_STRATEGY.md` が定めるペルソナ: ISTQB FL 取得済みジュニアテスト担当者）。
2. 期待結果と実際の挙動が一致すること。一致しない場合は `WS2D-DL-001` の起票プロセスに
   従って不具合として記録し、本書の判定を「不合格」とする。
3. `WS2D-TP-001` §8.2 の出口基準（L1+L2 green・L3 green・critical/high 指摘ゼロ）を
   本受入の前提条件として満たしていること。

## 2. 受入テストケース一覧

`quality/feature_contracts.yml` の `risk_level: critical`（11件）・`risk_level: high`（20件）
の全 31 機能を対象に、各1ケース以上を割り当てた。加えて複数機能にまたがる複合シナリオを
4 件追加し、合計 **35 ケース**とする（最低基準の 25 ケースを上回る）。

### 2.1 critical 機能（11件、AT-001〜AT-011）

| ケースID | 要件ID | シナリオ | 前提条件 | 手順 | 期待結果 | 判定 |
|---|---|---|---|---|---|---|
| AT-001 | discover | URL解析による画面発見 | 対象URLが到達可能で、ローカル/プライベートURL許可設定がある場合は `WEBSPEC2DOC_ALLOW_LOCAL=1` | ダッシュボードでURLを入力し「発見」を実行、候補画面一覧を確認する | 候補画面が一覧表示される。無効なURL・タイムアウト・ログイン壁検出時は分かりやすい日本語のエラー/状態表示が出る | 未実施 |
| AT-002 | crawl | クロールとレポート生成 | discover完了済み | 「クロール開始」を実行し、進捗表示を確認後、完了したreport.htmlを開く | report.html/report.json/スクリーンショットが生成される。キャンセル操作・タイムアウト発生時も途中結果（チェックポイント）が保持される | 未実施 |
| AT-003 | login | 認証つきサイトの解析 | ログイン壁のあるテスト対象サイトを用意する | ログイン検出後、GUIで認証情報を入力し記録、再クロールを実行する | 認証後ページが解析対象に含まれる。入力したパスワードは `auth.json` 等に平文保存されない | 未実施 |
| AT-004 | account_auth | アカウント認証とロックアウト | 初期セットアップ未実施の環境 | `/auth/setup` で初期作成→ログアウト→誤ったパスワードで5回連続ログイン試行→正しいパスワードで再試行 | 5回失敗後に一定時間ロックアウトされ、正しいパスワードでも一時的に拒否される。ロック解除後は正常にログインできる | 未実施 |
| AT-005 | tenant_membership | テナント選択とロール管理 | 複数テナントに所属するユーザーアカウント | テナント選択画面で切替→管理者コンソールでメンバーの招待・ロール変更を行う | 選択したテナントのワークスペースに切り替わり、一般/管理者ロールに応じて操作可否が画面に反映される | 未実施 |
| AT-006 | tenant_isolation | テナント間データ分離 | テナントA・Bが存在し、それぞれでクロール実施済み | テナントAで生成した出力をテナントBのセッションから参照試行、他テナントのAPIトークンでアクセス試行 | テナントBからテナントAの出力・観点DBへアクセスできない。他テナントのAPIトークンでのアクセスは拒否される | 未実施 |
| AT-007 | diff_history | 再クロールによる差分検知 | 一度クロール済みのサイトが登録済み | 対象サイトを再クロールし、履歴画面で前回との差分比較を確認する | 前回比の仕様ドリフトが diff_report.html に提示され、比較元/比較先のスナップショット日時が明示される | 未実施 |
| AT-008 | document_mbt | 文書駆動MBTによるテスト設計生成 | 要件定義書等の参照文書をアップロード済み | AutoRunでDoc Fusion経由の文書を投入し、MBT生成を実行、生成物（テストデータ・検証観測・ペアワイズケース）を確認する | 要件と実測から test_data／validation_observations／pairwise_cases が生成され、未マッチ要件がある場合はその旨が明示される | 未実施 |
| AT-009 | sso_oidc | SSO（OIDC）ログイン | OIDCプロバイダ設定済みの環境 | `/auth/oidc/login` からIdP認証へ遷移し、コールバックを確認する | 正規ログイン時はセッションが確立する。state/issuer/audience/nonce不一致時は明確に拒否される | 未実施 |
| AT-010 | autorun_stage_approval | AutoRun段階承認パイプライン | URL投入済みでAutoRunを開始できる状態 | 目的→計画→観点→設計→詳細→ケースの各段階で承認操作を行う | 各段階で承認待ちUIが明示され、未承認のまま次段階へ自動的に進まない | 未実施 |
| AT-011 | autorun_security_kernel | AutoRunセキュリティカーネル | AutoRun実行中でLLM呼び出し等の外部送信を伴う操作がある | 外部送信を伴う操作を実行し、`egress_log.ndjson` を確認する | SSRF/DNSリバインディング等の試行が拒否され、秘密情報がログ上で秘匿化（redact）される | 未実施 |

### 2.2 high 機能（20件、AT-012〜AT-031）

| ケースID | 要件ID | シナリオ | 前提条件 | 手順 | 期待結果 | 判定 |
|---|---|---|---|---|---|---|
| AT-012 | autorun | AutoRun全自動実行 | URL投入済み | 承認操作を経てテスト実行を行い、結果を確認する | 実行結果がテストケース単位でPASS/FAILとして提示される | 未実施 |
| AT-013 | settings | 設定変更と観点適用 | 設定画面にアクセス可能 | 環境設定値を変更・保存し、観点テンプレートを適用する | 不正な値は拒否され、正常値は`.env`に反映される。適用した観点がテスト設計に反映される | 未実施 |
| AT-014 | doc_fusion | 文書×実測突合 | 参照文書をアップロード済み | crawl実行後にDoc Fusionを実行し、doc_fusion.mdを確認する | 文書記載のルールと実測の不一致が検出される。幻覚（根拠のない引用）は除外される | 未実施 |
| AT-015 | exploration_capture | 探索セッション記録 | 実ブラウザでの操作記録機能を起動できる | 画面を操作しながらセッションを記録し、カバレッジヒートマップを確認する | 操作がセッションとして記録され、ヒートマップの分子に反映される | 未実施 |
| AT-016 | old_new_comparison | 現新比較モード | 新旧2つのサイトURLが用意されている | 比較モードを実行し、comparison.htmlを確認する | スクリーンショット差分・リンク切れが提示され、誤検知として除外した項目の内訳が開示される | 未実施 |
| AT-017 | snapshot_retention | スナップショット保持・容量管理 | 複数回クロール済みでスナップショットが蓄積している | 保持ポリシーを設定し、古いスナップショットの自動削除とストレージ使用量表示を確認する | ポリシーどおりに世代管理される。シンボリックリンクを用いた領域外アクセスは拒否される | 未実施 |
| AT-018 | admin_audit | 管理操作の監査ログ | 管理者権限を持つユーザー | 設定変更等の管理操作を実施し、監査ログ画面で確認する | 操作が`admin_audit.jsonl`に記録され、秘密情報はマスクされた状態で表示される | 未実施 |
| AT-019 | ci_drift_monitor | CI組み込みドリフト監視 | GitHub Actions（spec-drift.yml）設定済み | ワークフローを手動トリガし、drift_summary.jsonとSlack通知を確認する | 差分検知時に通知が送られ、無変更時は正常終了（no_change_path）する | 未実施 |
| AT-020 | evidence_pack | 証跡パック生成 | AutoRun実行が完了している | 証跡パック生成操作を行い、evidence_pack.htmlを確認する | 実施証跡が、主張できる範囲（claim_scope）を明示した形で生成される | 未実施 |
| AT-021 | diff_severity | 差分の重要度判定 | 差分のあるクロール結果が存在する | diff_report.htmlで重要度別内訳を確認し、除外ルールを設定して再判定する | 同一入力から同一出力となる決定的な重要度判定が行われ、除外内訳が開示される | 未実施 |
| AT-022 | api_v1_openapi | REST API v1とOpenAPI公開 | APIトークンが発行済み | `/api/v1/docs`にアクセスし、エンドポイントを実行、権限外操作を試行する | OpenAPI仕様が閲覧でき、非admin権限での操作は適切に拒否される | 未実施 |
| AT-023 | autorun_result_report | AutoRun実行結果レポート専用ページ | AutoRun実行が完了している | 「テスト実行レポートを見る」を押下する | ダッシュボード・計画・設計・ケース・実行結果が専用ページで一気通貫に閲覧できる | 未実施 |
| AT-024 | autorun_self_check | AutoRun自己検証（ミューテーションテスト） | テストケースが生成済み | 自己検証を実行し、mutation_verification.jsonを確認する | 弱いテスト（欠陥を検出できないテスト）の一覧が提示される | 未実施 |
| AT-025 | autorun_nonfunctional_judge | AutoRun非機能判定 | 基準線となる過去の測定データが存在する | 非機能判定を実行し、nonfunctional_judgement.jsonを確認する | 基準線比の合否と、観測できなかった領域が明示される | 未実施 |
| AT-026 | autorun_failure_triage | AutoRun失敗の原因特定 | テスト失敗が発生している | 失敗トリアージを実行し、failure_hypotheses.jsonを確認する | 原因候補が提示され、説明できない失敗はその旨が明示される（原因の断定はしない） | 未実施 |
| AT-027 | technique_engine | テスト技法エンジン（被覆配列） | 複数因子を持つ設定項目が存在する | ペアワイズケースを生成し、被覆率レポートを確認する | 決定的な被覆配列（同一入力から同一出力）が生成され、被覆不能な組合せが列挙される | 未実施 |
| AT-028 | autorun_extended_techniques | テスト技法の網羅的適用 | AutoRun設計段階に到達している | 分類ツリー・直交表・原因結果グラフの生成結果を確認する | 各技法の適用結果が表示され、直交表には直交性検査結果が付与される | 未実施 |
| AT-029 | state_transition_table | 状態遷移表生成 | crawlが完了している | 遷移図タブから状態遷移表を確認する | 0-switch/1-switchテストパスと無効遷移ケースが提示される | 未実施 |
| AT-030 | testcase_table | ローレベルテストケース表の編集 | テストケースが生成済み | セルを編集し、編集履歴を確認、Playwrightコードを生成して実行する | 編集履歴（変更前後の値）が保持され、生成された`testcases.spec.ts`が実行できる | 未実施 |
| AT-031 | cli_mode | CLIモードでの実行 | ターミナルからアクセス可能 | `python -m src.cli autorun <url>` を実行し、終了コードを確認する | `--json`指定時に機械可読な結果が得られ、終了コード（0/1/2/130）が状況に応じて意味を持つ | 未実施 |

### 2.3 複合シナリオ（4件、AT-032〜AT-035）

複数機能・非機能を横断する実利用シナリオを追加する。前版（1.0）の UAT-8〜12 の一部を
引き継ぎつつ、対象を本改訂の 51 機能構成に合わせて更新した。

| ケースID | 対象 | シナリオ | 前提条件 | 手順 | 期待結果 | 判定 |
|---|---|---|---|---|---|---|
| AT-032 | tenant_membership + tenant_isolation | マルチテナント総合シナリオ | 複数テナント・複数ロールのユーザーが存在 | ログイン→テナント選択→システム選択→データ操作→別テナントへの切替を通しで行う | 遷移順序が「ログイン→テナント選択→システム選択」で一貫し、テナントをまたいだデータ漏洩がない | 未実施 |
| AT-033 | 横断（画面表示・アクセシビリティ） | ダークモード全画面巡回 | ダークモード設定が可能 | 全ビューをダークモードで巡回する | 表示崩れ・低コントラストがなく、コンソールエラーが発生しない | 未実施 |
| AT-034 | usage_roi | ROIダッシュボード確認 | 利用実績ログ（usage_log.jsonl）が存在 | ROIダッシュボードを開き、推定削減工数を確認する | 推定値であることが明示された上で削減工数が表示される。ログが空の場合は空状態が適切に表示される | 未実施 |
| AT-035 | settings + TV-001観点管理 | 観点管理からテスト設計への反映 | 観点管理ビューにアクセス可能 | 観点を追加・編集し、テンプレートを適用して生成テスト設計に反映されるか確認する | 追加した観点が版管理された状態で保持され、生成される観点カテゴリ表（`WS2D-TV-001`）に反映される | 未実施 |

## 3. 受入環境

| 項目 | 内容 |
|---|---|
| 実行方法 | ローカル環境（`FLASK_TESTING=1 WEBSPEC2DOC_ALLOW_LOCAL=1 python app.py`） |
| 認証系ケース | `WEBSPEC2DOC_AUTH_MODE` を該当モードに設定して実施（AT-004/005/006/009/018） |
| ブラウザ | Chromium（推奨）。1280×800・1366×768・1920×1080 の3解像度で確認する |
| CLIケース | ターミナルから直接実行（AT-031） |
| 外部連携ケース | OIDCプロバイダのテスト用テナント、OpenAIまたはスタブ環境（AT-009/014/022） |
| データ | 実データではなく検証用に作成したサイト・テナント・アカウントを使用する |

## 4. 受入体制と役割

| 役割 | 担当 | 責務 |
|---|---|---|
| 受入実施者 | 配布先ユーザーまたはプロダクトオーナー（開発者本人が代行する場合を含む） | 各ケースの手順実施・結果記録・気づきのメモ |
| 受入判定者 | プロダクトオーナー | §5 の合格基準に基づく最終合否判断 |
| 不具合対応窓口 | 開発チーム | 不合格ケースの `WS2D-DL-001` への起票・修正・再検証 |
| 証跡管理 | 受入実施者 | 各ケースのスクリーンショットを保存し、判定欄と紐付ける |

## 5. 合格基準

本書は「全件合格」を原則としつつ、`risk_level` に応じた許容度を設ける。

| risk_level | 許容基準 |
|---|---|
| critical（AT-001〜011） | **全件合格が必須**。1件でも不合格の場合はリリース不可とする |
| high（AT-012〜031） | 原則全件合格。回避策があり `WS2D-DL-001` のPriority P3相当と判断できる不具合が
  1〜2件に限り、プロダクトオーナー承認のもとで条件付き合格とすることを許容する |
| 複合シナリオ（AT-032〜035） | 全件合格を目標とするが、個別ケース（AT-001〜031）側で
  既に検証済みの内容と重複するため、必須条件からは除外可能とする |

条件付き合格を選択した場合、残存する不具合と回避策を `WS2D-TR-001` の
「残存リスクと既知の制限」に必ず転記すること。

## 6. 不合格時の対応フロー

```
ケース実施 → 期待結果と不一致 → WS2D-DL-001 へ起票（事象・重要度一次判定）
   → 開発チームが原因分析（5 Whys 等の named framework、functional-integrity.md 準拠）
   → 修正 → 該当ケースを再実施 → 合格したら判定を更新
   → critical ケースが再度不合格の場合、リリースを見送り §5 の基準を満たすまで繰り返す
```

不合格の記録は本書の「判定」欄を直接書き換えるのではなく、`WS2D-DL-001` の実績台帳に
起票した上で、本書には最終的な再実施結果（合格/条件付き合格）のみを反映する。
これにより、不合格の経緯を捏造・隠蔽せず追跡可能な状態に保つ。

## 7. 受入スケジュール

本プロジェクトはチケット工数管理を行っていないため（`WS2D-TP-001` §10 参照）、
受入テストは「実装が落ち着いた区切り（マイルストーン）ごと」に実施する運用とする。

| タイミング | 実施範囲 |
|---|---|
| 新機能リリース時 | 当該機能に対応するケース（例: 新機能Xを追加した場合はXに対応するAT-xxxのみ） |
| 大幅UI変更時 | AT-033（ダークモード巡回）を含む横断ケース一式 |
| 全面棚卸し（本改訂のような区切り） | 35ケース全件 |

本書は 2026-08-02 時点で全 35 ケースを新規作成したが、実施そのものは行っていない
（**未実施**）。次回の機能リリースまたは棚卸しのタイミングで実施することを推奨する。

## 8. 署名欄

| 役割 | 氏名 | 実施日 | 判定 |
|---|---|---|---|
| 受入実施者 | — | — | — |
| 受入判定者（プロダクトオーナー） | — | — | — |

## 9. 改訂履歴

| 版 | 日付 | 内容 | 作成者 |
|---|---|---|---|
| 1.0 | 2026-07-16 | 初版（38行、UAT-1〜12の12ケースのみ、うちUAT-8〜12はUI刷新分） | 開発チーム |
| 2.0 | 2026-08-02 | 全面改訂。`feature_contracts.yml` の risk_level: critical/high 全31機能に受入ケースを新規割当（AT-001〜031）、複合シナリオ4件を追加（AT-032〜035）、合格基準・不合格時対応フロー・受入体制を新設。実施結果はすべて「未実施」で提示し捏造なし | 開発チーム |

## 10. 各ケースの不合格判定条件（`failure_modes` 対照表）

`quality/feature_contracts.yml` の各機能が宣言する `failure_modes`（起こってはならない
異常系）を、対応する受入ケースと突き合わせる。実施者は手順実行中にこれらの事象が
発生していないかを重点的に確認すること（2026-08-02実測、feature_contracts.ymlより抽出）。

| ケースID | 要件ID | 監視すべき failure_modes（代表・全件はfeature_contracts.yml参照） |
|---|---|---|
| AT-001 | discover | invalid_url, timeout, login_wall, restricted_url |
| AT-002 | crawl | login_wall_during_crawl, timeout, cancel, partial_checkpoint, robots_disallowed, mutation_blocked |
| AT-003 | login | invalid_credentials, mfa_required, session_expired, recorder_timeout |
| AT-004 | account_auth | account_locked_after_repeated_failures, inactive_account, weak_password_rejected, open_redirect_blocked |
| AT-005 | tenant_membership | no_membership_blocks_work, tenant_not_selected_redirect, last_tenant_cannot_be_deleted |
| AT-006 | tenant_isolation | invalid_tenant_slug_rejected, cross_tenant_path_traversal_blocked |
| AT-007 | diff_history | missing_snapshot, session_expired_false_diff, snapshot_overwrite |
| AT-008 | document_mbt | missing_reference_docs, unmatched_requirements, no_reachable_path |
| AT-009 | sso_oidc | state_mismatch, issuer_mismatch, audience_mismatch, domain_not_allowed |
| AT-010 | autorun_stage_approval | invalid_domain, unknown_stage, unapproved_items |
| AT-011 | autorun_security_kernel | ssrf_attempt_denied, dns_rebinding_denied, budget_exhausted, secret_redacted |
| AT-012 | autorun | approval_timeout, dependency_missing, execution_timeout_partial_result |
| AT-013 | settings | invalid_json, invalid_type, unsafe_option_enabled |
| AT-014 | doc_fusion | no_match, llm_schema_reject, hallucinated_quote, path_traversal_attempt |
| AT-015 | exploration_capture | no_inventory, no_sessions, unmatched_footprint |
| AT-016 | old_new_comparison | one_side_empty, no_pairs, link_timeout, insignificant_diff_shown_as_change |
| AT-017 | snapshot_retention | invalid_policy, symlink_escape, gc_io_failure |
| AT-018 | admin_audit | malformed_line, secret_value, permission_denied, tenant_escape |
| AT-019 | ci_drift_monitor | missing_webhook, notify_http_error, missing_target |
| AT-020 | evidence_pack | missing_report, missing_screenshots, interrupted_run |
| AT-021 | diff_severity | invalid_regex_rule, all_changes_excluded |
| AT-022 | api_v1_openapi | forbidden_non_admin, cross_tenant_access |
| AT-023 | autorun_result_report | unknown_domain, missing_artifact |
| AT-024 | autorun_self_check | self_check_not_applicable, self_check_execution_error |
| AT-025 | autorun_nonfunctional_judge | no_baseline_first_run, login_wall_unobserved |
| AT-026 | autorun_failure_triage | unexplained_failure, environment_error |
| AT-027 | technique_engine | conflicting_constraints_make_tuples_uncoverable, empty_domain |
| AT-028 | autorun_extended_techniques | no_measured_constraints, no_transitions_observed |
| AT-029 | state_transition_table | no_screens_observed, one_switch_path_truncated |
| AT-030 | testcase_table | concurrent_edit_overwrite, playwright_not_installed, execution_timeout |
| AT-031 | cli_mode | zero_tests_executed_reported_as_success, stage_approval_auto_passed_without_human |

## 11. 受入テスト実施前の準備手順

実施者が迷わずケースを開始できるよう、複雑な前提条件を要するケース向けの準備手順を示す。

### 11.1 マルチテナント環境の準備（AT-005・AT-006・AT-032向け）

1. テナントA・テナントBの2つのワークスペースを作成する（管理者コンソールから）。
2. 各テナントに最低1名のメンバー（一般ロール）を招待する。
3. テナントAで最低1回クロールを実施し、出力（`output/tenants/{slug-a}/`）を生成しておく。
4. テナントBのユーザーでログインし、テナントAの出力・観点DB・APIトークンへの
   アクセスを試みる準備をする（実施はケース手順内で行う）。

### 11.2 SSO/OIDC環境の準備（AT-009向け）

1. テスト用のOIDCプロバイダ（またはモック）を用意し、`WEBSPEC2DOC_OIDC_PROVIDER`等の
   環境変数を設定する。
2. 正規の認証情報1組と、意図的に不正な state/issuer を持つリクエストを準備する。
3. 許可ドメイン外のメールアドレスを持つテストアカウントも1つ用意し、
   `domain_not_allowed` の検証に用いる。

### 11.3 AutoRunセキュリティケースの準備（AT-011向け）

1. 外部送信を要する操作（LLM呼び出し等）を含むAutoRunフローを準備する。
2. SSRF・DNSリバインディングを試行する想定の入力（内部IPアドレス表記等）を
   あらかじめ用意しておく（実際の攻撃ではなく、拒否されることを確認する目的）。
3. `egress_log.ndjson` の出力先を確認できる状態にしておく。

### 11.4 CLI実行環境の準備（AT-031向け）

1. ターミナルから `venv/bin/python -m src.cli --help` が実行できることを確認する。
2. `--json` オプションの有無で出力形式が変わることを事前に把握しておく。
3. 意図的にログインが必要なサイトを対象URLとして用意し、認証情報なしでの
   実行時の終了コードを確認できるようにする。

### 11.5 複合シナリオ共通の準備（AT-032〜035向け）

複合シナリオは個別ケース（AT-001〜031）の前提環境を組み合わせて使うため、
先に該当する個別ケースの準備（§11.1〜11.4）を完了させてから着手すること。
特にAT-033（ダークモード巡回）は追加の準備を要さず、OS/ブラウザのダークモード
設定を切り替えるのみでよい。

## 12. 本書のカバレッジ確認

`quality/feature_contracts.yml` の risk_level 別に、本書が実際にケースを割り当てた
比率を確認する（2026-08-02実測、本書自身の集計）。

| risk_level | 総数 | 個別ケース割当 | 複合ケースのみ | 未割当 | 割当率 |
|---|---|---|---|---|---|
| critical | 11 | 11 | 0 | 0 | 100% |
| high | 20 | 20 | 0 | 0 | 100% |
| medium | 18 | 0 | 1（usage_roi） | 17 | 5.6% |
| low | 2 | 0 | 0 | 2 | 0% |
| 合計 | 51 | 31 | 1 | 19 | 60.8% |

critical・high はいずれも100%の割当を達成しており、本書§1の目的（利用者が実際に
価値を受け取れることの確認）の対象を、リスクが高い機能について取りこぼしなく
カバーしていることを示す。medium・low への割当拡大は次回改訂の検討課題とする。

## 13. 用語の定義

| 用語 | 定義 |
|---|---|
| 判定 | 本書における各ケースの実施結果欄。「未実施」「合格」「不合格」「条件付き合格」のいずれかを記入する |
| claim_scope | `evidence_pack` 機能が明示する「どこまでを主張できるか」の範囲。過大な主張を避ける設計原則 |
| evidence-only原則 | 観測した事実のみを主張し、推測や未確認の内容を事実として提示しない本製品の設計原則 |
| 複合シナリオ | 単一機能ではなく複数機能・非機能観点を横断して確認するテストケース（AT-032〜035） |
