# WS2D-PD-001 DB物理設計書

- 版数: 1.0 / 作成日: 2026-08-02 / 準拠: IPA 共通フレーム（データベース物理設計）
- 正本: `docs/sdlc/_asbuilt/schema.sql`（機械抽出DDL）。本書はこれをそのまま転記・注釈する。
- DBMS: SQLite 3。ファイル2本 — `instance/auth.db`（利用者認証・テナント）、
  `instance/viewpoints.db`（テスト観点）。
- 実測コマンド: `ls -la instance/*.db`（2026-08-02実行）
  → `auth.db` 106,496 bytes（約104KB）、`viewpoints.db` 23,310,336 bytes（約22.2MB）。

## 1. テーブル定義（auth.db）

### 1.1 `users`（論理名: 利用者）

用途: アプリ利用者アカウント（メール・パスワードハッシュ・ロック状態）。

| カラム | 型 | NULL | デフォルト | 制約 | 説明 |
|---|---|---|---|---|---|
| id | TEXT | NOT NULL | — | PK | 利用者ID |
| email | TEXT | NOT NULL | — | UNIQUE | ログインメール |
| name | TEXT | NOT NULL | — | | 表示名 |
| password_hash | TEXT | NOT NULL | `''` | | パスワードハッシュ（パスワードレス利用者は空） |
| is_active | INTEGER | NOT NULL | 1 | | 有効フラグ |
| failed_attempts | INTEGER | NOT NULL | 0 | | ログイン失敗回数 |
| locked_until | TEXT | NULL可 | — | | ロック解除時刻（ISO8601） |
| last_login_at | TEXT | NULL可 | — | | 最終ログイン時刻 |
| tour_completed_at | TEXT | NULL可 | — | | v2マイグレーションで追加。初回ツアー完了時刻 |
| created_at | TEXT | NOT NULL | — | | 作成日時 |
| updated_at | TEXT | NOT NULL | — | | 更新日時 |

### 1.2 `tenants`（論理名: テナント）

用途: マルチテナントの区画単位。

| カラム | 型 | NULL | デフォルト | 制約 | 説明 |
|---|---|---|---|---|---|
| id | TEXT | NOT NULL | — | PK | テナントID |
| name | TEXT | NOT NULL | — | | 表示名 |
| slug | TEXT | NOT NULL | — | UNIQUE | URLセーフな識別子 |
| created_at | TEXT | NOT NULL | — | | 作成日時 |
| updated_at | TEXT | NOT NULL | — | | 更新日時 |

### 1.3 `memberships`（論理名: テナント所属）

用途: 利用者とテナントの多対多関係とロール。

| カラム | 型 | NULL | デフォルト | 制約 | 説明 |
|---|---|---|---|---|---|
| id | TEXT | NOT NULL | — | PK | 所属ID |
| user_id | TEXT | NOT NULL | — | FK→users.id | 利用者 |
| tenant_id | TEXT | NOT NULL | — | FK→tenants.id | テナント |
| role | TEXT | NOT NULL | — | CHECK IN('member','admin') | ロール |
| created_at | TEXT | NOT NULL | — | | 作成日時 |
| （複合） | | | | UNIQUE(user_id, tenant_id) | 同一利用者の同一テナント重複所属を禁止 |

### 1.4 `api_tokens`（論理名: APIトークン）

用途: プログラム的アクセス用の発行トークン（ハッシュ保存）。

| カラム | 型 | NULL | デフォルト | 制約 | 説明 |
|---|---|---|---|---|---|
| id | TEXT | NOT NULL | — | PK | トークンID |
| tenant_id | TEXT | NOT NULL | — | FK→tenants.id | 発行先テナント |
| name | TEXT | NOT NULL | — | | トークン名 |
| token_hash | TEXT | NOT NULL | — | UNIQUE | トークンのハッシュ値 |
| created_by | TEXT | NULL可 | — | FK→users.id | 発行者 |
| created_at | TEXT | NOT NULL | — | | 発行日時 |
| last_used_at | TEXT | NULL可 | — | | 最終使用日時 |
| revoked_at | TEXT | NULL可 | — | | 失効日時 |
| scope | TEXT | NOT NULL | `'full'` | | v3マイグレーションで追加。権限範囲 |

