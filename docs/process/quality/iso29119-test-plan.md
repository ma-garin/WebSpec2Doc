# WebSpec2Doc テスト計画書（ISO/IEC/IEEE 29119-3 準拠）

**目的**: 本リポジトリの実在するテスト資産・品質ゲート・機能契約を、29119-3 の Test Plan 項目構成に写像し、以後の合否判定を同一の基準で行えるようにする。

> 本計画は **WebSpec2Doc という製品自身をテストするための計画**である。
> `docs/process/TEST_LEVEL_POLICY.md` は「製品が顧客に提供するテスト範囲（受入〜システム〜API 結合、単体は対象外）」の宣言であり、本計画とは別物。混同しないこと。

---

## 1. 文書識別・版・適用範囲（29119-3: 5.2 Overview / Scope）

| 項目 | 内容 |
|---|---|
| 文書 ID | WS2D-TP-001 |
| 版 | 1.0.0 |
| 作成日 | 2026-08-23 |
| 準拠規格 | ISO/IEC/IEEE 29119-3:2021（Test Plan）、29119-2:2021（リスクベース）、ISTQB FL v4.0 |
| 対象システム | WebSpec2Doc（Flask 3.1.3 / Python 3.12 / vanilla JS） |
| 上位文書 | `docs/process/TESTING_STRATEGY.md`（v1.0.0 APPROVED）、`docs/process/DEFINITION_OF_DONE.md`（v1.0.0） |
| 従属文書 | `quality/feature_contracts.yml`、`docs/process/functional-integrity-gate.md`、`.claude/rules/functional-integrity.md` |
| 承認状態 | 未承認（レビュー待ち） |

### 1.1 既存文書との関係（矛盾させない責務分担）

| 文書 | 本計画との関係 |
|---|---|
| `docs/process/TESTING_STRATEGY.md` | L1〜L4 の定義・ツールチェーン・UAT シナリオの**原典**。本計画は参照し再定義しない |
| `docs/process/DEFINITION_OF_DONE.md` | 変更タイプ別（Type A/B/C）の完了条件の**原典**。第 5 章の終了基準はこれに従属 |
| `quality/feature_contracts.yml` | 機能契約 52 件の**原典**。第 4 章のリスク優先度はこの `risk_level` を根拠にする |
| `docs/process/functional-integrity-gate.md` | 完了判定の必須実行パスと `未確認` ルールの**原典** |

---

## 2. テストの対象と対象外（29119-3: Test items / Features not to be tested）

### 2.1 テスト対象（実測: 2026-08-23）

| 対象 | 実測値 | 取得コマンド |
|---|---|---|
| Python 実装ファイル（`src/`） | 147 ファイル | `find src -name "*.py" \| wc -l` |
| Python 実装ファイル（`web/`） | 93 ファイル | `find web -name "*.py" \| wc -l` |
| 実装 LOC（`src/` + `web/` + `app.py`） | 57,277 行 | `find src web app.py -name "*.py" -exec cat {} + \| wc -l` |
| HTTP ルートモジュール | 27 ファイル（`web/routes/`） | `ls web/routes/*.py \| grep -v __init__ \| wc -l` |
| サービスモジュール | 46 ファイル（`web/services/`） | `ls web/services/*.py \| grep -v __init__ \| wc -l` |
| ルート宣言（デコレータ数 / 一意パス数） | 194 / 171 | `grep -rhoE "@[a-z_]+\.(route\|get\|post\|put\|delete)\(" web app.py \| wc -l` |
| HTML テンプレート | 43 ファイル | `find templates -name "*.html" \| wc -l` |
| JavaScript | 55 ファイル / 18,153 行（うち非 vendor 53） | `find static -type f -name "*.js" \| wc -l` |
| CSS | 20 ファイル / 7,882 行 | `find static -type f -name "*.css" \| wc -l` |
| 機能契約（テスト対象機能の正本） | 52 件（全件 `status: implemented`） | `grep -c '"feature_id"' quality/feature_contracts.yml` |

### 2.2 4 システム構成と対象範囲

