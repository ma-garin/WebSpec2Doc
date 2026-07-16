# WS2D-DD-001 データ設計書

- 版数: 1.0 / 作成日: 2026-07-16 / 準拠: IPA 共通フレーム（データ設計）
- 分離の将来設計は `docs/design/workspace-data-separation.md`。

## 1. データ配置一覧

| データ | 場所 | 形式 | 主キー | 説明 |
|---|---|---|---|---|
| クロール成果物 | `output/{domain}/` | ファイル群 | domain | サイト単位の生成物 |
| サイト認証セッション | `output/{domain}/auth.json` | JSON | domain | Cookie 等（**PW 本体は持たない**） |
| 探索セッション | `output/{domain}/sessions/session_*.jsonl` | JSONL | 連番 | 記録した操作列 |
| 監査ログ | `output/{domain}/audit.jsonl` | JSONL | 追記 | クロール礼儀・遮断の記録 |
| 観点管理 | `instance/viewpoints.db`（共有）/ `instance/tenants/{slug}/viewpoints.db`（テナント） | SQLite | set_id/item_id | 観点セット・版・アイテム・割当・提案（DB-per-tenant） |
| テスト設計設定 | `instance/test_design_settings.json` | JSON | － | 生成条件 |
| 認証（利用者/テナント/セッション/トークン/監査） | `instance/auth.db` | SQLite | 各テーブルキー | 全テナント共通の認証DB（下記 §3） |
| 観点テンプレート | `data/viewpoint_templates/*.json` | JSON | key | 全テナント共有参照（istqb/iso25010/nfr2018/pmbok） |

- パス定数は `web/config.py`（`OUTPUT_DIR` / `VIEWPOINTS_DB` / `TEST_DESIGN_SETTINGS_FILE`）に集約。環境変数で上書き可能。
- テナント有効時は `web/tenancy.py: scoped_output_dir() / scoped_instance_path()` が保存先を
  `output/tenants/{slug}/{domain}/` ・ `instance/tenants/{slug}/` に切り替える（slug はパス構築前に
  `^[a-z0-9][a-z0-9-]{0,31}$` で再検証しトラバーサルを防止）。詳細は `docs/AUTH_TENANCY.md`。

## 2. `output/{domain}/` の主な成果物

- `report.json`（正本・全解析結果）/ `report.html`（人間可読レポート）
- `screens.md`（画面別仕様）/ `forms.md`（フォーム項目）/ `transition.mmd`（遷移図 Mermaid）
- `spec.xlsx`（Excel）/ `screenshots/P*.png`（画面証跡）/ `sessions/`, `audit.jsonl`

`report.json` スキーマ概要: `meta`（target_url, crawled_at, screen_count 等）＋
`screens[]`（page_id, title, url, headings, buttons, forms[], transitions）。

## 3. 認証DB（`instance/auth.db` / `web/services/auth_store.py`）

商用/共有サーバ向け認証（`account_auth`）とテナント分離（`tenant_isolation`）の永続化。
主なテーブル: ユーザー（email・パスワードhash＝scrypt・ロール owner/admin/member）／
テナント（slug・名称）／メンバーシップ／`auth_sessions`（トークンの SHA-256 のみ保存・
既定12h失効）／`api_tokens`（`/api/v1` 用・SHA-256 のみ）／`audit_log`（ログイン・
ユーザー変更・トークン発行の監査）。詳細仕様は `docs/AUTH_TENANCY.md`。

## 4. 保持・バックアップ

- `instance/` `output/` は gitignore（環境ローカル）。バックアップ対象。
- 削除: サイト削除 API（`DELETE /api/site/<domain>`）で対象ディレクトリを除去。
- テナント有効時のクロール成果物は `output/tenants/{slug}/{domain}/`、観点DBは
  `instance/tenants/{slug}/viewpoints.db`（DB-per-tenant）。既存データの移行は手動
  （`docs/AUTH_TENANCY.md` 既知の制約）。

## 5. データ保護

- サイト認証の ID/PW は送信のみで即破棄、保存しない（ADR-0002）。
- 利用者パスワードは werkzeug（scrypt）でハッシュ化。セッションクッキー `ws2d_session` は
  ランダムトークンのみ（HttpOnly / SameSite=Lax）。
- secret_key は `WEBSPEC2DOC_SECRET_KEY` → `instance/secret_key`（0600 自動生成）の順で解決。