### 1.5 `auth_sessions`（論理名: 認証セッション）

用途: ログインセッション（トークンハッシュで照合）。

| カラム | 型 | NULL | デフォルト | 制約 | 説明 |
|---|---|---|---|---|---|
| id | TEXT | NOT NULL | — | PK | セッションID |
| user_id | TEXT | NOT NULL | — | FK→users.id | 利用者 |
| token_hash | TEXT | NOT NULL | — | UNIQUE | セッショントークンのハッシュ |
| created_at | TEXT | NOT NULL | — | | 作成日時 |
| expires_at | TEXT | NOT NULL | — | | 有効期限 |
| last_seen_at | TEXT | NOT NULL | — | | 最終アクセス時刻 |
| revoked_at | TEXT | NULL可 | — | | 失効日時 |
| tenant_id | TEXT | NULL可 | — | | v4マイグレーションで追加。選択中テナント |

### 1.6 `audit_log`（論理名: 監査ログ）

用途: 認証・アカウント操作の監査証跡。

| カラム | 型 | NULL | デフォルト | 制約 | 説明 |
|---|---|---|---|---|---|
| id | INTEGER | NOT NULL | — | PK AUTOINCREMENT | 連番 |
| at | TEXT | NOT NULL | — | | 発生日時 |
| event | TEXT | NOT NULL | — | | イベント種別 |
| user_id | TEXT | NULL可 | — | | 実行者 |
| tenant_id | TEXT | NULL可 | — | | 対象テナント |
| detail | TEXT | NOT NULL | `''` | | 詳細（JSON文字列等） |

## 2. テーブル定義（viewpoints.db）

### 2.1 `viewpoint_sets`（論理名: 観点セット）

用途: テスト観点の集合（親子関係・優先度・有効/無効を持つ）。

| カラム | 型 | NULL | デフォルト | 制約 | 説明 |
|---|---|---|---|---|---|
| id | TEXT | NOT NULL | — | PK | セットID |
| name | TEXT | NOT NULL | — | | 名称 |
| description | TEXT | NOT NULL | `''` | | 説明 |
| parent_set_id | TEXT | NULL可 | — | FK→viewpoint_sets.id（自己参照） | 親セット |
| state | TEXT | NOT NULL | `'active'` | | 状態 |
| is_default | INTEGER | NOT NULL | 0 | | 既定セットか |
| priority | INTEGER | NOT NULL | 0 | | 優先度 |
| revision | INTEGER | NOT NULL | 1 | | 楽観ロック用リビジョン |
| deleted_at | TEXT | NULL可 | — | | 論理削除日時 |
| created_at | TEXT | NOT NULL | — | | 作成日時 |
| updated_at | TEXT | NOT NULL | — | | 更新日時 |
| applicability | TEXT | NOT NULL | `'{}'` | | v4マイグレーションで追加。適用条件JSON |

### 2.2 `viewpoint_versions`（論理名: 観点バージョン）

用途: セットの版管理（draft/published/archived）。

| カラム | 型 | NULL | デフォルト | 制約 | 説明 |
|---|---|---|---|---|---|
| id | TEXT | NOT NULL | — | PK | バージョンID |
| set_id | TEXT | NOT NULL | — | FK→viewpoint_sets.id | 所属セット |
| version_number | INTEGER | NOT NULL | — | | 版番号 |
| status | TEXT | NOT NULL | — | CHECK IN('draft','published','archived') | 状態 |
| change_reason | TEXT | NOT NULL | `''` | | 変更理由 |
| checksum | TEXT | NOT NULL | `''` | | 内容チェックサム |
| based_on_version_id | TEXT | NULL可 | — | FK→viewpoint_versions.id（自己参照） | 派生元バージョン |
| published_at | TEXT | NULL可 | — | | 公開日時 |
| revision | INTEGER | NOT NULL | 1 | | 楽観ロック用リビジョン |
| created_at | TEXT | NOT NULL | — | | 作成日時 |
| updated_at | TEXT | NOT NULL | — | | 更新日時 |
| （複合） | | | | UNIQUE(set_id, version_number) | セット内の版番号一意性 |