| # | システム | 実在物 | 主なテスト対象 |
|---|---|---|---|
| 01 | ドキュメント作成 | `templates/partials/view-generate.html`、`view-dashboard.html`、`web/routes/discover.py`・`crawl.py`・`report.py`、`src/crawler/`(18)・`src/analyzer/`(10)・`src/generator/`(24) | クロール → 解析 → 仕様書生成 → 永続化 |
| 02 | テスト活動支援 | `templates/partials/view-ta-*.html`（10 画面）、`web/routes/qa_process.py`・`viewpoints.py`・`traceability.py`、`src/techniques/`・`src/mbt/`(8) | 観点・技法・テストケース・トレーサビリティ |
| — | AutoRun | `templates/partials/view-auto-run.html`、`templates/autorun-report.html`、`web/routes/auto_run.py`・`autorun_stages.py`・`autorun_report.py`、`src/autorun/`(14) | 17 ステップの段階承認・実行・レポート |
| — | マルチテナント基盤 | `web/auth.py`(272 行)・`web/tenancy.py`(67 行)・`web/security.py`(95 行)・`web/validation.py`(114 行)、`web/routes/login.py`・`oidc.py`・`tenant_admin.py`・`admin.py` | 認証・テナント分離・権限・監査 |

### 2.3 対象外（Features not to be tested）

| 対象外 | 理由（根拠） |
|---|---|
| `output/`、`venv/`、`node_modules/` | `docs/process/TESTING_STRATEGY.md` §1 で明示的に適用外 |
| `static/vendor/` 配下（2 ファイル） | 外部配布物。上流の責務 |
| 性能テスト（負荷・耐久） | `docs/process/TESTING_STRATEGY.md` §3 で「現状対象外（将来拡張）」と宣言済み。ただし `src/health/`・`tests/test_perf_budgets.py` によるバジェット確認は L1/L2 で実施 |
| モバイル / タブレット表示 | PC 専用製品として対象外（検証解像度は 1280×800・1366×768・1920×1080） |
| 外部 LLM プロバイダ本体の品質 | `src/llm/openai_client.py` は差し替え可能アダプタ。`scripts/quality_harness.py` の `UNREGISTERED_ALLOWLIST` で機能契約対象外と定義済み |
| `web/config.py`・`web/types.py` 等の横断部品 | 同上（`UNREGISTERED_ALLOWLIST` に列挙。単独機能ではない） |

---

## 3. テストレベルとテストタイプ（29119-3: Test levels / Test types）

### 3.1 本リポジトリの L0〜L3 と ISTQB レベルの対応

| 本リポジトリ | 実行コマンド（Makefile） | ISTQB v4.0 のレベル | 実測資産 | ゲート |
|---|---|---|---|---|
| **L0** 機能完全性ハーネス | `make quality-harness` → `scripts/quality_harness.py` | ISTQB のテストレベルに**該当なし**（静的テスト／仕様と実装の整合検査。ISTQB FL 3.2 のレビュー・静的解析に相当） | 機能契約 52 件 + 自己検査 5 件（`tests/smoke/test_quality_harness.py`） | 契約違反 1 件で exit != 0 |
| **L1** コンポーネント | `make test`（`pytest tests/ --ignore=tests/e2e`） | コンポーネントテスト | L1/L2 合算で 196 ファイル / 2,989 テスト関数 | 1 件でも FAIL → コミット不可 |
| **L2** 統合 | 同上（L1 と同一コマンド。Flask test client 利用） | コンポーネント統合テスト + システム統合テスト | 同上（L1 と分離計測は**未計測**） | 同上 + 行カバレッジ 80% |
| **L3** システム / E2E | `make verify-ui`（`pytest tests/e2e/`） | システムテスト | 28 ファイル / 117 テスト関数（うち `tests/e2e/system/` に ST1〜ST6 の 6 ファイル） | 1 件でも FAIL → `.ui-verified` 不生成 → コミット不可 |
| **L4** 受入 | 手動（`docs/process/TESTING_STRATEGY.md` §4 の UAT-01〜UAT-07） | 受入テスト | 7 シナリオ（自動化なし） | プロダクトオーナー承認 |

**L1/L2 が分離できていない点は本計画の既知の弱点**（第 8 章 弱点 2 参照）。`make test` は両者を同一コマンドで実行し、pytest マーカーによる区別が `pyproject.toml` に定義されていない（`[tool.pytest.ini_options]` に `markers` の記載なし）。

### 3.2 テストタイプ × レベル

