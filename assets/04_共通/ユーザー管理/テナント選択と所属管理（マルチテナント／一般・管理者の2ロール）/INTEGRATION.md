# 組み込み手順: テナント選択と所属管理（マルチテナント／一般・管理者の2ロール）

| 項目 | 値 |
|---|---|
| feature_id | `tenant_membership` |
| 版 | `20260829-34d52a3` |
| 生成元 | `WebSpec2Doc` @ `34d52a3` |
| 生成日時 (UTC) | 2026-08-29T09:32:19Z |
| リスク / 状態 | critical / implemented |
| 同梱ファイル数 | 13 |
| 生成時の作業ツリー | **未コミットの変更あり**（再現性が落ちる。コミット後の再生成を推奨） |

## 0. 先に検証する

配置の前にバンドルの完全性を確認する。SHA-256 が 1 つでも合わなければ、
転送か展開が壊れているので配置しない。

```bash
python3 scripts/verify_feature_asset.py <このディレクトリ>
# 受け側リポジトリの依存充足も見る場合
python3 scripts/verify_feature_asset.py <このディレクトリ> --against <受け側リポジトリのルート>
```

## 1. ファイルを配置する

`files/` 配下は **リポジトリ相対パスをそのまま保持** している。配置先はパスそのもの。

```bash
rsync -a files/ <受け側リポジトリのルート>/
```

### ルート（API）（2 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `web/routes/tenant_admin.py` | 7539 | `be05d9ed30f2` |
| `web/routes/account.py` | 15585 | `b8080ea17977` |

### サービス / コア（2 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `web/services/auth_store.py` | 57641 | `77d943ff7550` |
| `web/auth.py` | 9885 | `d4a8a25cb642` |

### UI（テンプレート・JS・CSS）（9 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `templates/auth/tenant.html` | 2761 | `dfea6638c68c` |
| `templates/partials/view-user-management.html` | 3298 | `6f48539fdf67` |
| `templates/partials/modal-user-admin.html` | 4845 | `97a60c6ec319` |
| `templates/partials/view-tenant-management.html` | 2796 | `4c362fed8844` |
| `templates/partials/modal-tenant-admin.html` | 3457 | `1d3a01832190` |
| `static/css/tenant-auth.css` | 7971 | `a7d65cfe6c66` |
| `static/css/account-view.css` | 11800 | `5964be2979da` |
| `static/js/user-admin-view.js` | 11802 | `4cdf0724b5c7` |
| `static/js/tenant-admin-view.js` | 6116 | `9373b4bd792f` |

## 2. 配線する

### 2-1. Blueprint を登録する

受け側の `web/__init__.py`（アプリケーションファクトリ）に追記する。

```python
from web.routes import account, tenant_admin
app.register_blueprint(account.bp)
app.register_blueprint(tenant_admin.bp)
```

| Blueprint | url_prefix | 定義元 |
|---|---|---|
| `tenant_admin` | `(なし)` | `web/routes/tenant_admin.py` |
| `account` | `(なし)` | `web/routes/account.py` |

### 2-2. SPA シェルに差し込む

受け側の `templates/index.html` に追記する（本リポジトリと同じ配線規約）。

```jinja
{% include 'auth/tenant.html' %}
{% include 'partials/view-user-management.html' %}
{% include 'partials/modal-user-admin.html' %}
{% include 'partials/view-tenant-management.html' %}
{% include 'partials/modal-tenant-admin.html' %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/tenant-auth.css') }}?v={{ _ver }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/account-view.css') }}?v={{ _ver }}">
<script src="{{ url_for('static', filename='js/user-admin-view.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/tenant-admin-view.js') }}?v={{ _ver }}"></script>
```

`?v={{ _ver }}` は本リポジトリのキャッシュバスター。受け側に同等の仕組みが
なければ外す。**外すと JS / CSS の古いキャッシュを掴む**ため、代替を用意すること。

### 2-3. 機能契約を登録する

受け側でも完了判定を機械化する場合は、`contract.json` の内容を受け側の
`quality/feature_contracts.yml` の `features` に追加する。
**feature_id はそのまま流用せず、受け側の体系で付け直す**
（`docs/common-assets-docs-vs-testlab.md` 第 3 節: 契約の形式は共用してよいが中身は各システム固有）。

## 3. 同梱していない依存（受け側に必要なもの）

ここが埋まらないとアセットは動かない。配置前に 1 つずつ確認する。

### 3-1. 内部モジュール（同梱外）

