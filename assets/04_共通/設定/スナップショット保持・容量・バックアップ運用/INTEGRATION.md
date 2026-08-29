# 組み込み手順: スナップショット保持・容量・バックアップ運用

| 項目 | 値 |
|---|---|
| feature_id | `snapshot_retention` |
| 版 | `20260829-5345533` |
| 生成元 | `WebSpec2Doc` @ `5345533` |
| 生成日時 (UTC) | 2026-08-29T07:50:12Z |
| リスク / 状態 | high / implemented |
| 同梱ファイル数 | 6 |
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

### ルート（API）（1 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `web/routes/admin.py` | 3348 | `a2ae89a447ea` |

### サービス / コア（2 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `web/services/retention.py` | 10026 | `5df7d7c3afe0` |
| `web/services/scheduler.py` | 21979 | `c49ab2c4bd7f` |

### UI（テンプレート・JS・CSS）（3 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `templates/partials/view-settings.html` | 39538 | `8df7d8ecb0f0` |
| `static/js/settings.js` | 46487 | `b14d55dfd0c8` |
| `static/css/settings-admin.css` | 3488 | `91f9a279ba03` |

## 2. 配線する

### 2-1. Blueprint を登録する

受け側の `web/__init__.py`（アプリケーションファクトリ）に追記する。

```python
from web.routes import admin
app.register_blueprint(admin.bp)
```

| Blueprint | url_prefix | 定義元 |
|---|---|---|
| `admin` | `/api/admin` | `web/routes/admin.py` |

### 2-2. SPA シェルに差し込む

受け側の `templates/index.html` に追記する（本リポジトリと同じ配線規約）。

```jinja
{% include 'partials/view-settings.html' %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/settings-admin.css') }}?v={{ _ver }}">
<script src="{{ url_for('static', filename='js/settings.js') }}?v={{ _ver }}"></script>
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

- `src/diff/snapshot.py`
- `web/auth.py`
- `web/config.py`
- `web/services/admin_audit.py`
- `web/services/metrics.py`
- `web/services/notifier.py`
- `web/tenancy.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `flask` | flask==3.1.3 |

### 3-3. 環境変数

- なし

### 3-4. 呼び出す API（受け側に実在が必要）

- `/api/admin/audit`
- `/api/admin/backup-guide`
- `/api/admin/retention`
- `/api/admin/storage`
- `/api/history`
- `/api/integrations`
- `/api/integrations/confluence`
- `/api/integrations/confluence/test`
- `/api/integrations/jira`
- `/api/integrations/jira/test`
- `/api/integrations/notion`
- `/api/integrations/notion/test`
- `/api/integrations/qualityforward`
- `/api/integrations/qualityforward/test`
- `/api/integrations/slack/test`
- `/api/integrations/teams`
- `/api/integrations/teams/test`
- `/api/integrations/webhook`
- `/api/settings`
- `/api/settings/allow-local`
- `/api/settings/clear-key`
- `/api/settings/llm-models`
- `/api/settings/test-connection`
- `/api/settings/test-design`
- `/schedule/config`
- `/schedule/history`
- `/schedule/notify/test`

### 3-5. データファイル

- なし

### 3-6. 同梱外のテンプレート / 静的ファイル参照

- なし

### 3-7. 同梱 JS が参照するグローバル

他アセット由来のものが混ざっていれば、そのアセットも併せて受け渡す。

- なし

## 3-8. 併せて渡す必要のある他機能の資産

このアセットと対で動くが、**別の機能契約に属している**ファイル。
受け側に無ければ、その機能のアセットも別途エクスポートして渡す。

- なし

## 4. このアセットが提供する API

| メソッド | ルール | 定義元 |
|---|---|---|
| GET | `/storage` | `web/routes/admin.py` |
| GET | `/backup-guide` | `web/routes/admin.py` |
| GET | `/audit` | `web/routes/admin.py` |
| GET | `/retention` | `web/routes/admin.py` |
| PUT | `/retention` | `web/routes/admin.py` |

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `retention.json`
- `storage usage API`
- `retention.snapshots_pruned audit event`

### 永続化

- `instance/tenants/{slug}/retention.json`
- `output/tenants/{slug}/{domain}/snapshots/`

### 失敗経路（すべて実際に踏むこと）

- invalid_policy
- malformed_policy
- symlink_escape
- gc_io_failure

### 対応テスト

- `happy_path`
- `error_path`
- `tenant_isolation`
- `symlink_boundary`
- `evidence`

## 6. 未検証事項（エクスポート側の申告）

- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる
  URL・実行時にのみ解決される参照は検出できない。
- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**
  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。
- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。