| テストタイプ | L0 | L1/L2 | L3 | L4 | 本リポジトリの実在物 |
|---|---|---|---|---|---|
| 機能 | ✓ | ✓ | ✓ | ✓ | 機能契約の `required_tests: [happy_path, error_path, evidence]` |
| 回帰 | ✓ | ✓ | ✓ | — | `tests/e2e/test_xss_regression_e2e.py`、`test_visual_regression_e2e.py`、`tests/test_ci_drift.py` |
| 確認（再テスト） | — | ✓ | ✓ | — | `tests/test_no_collection_warnings.py`、`tests/e2e/test_broken_views_e2e.py` |
| セキュリティ | — | ✓ | ✓ | — | `tests/test_security_headers.py`、`test_security_kernel.py`、`test_url_safety.py`、`test_validation_security.py`、`test_prompt_guard.py`、`tests/e2e/test_autorun_security_e2e.py`、`make security`（bandit `-ll` + pip-audit） |
| ユーザビリティ | — | ✓ | 一部 | ✓ | `tests/test_ux_heuristics.py`、`test_usability_smells.py`、`tests/e2e/test_ux_review_e2e.py` |
| アクセシビリティ | — | ✓ | — | — | `tests/test_a11y_extraction.py`、`test_axe_runner.py`、`test_accessibility_reporter.py` |
| 相互運用（マルチテナント） | ✓ | ✓ | ✓ | — | テナント関連テストファイル 11 件、`tests/e2e/test_auth_tenant_e2e.py` |
| 静的解析 | — | — | — | — | `make lint`: ruff + mypy + `scripts/check_e2e_conventions.py` + `scripts/check_fetch_error_handling.py` |

**適用したテスト技法**（`src/techniques/`・`src/mbt/` に実装があり、自テストにも同種の観点を適用する）: 同値分割・境界値（`tests/test_bva.py`）、ペアワイズ（`test_pairwise.py`）、状態遷移（`test_state_table.py`・`test_transition_graph.py`・`test_prime_path.py`）、メタモルフィック（`test_metamorphic.py`）、ミューテーション（`test_mutation_verifier.py`）、ファジング（`test_viewpoint_catalog_fuzzing.py`・`test_viewpoint_csv_import_fuzzing.py`）。パラメタライズ利用箇所は実測 65 件（`grep -rE "@pytest.mark.parametrize" tests --include="*.py" \| wc -l`）。

---

## 4. リスクベースのテスト戦略（29119-2: リスク識別・分析・軽減）

### 4.1 リスクの識別根拠

`quality/feature_contracts.yml` の `risk_level` を一次根拠とする（実測分布）:

| risk_level | 件数 | 取得コマンド |
|---|---|---|
| critical | 11 | `grep -o '"risk_level": "[a-z]*"' quality/feature_contracts.yml \| sort \| uniq -c` |
| high | 21 | 同上 |
| medium | 18 | 同上 |
| low | 2 | 同上 |
| **合計** | **52** | |

`scripts/quality_harness.py` は `RISK_LEVELS_REQUIRING_FAILURE_TESTS = {"critical", "high"}` を持ち、critical/high の 32 件には失敗系テストの登録を機械的に要求する。本計画の優先度はこの機構と整合させる。

### 4.2 プロダクトリスク登録簿（実モジュール名で記述）

影響度 × 発生可能性 → 優先度（P1 最優先）。