### 2.3 `viewpoint_items`（論理名: 観点項目）

用途: 個々のテスト観点（カテゴリ・リスク重み・技法等、QualityForward互換カラムを含む）。

| カラム | 型 | NULL | デフォルト | 制約 | 説明 |
|---|---|---|---|---|---|
| id | TEXT | NOT NULL | — | PK | 項目ID |
| version_id | TEXT | NOT NULL | — | FK→viewpoint_versions.id ON DELETE CASCADE | 所属バージョン |
| persistent_key | TEXT | NOT NULL | — | UNIQUE(version_id, persistent_key) | 版をまたぐ永続キー |
| name | TEXT | NOT NULL | — | | 項目名 |
| category | TEXT | NOT NULL | — | | カテゴリ |
| purpose | TEXT | NOT NULL | `''` | | 目的 |
| trigger_rule | TEXT | NOT NULL | `'{}'` | | 適用トリガー（JSON） |
| recommended_checks | TEXT | NOT NULL | `''` | | 推奨チェック内容 |
| risk_weight | INTEGER | NOT NULL | 3 | CHECK BETWEEN 1 AND 5 | リスク重み |
| automation | TEXT | NOT NULL | `'manual'` | | 自動化区分 |
| standards | TEXT | NOT NULL | `''` | | 準拠規格 |
| tags | TEXT | NOT NULL | `'[]'` | | タグ（JSON配列） |
| enabled | INTEGER | NOT NULL | 1 | | 有効フラグ |
| node_type | TEXT | NOT NULL | `'viewpoint'` | | ノード種別（階層表現用） |
| parent_key | TEXT | NULL可 | NULL | | 親項目キー |
| sort_order | INTEGER | NOT NULL | 0 | | 表示順 |
| revision | INTEGER | NOT NULL | 1 | | 楽観ロック用リビジョン |
| deleted_at | TEXT | NULL可 | — | | 論理削除日時 |
| created_at | TEXT | NOT NULL | — | | 作成日時 |
| updated_at | TEXT | NOT NULL | — | | 更新日時 |
| expected_result | TEXT | NOT NULL | `''` | | 期待結果 |
| evidence | TEXT | NOT NULL | `''` | | 根拠 |
| technique | TEXT | NOT NULL | `''` | | テスト技法 |
| test_level | TEXT | NOT NULL | `''` | | テストレベル |

### 2.4 `viewpoint_proposals`（論理名: 観点提案）

用途: LLM等からの追加提案（承認/却下待ち）。

| カラム | 型 | NULL | デフォルト | 制約 | 説明 |
|---|---|---|---|---|---|
| id | TEXT | NOT NULL | — | PK | 提案ID |
| set_id | TEXT | NOT NULL | — | FK→viewpoint_sets.id | 対象セット |
| version_id | TEXT | NULL可 | — | FK→viewpoint_versions.id | 対象バージョン |
| payload | TEXT | NOT NULL | — | | 提案内容（JSON） |
| rationale | TEXT | NOT NULL | — | | 根拠説明 |
| confidence | REAL | NOT NULL | — | CHECK BETWEEN 0 AND 1 | 確信度 |
| duplicate_key | TEXT | NOT NULL | `''` | | 重複検出キー |
| status | TEXT | NOT NULL | — | CHECK IN('pending','adopted','rejected') | 処理状態 |
| revision | INTEGER | NOT NULL | 1 | | 楽観ロック用リビジョン |
| created_at | TEXT | NOT NULL | — | | 作成日時 |
| updated_at | TEXT | NOT NULL | — | | 更新日時 |

### 2.5 `viewpoint_assignments`（論理名: 観点割当ルール）

用途: セットを対象（サイト等）に割り当てる規則。

| カラム | 型 | NULL | デフォルト | 制約 | 説明 |
|---|---|---|---|---|---|
| id | TEXT | NOT NULL | — | PK | 割当ID |
| set_id | TEXT | NOT NULL | — | FK→viewpoint_sets.id | 対象セット |
| rule | TEXT | NOT NULL | — | | 割当規則 |
| priority | INTEGER | NOT NULL | 0 | | 優先度 |
| enabled | INTEGER | NOT NULL | 1 | | 有効フラグ |
| revision | INTEGER | NOT NULL | 1 | | 楽観ロック用リビジョン |
| deleted_at | TEXT | NULL可 | — | | 論理削除日時 |
| created_at | TEXT | NOT NULL | — | | 作成日時 |
| updated_at | TEXT | NOT NULL | — | | 更新日時 |

