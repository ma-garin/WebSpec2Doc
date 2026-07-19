# WS2D-RD-001 要件定義書

- 版数: 2.0 / 作成日: 2026-07-16 / 最終更新: 2026-07-19 / 準拠: IPA 共通フレーム（要件定義）
- 要件の機械可読ソース: `quality/feature_contracts.yml`（本書はその整形・解説）
- 要件IDは `feature_id`。優先度は `risk_level`、受入基準は `required_tests` に対応。

## 1. システム目的

稼働中の Web システムの URL から、QA テスト分析インプット文書（画面仕様書・テスト
設計・画面遷移図・テストケース等）を自動生成する。一度登録したサイトを再クロールして
**仕様ドリフトを検知**する継続利用を主眼とする（詳細な用語は `CONTEXT.md`）。

## 2. 対象利用者・運用形態

- 主利用者: QA エンジニア / テスト設計者。
- 運用: ローカル単一利用者（既定）。社内サーバ展開時のみ `WEBSPEC2DOC_TRUSTED_HOSTS`＋
  `WEBSPEC2DOC_AUTH` で利用者ログイン＋ワークスペースを有効化（ADR-0004）。

## 3. 機能要件一覧（33件）

| 要件ID | 名称 | 優先度 | 受入基準（必須テスト種別） |
|---|---|---|---|
| `discover` | URL解析 / 画面発見 | critical | happy_path, error_path, evidence |
| `crawl` | クロール / レポート生成 | critical | happy_path, error_path, cancel_path, checkpoint_path, evidence |
| `login` | ログイン / セッション | critical | happy_path, error_path, session_expiry_path, evidence, timeout_path, cancel_path |
| `account_auth` | アプリ利用者認証（ログイン/セッション/アカウント管理） | critical | happy_path, error_path, lockout_path, session_expiry_path, evidence |
| `tenant_isolation` | テナント分離（出力・観点DB・APIトークンのワークスペース分離） | critical | happy_path, isolation_path, error_path, evidence |
| `autorun` | AutoRun | high | happy_path, approval_path, cancel_path, error_path, timeout_path, evidence |
| `diff_history` | 差分 / 履歴 / 再クロール | critical | happy_path, breaking_change_path, error_path, evidence |
| `settings` | 設定 | high | happy_path, validation_path, evidence |
| `usage_roi` | ROIダッシュボード / 利用実績 | medium | happy_path, empty_path, evidence |
| `coverage_gap_report` | カバレッジと未確認領域（網羅性証明） | medium | happy_path, empty_path, evidence |
| `doc_fusion` | 文書×実測突合（Doc Fusion） | high | happy_path, error_path, mismatch_detection, evidence |
| `exploration_capture` | 探索セッション記録 / カバレッジヒートマップ | high | happy_path, error_path, state_join_key, evidence |
| `reverse_assets` | リバース（記録セッション→テスト資産の逆生成） | medium | happy_path, error_path, state_join_key, evidence |
| `field_definition_bva` | 項目定義書＋境界値分析（BVA）テストデータ自動生成 | medium | happy_path, error_path, evidence |
| `finding_ticket` | 気づきマーク → 再現手順付きバグ票（JSON/CSV エクスポート） | medium | happy_path, error_path, state_join_key, evidence |
| `test_plan` | テスト計画ドラフト生成（インベントリ×ROI係数→工数見積・スコープ表） | medium | happy_path, error_path, evidence |
| `ci_warnings_cleanup` | CI警告一掃（pytest収集警告・Pillow非推奨警告の解消と再発防止） | low | parity, collection_guard, static_guard |
| `old_new_comparison` | 現新比較モード（移行検証支援） | high | happy_path, error_path, evidence, unclassified_fallback |
| `ux_review` | UX自動エキスパートレビュー（axe-core＋ニールセン10原則ヒューリスティック） | medium | happy_path, error_path, evidence |
| `snapshot_retention` | スナップショット保持・容量・バックアップ運用 | high | happy_path, error_path, tenant_isolation, symlink_boundary, evidence |
| `admin_audit` | 管理操作のテナント監査ログ | high | happy_path, error_path, tenant_isolation, authorization, evidence |
| `ci_drift_monitor` | Drift Check as Code（CI組み込みドリフト監視） | high | happy_path, error_path, no_change_path, exit_code_contract, evidence |
| `document_mbt` | 文書駆動MBT（要件×実測からのテスト設計） | critical | happy_path, error_path, coverage_path, no_submit_guarantee, evidence |
| `evidence_pack` | 検収・監査向けテスト実施証跡パック | high | happy_path, missing_input_path, claim_scope, evidence |
| `diff_severity` | 差分の重要度判定と誤検知フィルタ | high | happy_path, determinism, immutability, exclusion_disclosure, evidence |
| `api_v1_openapi` | REST API拡充とOpenAPI公開 | high | happy_path, error_path, authorization_path, implemented_paths_only, evidence |
| `multi_viewport` | マルチビューポート仕様書 | medium | happy_path, error_path, evidence |
| `sso_oidc` | SSO（OIDC）とAPIトークンスコープ | critical | happy_path, error_path, authorization_path, token_validation, evidence |
| `observability` | 可観測性（メトリクス・構造化ログ） | medium | happy_path, failure_observable, evidence |
| `api_spec_recovery` | API仕様の逆生成 | medium | happy_path, no_invention, evidence |
| `screen_coverage_map` | 画面カバレッジマップ | medium | happy_path, no_rate_claim, evidence |
| `wording_consistency` | 文言一貫性・表記ゆれチェック | low | happy_path, dictionary_scope |
| `full_archive` | 完全アーカイブと外形監視（sitemap/PDF） | medium | happy_path, tamper_detection, source_preserved, evidence |

各要件の UI / route / core 実装ファイル・シンボル・異常系・成果物・永続化先は
`quality/feature_contracts.yml` に定義され、`WS2D-TM-001`（トレーサビリティ）で
実装・テストまで追跡できる。

## 4. 横断（全機能共通）要件

- **evidence-only 原則**: 生成物は実在要素の実測根拠（セレクタ・スクショ座標・
  confidence）に紐づく。根拠なき生成物は破棄（`CONTEXT.md` evidence）。
- **クロール礼儀**: robots.txt 尊重・per-origin レート制御・破壊的リクエスト遮断
  （`src/crawler/politeness.py`）。
- **ローカル安全性**: 既定 127.0.0.1 バインド、localhost_guard / CSRF ガード。

## 5. 利用者認証・テナント分離要件（`account_auth` / `tenant_isolation`）

商用/共有サーバ運用向けの認証・テナント分離を実装（詳細は `docs/AUTH_TENANCY.md`）。
- 利用者ログイン・セッション・アカウント管理（パスワード・ロックアウト・API トークン）。
- テナント分離: 出力・観点DB・API トークンをワークスペース単位で分離。
- 実装: `web/auth.py` / `web/services/auth_store.py` / `web/tenancy.py` /
  `web/routes/account.py`。有効化は環境変数（`docs/AUTH_TENANCY.md`）。

> 注: 初期に検討した軽量版（メール自己申告＋WS選択、`docs/design/auth-tenant-integration.md` /
> ADR-0004）は本商用実装に統合・置換された（履歴として design/adr を保持）。

## 6. 非機能要件

`WS2D-NF-001_非機能要件定義書.md` を参照。

## 7. 制約・前提

- LLM 連携（OpenAI）はオプション。未設定時はルールベースでフォールバック（`CONTEXT.md`）。
- 対応ブラウザ実行基盤: Playwright Chromium。