| ID | プロダクトリスク（実在物） | 影響度 | 発生可能性 | 優先度 | 軽減策（実在するテスト／ゲート） |
|---|---|---|---|---|---|
| PR-01 | **テナント越境**: `web/tenancy.py`(67 行) のテナント解決を経ずに `web/routes/runs.py`・`history.py` が `instance/tenants/{slug}/` を読み、他テナントの成果物が露出する | 高 | 中 | **P1** | `tests/test_tenancy.py`、`test_tenant_isolation`系（テナント関連 11 ファイル）、`tests/e2e/test_auth_tenant_e2e.py`、`tests/e2e/system/test_st1_auth.py` |
| PR-02 | **SSRF / 内部ネットワーク到達**: `src/crawler/url_safety.py`(82 行) の判定を `WEBSPEC2DOC_ALLOW_LOCAL=1` が無条件に無効化し、社内 IP へクロールが飛ぶ | 高 | 中 | **P1** | `tests/test_url_safety.py`、`tests/test_settings_allow_local.py`、`make security`（bandit） |
| PR-03 | **AutoRun の破壊的操作**: `src/autorun/` (14 ファイル) が対象サイトへ書き込み系操作を実行する。`WEBSPEC2DOC_ALLOW_MUTATION`・`WEBSPEC2DOC_ALLOW_FORM_SUBMIT`・`WEBSPEC2DOC_EGRESS_POLICY` の既定値が誤ると本番サイトを変更する | 高 | 低 | **P1** | `tests/test_autorun_mutation_stage.py`、`test_security_kernel.py`、`tests/e2e/test_autorun_security_e2e.py`、`_autorun_egress.ts` |
| PR-04 | **XSS**: クロール結果（外部サイト由来の HTML/テキスト）を `static/js/results.js`・`report.js` が DOM へ流し込む。53 ファイルの vanilla JS に共通のサニタイズ層がない | 高 | 中 | **P1** | `tests/e2e/test_xss_regression_e2e.py`、`tests/test_markdown_lite.py`、`tests/test_security_headers.py` |
| PR-05 | **認証迂回**: `web/auth.py`(272 行) の `WEBSPEC2DOC_AUTH_MODE=off` / `WEBSPEC2DOC_AUTH_MOCK` が本番構成に混入し、全 171 パスが無認証で開く | 高 | 低 | **P1** | `tests/test_auth.py`、`test_app_login.py`、`test_session_guard.py`、`test_mock_auth_tenancy.py`、`tests/e2e/system/test_st1_auth.py` |
| PR-06 | **プロンプトインジェクション**: クロール対象サイトのテキストが `src/llm/` (8 ファイル) 経由で LLM へ渡り、生成された観点・テストケースが汚染される | 中 | 中 | **P2** | `tests/test_prompt_guard.py`、`test_llm_wiring.py`、`test_llm_extractor.py` |
| PR-07 | **UI 未接続機能**: 画面（`templates/partials/` 33 ファイル）だけ存在しルートが無い機能が残る | 中 | 中 | **P2** | L0 `_validate_no_unimplemented_user_paths` / `_validate_all_modules_registered`（`FORBIDDEN_STATUS = {"ui-only"}`） |
| PR-08 | **クロール中断でのデータ損失**: `src/crawler/parallel_crawler.py`・`web/services/job_queue` 系でタイムアウト・キャンセル時に部分結果が保存されず、長時間の処理がやり直しになる | 中 | 高 | **P2** | `tests/test_crawl_resilience.py`、`test_job_queue.py`、`test_parallel_site_crawl.py`、`test_real_site_resilience.py` |
| PR-09 | **ログイン壁での沈黙失敗**: `web/routes/login.py`・`src/crawler/` がログイン必須サイトで空の成果物を「成功」として返す | 中 | 高 | **P2** | `tests/test_login_wall.py`、`test_login_signal.py`、`test_auto_login.py`、`test_auth_recorder.py` |
| PR-10 | **成果物の非互換ドリフト**: `src/generator/` (24 ファイル) の出力形式変更で過去 run のアーティファクトが読めなくなる | 中 | 中 | **P2** | `tests/test_history_artifact_parity.py`、`test_archive.py`、`test_retention.py`、`.github/workflows/spec-drift.yml` |
| PR-11 | **fetch のエラー無処理**: 53 個の JS が `fetch` の失敗を握り潰し、画面が無反応になる | 中 | 中 | **P2** | `make lint` 内の `scripts/check_fetch_error_handling.py --fail-on-missing`（P0-3 ゲート） |
| PR-12 | **段階承認の状態破綻**: `web/routes/autorun_stages.py` の 17 ステップで、承認/スキップ/リセットの遷移が不正状態を作る | 中 | 中 | **P2** | `tests/test_autorun_stages.py`、`test_autorun_stages_api.py`、`test_stage_skip_on_rerun.py`、`tests/e2e/test_autorun_state_matrix_e2e.py`、`test_stale_state_e2e.py` |
| PR-13 | **依存の脆弱性**: `playwright==1.61.0`・`flask==3.1.3` 等の既知 CVE | 中 | 低 | **P3** | `make security`（pip-audit）、`make audit`（pip-audit + `npm audit` on `output/.playwright_env`） |
| PR-14 | **Playwright ランタイム不整合**: `PLAYWRIGHT_BROWSERS_PATH=$(CURDIR)/.runtime/ms-playwright` の Chromium 未導入で L3 が全滅する | 低 | 中 | **P3** | `make check-runtime`（`scripts/manage_playwright_runtime.py check`）、`make doctor`（`src/doctor.py`）、`tests/test_playwright_runtime.py`、`tests/test_doctor.py` |
| PR-15 | **文言・表記の不統一**: 43 テンプレート間で用語がずれ、生成物の品質主張が揺れる | 低 | 中 | **P3** | `tests/test_wording.py`、`tests/test_ux_claim_scope.py`、`scripts/check_doc_consistency.py`（`make docs-check`） |