## 3. インデックス一覧

| インデックス名 | 対象テーブル | 対象カラム | 種別 | 目的 |
|---|---|---|---|---|
| ix_api_tokens_tenant | api_tokens | tenant_id | 通常 | テナント別トークン一覧の高速化 |
| ix_memberships_tenant | memberships | tenant_id | 通常 | テナント別メンバー一覧の高速化 |
| ix_memberships_user | memberships | user_id | 通常 | 利用者別所属一覧の高速化 |
| ix_sessions_user | auth_sessions | user_id | 通常 | 利用者別セッション一覧の高速化 |
| ix_viewpoint_items_version | viewpoint_items | version_id | 通常 | バージョン別項目一覧の高速化 |
| ix_viewpoint_versions_set | viewpoint_versions | set_id, version_number DESC | 通常 | セット別最新版の高速取得 |
| uq_viewpoint_draft | viewpoint_versions | set_id（WHERE status='draft'） | 一意（部分索引） | 1セットにつき draft は同時に1件のみを強制 |
| uq_viewpoint_set_name_active | viewpoint_sets | lower(name)（WHERE deleted_at IS NULL） | 一意（部分索引） | 論理削除されていないセット名の大小無視重複を防止 |

## 4. 制約一覧と参照整合性方針

**PK**: 全テーブル `id`（`audit_log` のみ `INTEGER AUTOINCREMENT`、他は `TEXT`=UUID相当の文字列キー）。

**FK**:
- `api_tokens.tenant_id → tenants.id`、`api_tokens.created_by → users.id`
- `auth_sessions.user_id → users.id`
- `memberships.user_id → users.id`、`memberships.tenant_id → tenants.id`
- `viewpoint_items.version_id → viewpoint_versions.id`（`ON DELETE CASCADE` — バージョン削除で項目も連動削除）
- `viewpoint_proposals.set_id → viewpoint_sets.id`、`viewpoint_proposals.version_id → viewpoint_versions.id`
- `viewpoint_assignments.set_id → viewpoint_sets.id`
- `viewpoint_sets.parent_set_id → viewpoint_sets.id`（自己参照）
- `viewpoint_versions.set_id → viewpoint_sets.id`、`viewpoint_versions.based_on_version_id → viewpoint_versions.id`（自己参照）

**UNIQUE**: `api_tokens.token_hash`、`auth_sessions.token_hash`、`tenants.slug`、`users.email`、
`memberships(user_id, tenant_id)`、`viewpoint_items(version_id, persistent_key)`、
`viewpoint_versions(set_id, version_number)`、および3章の部分ユニークインデックス2件。

**CHECK**: `memberships.role IN('member','admin')`、`viewpoint_items.risk_weight BETWEEN 1 AND 5`、
`viewpoint_proposals.confidence BETWEEN 0 AND 1`、`viewpoint_proposals.status IN('pending','adopted','rejected')`、
`viewpoint_versions.status IN('draft','published','archived')`。

**参照整合性の方針**: SQLiteは既定でFK制約チェックが無効なため、両ストアとも接続確立直後に
`PRAGMA foreign_keys = ON` を明示発行して有効化している（実測: `auth_store.py:162`,
`viewpoint_store.py:183`）。`auth_store.py` の `_migrate_v4` のみ、テーブル再構築
（`users` → `users_v4` へのRENAME等）の間だけ一時的に `PRAGMA foreign_keys = OFF` にし、
完了後 `ON` へ戻す（`auth_store.py:277, 322`）。

## 5. 物理設計上の考慮

**同時実行制御・WAL**（実測: `grep -n "journal_mode\|PRAGMA" web/services/auth_store.py
web/services/viewpoint_store.py`）:
- 両DBとも journal_mode を **WAL（Write-Ahead Logging）** に設定。`auth_store.py` は接続時に
  無条件で `PRAGMA journal_mode = WAL` を発行。`viewpoint_store.py` は現在のモードを確認し
  WALでなければ切り替える（コード注釈: 「他の接続が開いているとSQLITE_BUSYになるため、
  誰か1つが切り替えれば足りる」設計）。
