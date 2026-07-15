# WS2D-RD-001 要件定義書

- 版数: 1.0 / 作成日: 2026-07-16 / 準拠: IPA 共通フレーム（要件定義）
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

## 3. 機能要件一覧（17件）

| 要件ID | 名称 | 優先度 | 受入基準（必須テスト種別） |
|---|---|---|---|
| `discover` | URL解析 / 画面発見 | critical | happy_path, error_path, evidence |
| `crawl` | クロール / レポート生成 | critical | happy_path, error_path, cancel_path, checkpoint_path, evidence |
| `login` | サイト認証 / セッション | critical | happy_path, error_path, session_expiry_path, evidence, timeout_path, cancel_path |
| `autorun` | AutoRun（全自動テスト実行） | high | happy_path, approval_path, cancel_path, error_path, timeout_path, evidence |
| `diff_history` | 差分 / 履歴 / 再クロール | critical | happy_path, breaking_change_path, error_path, evidence |
| `settings` | 設定 | high | happy_path, validation_path, evidence |
| `usage_roi` | ROIダッシュボード / 利用実績 | medium | happy_path, empty_path, evidence |
| `coverage_gap_report` | カバレッジと未確認領域 | medium | happy_path, empty_path, evidence |
| `doc_fusion` | 文書×実測突合（Doc Fusion） | high | happy_path, error_path, mismatch_detection, evidence |
| `exploration_capture` | 探索セッション記録 / ヒートマップ | high | happy_path, error_path, state_join_key, evidence |
| `reverse_assets` | 記録セッション→テスト資産の逆生成 | medium | happy_path, error_path, state_join_key, evidence |
| `field_definition_bva` | 項目定義書＋境界値分析データ生成 | medium | happy_path, error_path, evidence |
| `finding_ticket` | 気づき→再現手順付きバグ票 | medium | happy_path, error_path, state_join_key, evidence |
| `test_plan` | テスト計画ドラフト生成 | medium | happy_path, error_path, evidence |
| `ci_warnings_cleanup` | CI警告一掃 | low | parity, collection_guard, static_guard |
| `old_new_comparison` | 現新比較モード | high | happy_path, error_path, evidence, unclassified_fallback |
| `ux_review` | UX自動レビュー（axe＋ニールセン10原則） | medium | happy_path, error_path, evidence |

各要件の UI / route / core 実装ファイル・シンボル・異常系・成果物・永続化先は
`quality/feature_contracts.yml` に定義され、`WS2D-TM-001`（トレーサビリティ）で
実装・テストまで追跡できる。

## 4. 横断（全機能共通）要件

- **evidence-only 原則**: 生成物は実在要素の実測根拠（セレクタ・スクショ座標・
  confidence）に紐づく。根拠なき生成物は破棄（`CONTEXT.md` evidence）。
- **クロール礼儀**: robots.txt 尊重・per-origin レート制御・破壊的リクエスト遮断
  （`src/crawler/politeness.py`）。
- **ローカル安全性**: 既定 127.0.0.1 バインド、localhost_guard / CSRF ガード。

## 5. 利用者・ワークスペース要件（オプトイン）

`WEBSPEC2DOC_AUTH` 有効時のみ。詳細は `docs/design/auth-tenant-integration.md`。
- 利用者ログイン（メール自己申告・パスワードなし）／ワークスペース選択。
- **将来要件**: 外部 IdP（Google 等）連携、ワークスペース別データ物理分離
  （設計は `docs/design/workspace-data-separation.md`、実装は次期）。

## 6. 非機能要件

`WS2D-NF-001_非機能要件定義書.md` を参照。

## 7. 制約・前提

- LLM 連携（OpenAI）はオプション。未設定時はルールベースでフォールバック（`CONTEXT.md`）。
- 対応ブラウザ実行基盤: Playwright Chromium。