### 4.3 リスク優先度とテスト強度の対応

| 優先度 | 対象 | 要求するテスト |
|---|---|---|
| P1 | PR-01〜PR-05 | happy path / failure path / timeout / cancellation / auth・login wall / robots 制限 / partial result / 証跡 / ユーザー可視エラー の 9 観点すべて（`docs/process/functional-integrity-gate.md` の必須確認観点）。L1/L2 + L3 の両方で確認 |
| P2 | PR-06〜PR-12 | happy path + failure path + 証跡。L3 は代表フローのみ |
| P3 | PR-13〜PR-15 | happy path + 自動チェッカによる検出のみ |

---

## 5. 合否判定基準・開始/終了基準（29119-3: Entry / Exit criteria）

### 5.1 開始基準（Entry Criteria）

| # | 基準 | 確認方法 |
|---|---|---|
| E-1 | `venv/bin/python` が存在する（Python 3.12） | Makefile の `check-venv` ターゲット |
| E-2 | Chromium が `.runtime/ms-playwright` に導入済み | `make check-runtime` |
| E-3 | テスト対象機能が `quality/feature_contracts.yml` に登録済み | `make quality-harness`（`_validate_all_modules_registered`） |
| E-4 | pre-commit hook がインストール済み | `make setup-hooks` → `.git/hooks/pre-commit` |
| E-5 | L3 実行時、対象 URL（既定 `http://127.0.0.1:8765`）が応答する | `tests/e2e/conftest.py` の `flask_server`（`WEBSPEC2DOC_E2E_URL` を参照） |

### 5.2 終了基準（Exit Criteria）

`docs/process/DEFINITION_OF_DONE.md` の変更タイプ別 DoD に従属する。本計画で追加定義はしない。

| レベル | 終了基準 | 根拠 |
|---|---|---|
| L0 | `scripts/quality_harness.py` が exit 0（契約違反 0 件、`status: ui-only` 0 件、未登録モジュール 0 件） | `docs/process/functional-integrity-gate.md`「ハーネス実行」 |
| L1/L2 | `make test` 全 PASS **かつ** `make coverage` で `src/`+`web/` 行カバレッジ **80% 以上**（`--cov-fail-under=80`） | `docs/process/TESTING_STRATEGY.md` §2 L1、DoD Type A |
| L3 | `make verify-ui` 全 PASS（`E2E_MAXFAIL=1` により初回失敗で打ち切り）→ `.ui-verified` に `git HEAD + UI hash + timestamp` が記録される | Makefile `verify-ui`、`.githooks/pre-commit` v2 |
| L3 追加 | UI 変更時、`.ui-verified` の UI hash が staged ファイルの再計算 hash と一致（`scripts/ui-hash.py`） | DoD Type B「MANDATORY」 |
| L4 | UAT-01〜UAT-07 をプロダクトオーナーが確認し、スクリーンショットを `tests/e2e/screenshots/uat-XX.png` に保存 | `docs/process/TESTING_STRATEGY.md` §4 |
| 静的 | `make lint` PASS（ruff / mypy / `check_e2e_conventions.py` / `check_fetch_error_handling.py --fail-on-missing`） | Makefile `lint`、CI `quality` ジョブ |
| セキュリティ | `make security` PASS（bandit `-ll` on `src web app.py` / pip-audit on `requirements.txt`） | Makefile `security` |

### 5.3 個別テストの合否判定基準