- `busy_timeout`: `auth_store.py` は 5,000ms、`viewpoint_store.py` は 10,000ms。ロック競合時は
  即座にエラーとせず、この時間内はリトライ待機する。
- `isolation_level=None`（自動コミットモード）で接続し、個々の操作内でトランザクション制御。

**バックアップ方式**（`docs/OPERATIONS_BACKUP.md` 準拠。本書と整合）:
- バックアップ対象は `output/` と `instance/` を必ず対で扱う（片方だけの復元は認証・テナント・
  保持設定との不整合を招くため禁止）。
- プロセス停止後のコールドバックアップのみ（稼働中コピーは行わない）。
- `tar -czf` → `shasum -a 256` でチェックサムを保存し、暗号化ストレージへ複製。
- 復旧時はチェックサム検証 → 展開 → 現データを退避してから対で入替。
- 四半期ごとのリストア演習を推奨（`docs/OPERATIONS_BACKUP.md` 記載）。

**想定データ量と増加率**: 開発環境での実測値（2026-08-02、`sqlite3 instance/xxx.db
"select count(*) from ..."`）は以下の通り。

| DB | テーブル | 件数 |
|---|---|---|
| auth.db | users | 3 |
| auth.db | tenants | 2 |
| auth.db | memberships | 4 |
| auth.db | api_tokens | 0 |
| auth.db | auth_sessions | 4 |
| auth.db | audit_log | 9 |
| viewpoints.db | viewpoint_sets | 142 |
| viewpoints.db | viewpoint_versions | 149 |
| viewpoints.db | viewpoint_items | 14,352 |
| viewpoints.db | viewpoint_assignments | 0 |
| viewpoints.db | viewpoint_proposals | 0 |

本番運用時の想定データ量・増加率は入手資料の範囲では**未確認**。`viewpoint_items` は
開発環境で既に14,352件あり、テナント数・サイト数に比例して線形増加する設計（`version_id`
経由でセット→バージョン→項目と連なる）と推測されるが、増加率の実測値は無い。

## 6. マイグレーション方式

両ストアとも専用マイグレーションツール（Alembic等）は使用せず、**`PRAGMA user_version` による
アプリ内蔵のインクリメンタルマイグレーション**を自前実装している（実測:
`grep -n "_migrate\|ALTER TABLE\|user_version" web/services/auth_store.py
web/services/viewpoint_store.py`）。現在の到達バージョンは両DBとも `user_version = 4`
（実測: `sqlite3 instance/auth.db "PRAGMA user_version;"` → 4、`viewpoints.db` も4）。

**`auth_store.py`**:
- 接続確立時に現在の `user_version` を読み取り、目標まで順に適用。
- v1→v2: `ALTER TABLE users ADD COLUMN tour_completed_at TEXT`
- v2→v3: `ALTER TABLE api_tokens ADD COLUMN scope TEXT NOT NULL DEFAULT 'full'`
- v3→v4（`_migrate_v4`）: `ALTER TABLE auth_sessions ADD COLUMN tenant_id TEXT` に加え、
  `users` テーブルの再構築（`ALTER TABLE users_v4 RENAME TO users` を含む）を実施。この間のみ
  `PRAGMA foreign_keys = OFF`。

**`viewpoint_store.py`**:
- `_add_columns(conn, table, columns)` ヘルパーが `PRAGMA table_info(table)` で既存カラムを
  確認し、無ければ `ALTER TABLE {table} ADD COLUMN {definition}` を発行（冪等）。
- `_migrate_v1_to_v2` / `_migrate_v2_to_v3` / `_migrate_v3_to_v4` を順次適用。
  v3→v4 で `viewpoint_sets.applicability TEXT NOT NULL DEFAULT '{}'` を追加。
- 各段階完了後 `PRAGMA user_version = N` を発行。

## 改訂履歴

| 版 | 日付 | 内容 | 作成者 |
|---|---|---|---|
| 1.0 | 2026-08-02 | 初版作成 | 開発チーム |