同梱ファイルが import しているが、このアセットには含まれないもの。
受け側に同名・同パスで実在する必要がある。

- `web/config.py`
- `web/services/admin_audit.py`
- `web/tenancy.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `flask` | flask==3.1.3 |
| `werkzeug` | **本リポジトリの requirements.txt に記載なし・要確認** |

### 3-3. 環境変数

- なし

### 3-4. 呼び出す API（受け側に実在が必要）

- `/api/admin/tenancy`
- `/api/admin/tenancy/tenants`
- `/api/admin/tenancy/tenants/`
- `/api/admin/tenancy/users`
- `/api/admin/tenancy/users/`

### 3-5. データファイル

- なし

### 3-6. 同梱外のテンプレート / 静的ファイル参照

- `auth/_shell.html`

### 3-7. 同梱 JS が参照するグローバル

他アセット由来のものが混ざっていれば、そのアセットも併せて受け渡す。

- なし

## 3-8. 併せて渡す必要のある他機能の資産

このアセットと対で動くが、**別の機能契約に属している**ファイル。
受け側に無ければ、その機能のアセットも別途エクスポートして渡す。

| ファイル | 所属する機能 | 関係 |
|---|---|---|
| `templates/auth/_shell.html` | `account_auth` | 同梱の `static/css/tenant-auth.css` を差し込んでいるが未同梱 |
| `templates/auth/login.html` | `account_auth` | 同梱の `static/css/tenant-auth.css` を差し込んでいるが未同梱 |

## 4. このアセットが提供する API

| メソッド | ルール | 定義元 |
|---|---|---|
| GET | `/admin/console` | `web/routes/tenant_admin.py` |
| GET | `/api/admin/tenancy` | `web/routes/tenant_admin.py` |
| POST | `/api/admin/tenancy/tenants` | `web/routes/tenant_admin.py` |
| PATCH | `/api/admin/tenancy/tenants/<tenant_id>` | `web/routes/tenant_admin.py` |
| DELETE | `/api/admin/tenancy/tenants/<tenant_id>` | `web/routes/tenant_admin.py` |
| POST | `/api/admin/tenancy/users` | `web/routes/tenant_admin.py` |
| PUT | `/api/admin/tenancy/users/<user_id>/memberships` | `web/routes/tenant_admin.py` |
| PATCH | `/api/admin/tenancy/users/<user_id>` | `web/routes/tenant_admin.py` |
| POST | `/api/admin/tenancy/users/<user_id>/password` | `web/routes/tenant_admin.py` |
| DELETE | `/api/admin/tenancy/users/<user_id>` | `web/routes/tenant_admin.py` |
| GET | `/auth/login` | `web/routes/account.py` |
| POST | `/auth/login` | `web/routes/account.py` |
| GET | `/auth/signup` | `web/routes/account.py` |
| POST | `/auth/signup` | `web/routes/account.py` |
| POST | `/auth/logout` | `web/routes/account.py` |
| GET | `/auth/setup` | `web/routes/account.py` |
| POST | `/auth/setup` | `web/routes/account.py` |
| GET | `/auth/account` | `web/routes/account.py` |
| GET | `/api/auth/me` | `web/routes/account.py` |
| GET | `/api/auth/tenants` | `web/routes/account.py` |
| GET | `/api/onboarding` | `web/routes/account.py` |
| POST | `/api/onboarding/complete` | `web/routes/account.py` |
| POST | `/api/auth/password` | `web/routes/account.py` |
| GET | `/api/auth/users` | `web/routes/account.py` |
| POST | `/api/auth/users` | `web/routes/account.py` |
| PATCH | `/api/auth/users/<user_id>` | `web/routes/account.py` |
| GET | `/api/auth/api-tokens` | `web/routes/account.py` |
| POST | `/api/auth/api-tokens` | `web/routes/account.py` |
| DELETE | `/api/auth/api-tokens/<token_id>` | `web/routes/account.py` |

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `tenant selection page`
- `admin console page`
- `/api/admin/tenancy/* JSON`
- `audit_log`

### 永続化

- `instance/auth.db`

### 失敗経路（すべて実際に踏むこと）

- no_membership_blocks_work
- tenant_not_selected_redirect
- not_a_member_rejected
- last_admin_protection
- last_tenant_cannot_be_deleted
- non_admin_forbidden

### 対応テスト

- `happy_path`
- `error_path`
- `evidence`

## 6. 未検証事項（エクスポート側の申告）

- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる
  URL・実行時にのみ解決される参照は検出できない。
- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**
  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。
- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。