| 判定 | 条件 |
|---|---|
| PASS | 期待結果と実際の結果が一致し、かつ証跡（スクリーンショット / ログ / 出力ファイル）が残っている |
| FAIL | 期待結果と不一致、または例外送出 |
| **未確認** | 実行していない、または証跡がない。**「完了」「検証済み」「問題なし」と記載してはならない**（`docs/process/functional-integrity-gate.md`「未確認ルール」） |
| BLOCKED | E-1〜E-5 の開始基準を満たさず実行不能 |

**「テストが通った」だけでは完了と認めない。**必須実行パス `UI → API → backend route → service/core → output → persistence → error handling → user-visible evidence` を辿ったことが完了の条件である。

---

## 6. テスト環境・データ（29119-3: Test environment requirements / Test data）

### 6.1 実行環境

| 項目 | 値 | 根拠 |
|---|---|---|
| Python | 3.12（`venv/lib/python3.12`、`pyproject.toml` の `target-version = "py312"`、CI も `python-version: "3.12"`） | `pyproject.toml`、`.github/workflows/ci.yml` |
| Web フレームワーク | flask==3.1.3 | `requirements.txt` |
| テストランナー | pytest==9.0.3 / pytest-cov==5.0.0 / pytest-timeout==2.3.1 | `requirements.txt` |
| E2E | pytest-playwright==0.8.0 / playwright==1.61.0（Chromium） | `requirements.txt` |
| ブラウザ配置 | `PLAYWRIGHT_BROWSERS_PATH = $(CURDIR)/.runtime/ms-playwright` | Makefile / `.github/workflows/ci.yml` |
| venv | `venv/bin/python`（Makefile の `PYTHON` 変数。システム Python は使わない） | Makefile |
| 既定ポート | 8765（`E2E_BASE_URL ?= http://127.0.0.1:8765`、`WEBSPEC2DOC_PORT` で変更可） | Makefile |

### 6.2 テスト用環境変数（実在するもののみ）

| 変数 | テストでの用途 | 参照箇所数（実測） |
|---|---|---|
| `FLASK_TESTING` | 起動時の `webbrowser.open` を抑止。**テスト・検証起動では必須** | 3 |
| `WEBSPEC2DOC_ALLOW_LOCAL` | ローカル / プライベート IP へのクロールを許可。E2E で自ホストを対象にするため必要（本番既定は無効） | 16 |
| `WEBSPEC2DOC_AUTH_MODE` | `off` で認証を無効化（`web/auth.py`）。**検証専用。`auth.db` は変更しない** | 2 |
| `WEBSPEC2DOC_AUTH_MOCK` | モック認証（`tests/test_mock_auth_tenancy.py`） | 2 |
| `WEBSPEC2DOC_E2E_URL` | L3 の対象 URL。Makefile が `E2E_BASE_URL` と同値に揃える | Makefile |
| `E2E_MAXFAIL` | 既定 1（fail fast）。全件確認時は 0 | Makefile |
| `WEBSPEC2DOC_ALLOW_MUTATION` / `WEBSPEC2DOC_ALLOW_FORM_SUBMIT` / `WEBSPEC2DOC_EGRESS_POLICY` | AutoRun の破壊的操作・外部通信の制御（PR-03 の直接の軽減手段） | 3 / 2 / 2 |
| `WEBSPEC2DOC_TRUSTED_HOSTS` | 許可ホスト（PR-02） | 4 |
| `WEBSPEC2DOC_LLM_API_KEY` / `_LLM_BASE_URL` / `_LLM_MODEL` | LLM 経路。未設定時はルールベースで全機能が成立する（`quality_harness.py` のコメント） | 1 / 4 / 4 |
| `WEBSPEC2DOC_OIDC_*`（8 変数） | SSO 経路（`web/routes/oidc.py`、`tests/test_oidc.py`） | 各 1〜2 |
| `WEBSPEC2DOC_SECRET_KEY` / `_SECURE_COOKIES` / `_SESSION_HOURS` | セッション（`tests/test_session_store.py`） | 各 1 |
| `WEBSPEC2DOC_DATA_DIR` / `_AUTH_DB` | データ隔離。**テストが本番 `instance/` を汚さないために必須** | 各 1 |

