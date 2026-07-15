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
| 観点管理 | `instance/viewpoints.db` | SQLite | set_id/item_id | 観点セット・版・アイテム・割当・提案 |
| テスト設計設定 | `instance/test_design_settings.json` | JSON | － | 生成条件 |
| 利用者 | `instance/auth/users.json` | JSON | email | メール識別 |
| ワークスペース | `instance/auth/tenants.json` | JSON | id | 作業単位 |
| メンバーシップ | `instance/auth/memberships.json` | JSON | (email, tenant_id) | 所属・ロール |
| 観点テンプレート | `data/viewpoint_templates/*.json` | JSON | key | 全テナント共有参照（istqb/iso25010/nfr2018/pmbok） |

パス定数は `web/config.py`（`OUTPUT_DIR` / `VIEWPOINTS_DB` / `TEST_DESIGN_SETTINGS_FILE`）に集約。
環境変数で上書き可能。

## 2. `output/{domain}/` の主な成果物

- `report.json`（正本・全解析結果）/ `report.html`（人間可読レポート）
- `screens.md`（画面別仕様）/ `forms.md`（フォーム項目）/ `transition.mmd`（遷移図 Mermaid）
- `spec.xlsx`（Excel）/ `screenshots/P*.png`（画面証跡）/ `sessions/`, `audit.jsonl`

`report.json` スキーマ概要: `meta`（target_url, crawled_at, screen_count 等）＋
`screens[]`（page_id, title, url, headings, buttons, forms[], transitions）。

## 3. 認証データモデル（`web/auth/models.py`）

- `User(email, created_at, last_login_at)`
- `Tenant(id, name, created_at)`
- `Membership(user_email, tenant_id, role)` role ∈ {owner, admin, member}

すべて `frozen=True` dataclass（イミュータブル）。JSON 永続化は原子的書き込み（tmp→replace）。

## 4. 保持・バックアップ

- `instance/` `output/` は gitignore（環境ローカル）。バックアップ対象。
- 削除: サイト削除 API（`DELETE /api/site/<domain>`）で `output/{domain}` を除去。
- 将来のワークスペース分離では `output/{tenant_id}/{domain}/` へ名前空間化
  （`docs/design/workspace-data-separation.md` 推奨案）。

## 5. データ保護

- サイト認証の ID/PW は送信のみで即破棄、保存しない（ADR-0002）。
- secret_key は `instance/auth/secret.key`（0600）または `WEBSPEC2DOC_SECRET_KEY`。