秘密情報（`WEBSPEC2DOC_LLM_API_KEY`・`WEBSPEC2DOC_OIDC_CLIENT_SECRET`・`WEBSPEC2DOC_SECRET_KEY`）は環境変数のみで供給し、テストコード・フィクスチャに埋め込まない。

### 6.3 テストデータ

| データ | 実体 | 用途 |
|---|---|---|
| 同梱デモサイト | `tests/fixtures/sample_site/`、`demo/`、`make demo`（`scripts/demo.sh`） | 外部サイトに依存しないクロール検証 |
| E2E スクリーンショット | `tests/e2e/screenshots/`（`--screenshot=only-on-failure`） | L3 の証跡 |
| ビジュアル基準 | `tests/e2e/snapshots/` | `test_visual_regression_e2e.py` の比較基準 |
| 永続データ | `instance/tenants/{slug}/`（例: `feedback.jsonl`） | テナント分離の検証対象。テスト実行時は `WEBSPEC2DOC_DATA_DIR` で隔離 |

**検証用ドメイン**: 外部実サイトを既定の対象にしない。`http://127.0.0.1:8765`（自ホスト）と同梱デモサイトを一次対象とし、外部サイトを使う場合は `WEBSPEC2DOC_TRUSTED_HOSTS` に明示登録する。

---

## 7. 中断・再開の基準、成果物一覧、役割と責任

### 7.1 中断基準（Suspension Criteria）

| # | 中断条件 | 判定根拠 |
|---|---|---|
| S-1 | `make quality-harness`（L0）が FAIL | 機能契約と実装が乖離しており、下位レベルの結果が信用できない |
| S-2 | E-1〜E-5 の開始基準を満たさない（venv 不在・Chromium 不在・対象 URL 無応答） | `check-venv` / `check-runtime` が exit != 0 |
| S-3 | P1 リスク（PR-01〜PR-05）に該当する不具合を検出 | セキュリティ・データ越境。他テストを続ける前に修正する |
| S-4 | L3 が `E2E_MAXFAIL=1` で初回失敗により打ち切られた | Makefile の fail fast 設計そのもの |
| S-5 | 同一の失敗が `git stash` 後の素の状態でも再現する（main 由来） | 当該スコープでの切り分けを打ち切り、main の課題として分離する |

### 7.2 再開基準（Resumption Criteria）

- S-1: 契約または実装を修正し、`make quality-harness` が exit 0 になったこと
- S-2: `make setup` / `make setup-runtime` / `make doctor` で環境不一致が解消したこと
- S-3: 修正コミットに対し、該当リスクの failure path テストが追加され PASS したこと
- S-4/S-5: 原因の修正後、`E2E_MAXFAIL=0` で全件再実行し PASS したこと

### 7.3 成果物一覧（Test Deliverables）

| 成果物 | 生成物 / 場所 | 生成契機 |
|---|---|---|
| 本テスト計画書 | `docs/process/quality/iso29119-test-plan.md` | 手動 |
| テスト戦略 | `docs/process/TESTING_STRATEGY.md` | 手動（既存） |
| 機能契約 | `quality/feature_contracts.yml`（52 件） | 機能追加時に必須更新 |
| L3 検証マーカー | `.ui-verified`（git HEAD + UI hash + ISO8601 timestamp） | `make verify-ui` |
| スクリーンショット | `tests/e2e/screenshots/` | L3 失敗時・UAT 実施時 |
| カバレッジレポート | term-missing 形式（`make coverage`） | 手動実行時 |
| インシデント記録 | `docs/process/INCIDENT_POSTMORTEM.md` | DoD 違反が判明した時 |
| SDLC 納品文書 | `docs/sdlc/`（`make docs` = `docs-extract` + `docs-build` + `docs-check`） | リリース時 |
| CI 実行結果 | `.github/workflows/ci.yml`（`changes` → `quality`: ruff / mypy / test / security） | push（main）・PR。`docs/`・`*.md` のみの変更は重いジョブをスキップ |

### 7.4 役割と責任

| 役割 | 担当 | 責務 |
|---|---|---|
| テストマネージャ | プロダクトオーナー（リポジトリ所有者） | 本計画の承認、L4 受入の合否判定、リスク優先度の最終決定 |
| テスト設計・実装 | 実装担当（AI エージェント含む） | L0〜L3 のテスト実装、機能契約への登録、`未確認` の明示 |
| テスト実行（自動） | pre-commit hook / GitHub Actions | L0〜L2 + lint + security の機械的強制 |
| L3 実行 | 実装担当 | UI 変更時の `make verify-ui` 実行と `.ui-verified` 生成 |
| 独立検証 | 生成者以外のレビュアー（`code-reviewer` / `security-reviewer`） | **作った本人に検証させない**。DoD Type A の REQUIRED 項目 |
| L4 受入 | プロダクトオーナー | UAT-01〜UAT-07 の実施と承認 |

---

## 8. スケジュールと工数見積（29119-3: Test schedule / Staffing and training needs）

### 8.1 テストサイクルのスケジュール（トリガ駆動。カレンダー日付を持たない）

| フェーズ | トリガ | 対象レベル | 実行時間 |
|---|---|---|---|
| コミット前 | `git commit` | L0（機能変更時）+ L1/L2 + UI 変更時の L3 マーカー照合 | **未計測** |
| PR 作成時 | pull_request | lint / mypy / L1/L2 / security（`docs/`・`*.md` のみの変更はスキップ） | **未計測** |
| main 統合時 | push to main | 同上（`code=true` 固定） | **未計測** |
| UI 変更時 | `static/**`・`templates/**` の変更 | L3 全件 | **未計測** |
| リリース時 | 手動 | L0〜L3 全件（`make verify-all`）+ L4（UAT-01〜07）+ `make docs` | **未計測** |
| 定期 | `.github/workflows/spec-drift.yml` | 生成仕様のドリフト検出 | **未計測** |

### 8.2 テスト規模（実測）

| 指標 | 実測値 |
|---|---|
| テストファイル総数（`tests/**/test_*.py`） | 224 |
| うち L1/L2（`tests/e2e` 除く） | 196 ファイル |
| うち L3（`tests/e2e/`） | 28 ファイル |
| テスト関数総数 | 3,106 |
| うち L1/L2 | 2,989 |
| うち L3 | 117 |
| うち L0 自己検査（`tests/smoke/`） | 5 |
| パラメタライズ宣言 | 65 |
| 機能契約 | 52 件（critical 11 / high 21 / medium 18 / low 2） |
| 実装 LOC 対 テスト関数比 | 57,277 行 / 3,106 関数 ≒ 18.4 行/関数 |

### 8.3 工数見積

| 作業 | 見積 | 備考 |
|---|---|---|
| 各レベルの**実行時間** | **未計測** | 本計画作成時にテストを実行していないため。`make test` / `make verify-ui` / `make quality-harness` の所要時間は次回実行時に実測して本節へ追記する |
| 現行カバレッジ実績値 | **未計測** | 閾値 80%（`--cov-fail-under=80`）は設定済みだが、現在値は `make coverage` 未実行のため不明 |
| L1/L2 の内訳（コンポーネント vs 統合） | **未計測** | pytest マーカーによる分離が未定義（第 3.1 節） |
| 新機能 1 件あたりのテスト実装工数 | **未計測** | 過去実績データが `docs/` 内に存在しない |
| L4 受入（UAT-01〜07） | **未計測** | 手動 7 シナリオ。過去の実施記録なし |

**実測を要する項目は上表のとおりすべて「未計測」と明記する。**推定値・概算値は本計画に記載しない。

---

## この計画の弱点

1. **実行時間とカバレッジ実績が全て未計測**であり、第 8 章のスケジュールは順序関係しか示せていない。80% 閾値に対する現在値が不明なため、終了基準 L1/L2 が今日の時点で満たせるのかを本計画は保証していない。
2. **L1 と L2 が分離できていない。**`make test` は両者を同一コマンドで実行し、`pyproject.toml` に区別用の pytest マーカー定義がない。よって「統合テストのカバレッジ」を独立に語れず、第 3.1 節の ISTQB 対応表は L1/L2 を合算した近似にとどまる。
3. **リスク登録簿の発生可能性は過去欠陥データに基づかない。**`docs/process/INCIDENT_POSTMORTEM.md` の件数を集計していないため、PR-01〜PR-15 の「発生可能性」列は機能契約の `risk_level` とコード構成からの導出であり、実績頻度による裏付けがない。
