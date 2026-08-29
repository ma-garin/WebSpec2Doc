# 組み込み手順: 管理操作のテナント監査ログ

| 項目 | 値 |
|---|---|
| feature_id | `admin_audit` |
| 版 | `20260829-34d52a3` |
| 生成元 | `WebSpec2Doc` @ `34d52a3` |
| 生成日時 (UTC) | 2026-08-29T09:32:20Z |
| リスク / 状態 | high / implemented |
| 同梱ファイル数 | 12 |
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

### ルート（API）（6 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `web/routes/admin.py` | 3348 | `a2ae89a447ea` |
| `web/routes/report.py` | 24514 | `f1b9d3e492af` |
| `web/routes/review.py` | 6386 | `d79e5ce673d7` |
| `web/routes/schedule.py` | 13381 | `49e5f38f2154` |
| `web/routes/settings.py` | 8583 | `8188369acf08` |
| `web/routes/viewpoints.py` | 11748 | `72e44c9252af` |

### サービス / コア（3 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `web/services/admin_audit.py` | 5876 | `c7ac7cebf500` |
| `web/audit_context.py` | 1196 | `85c7e9676c3c` |
| `web/services/auth_store.py` | 57641 | `77d943ff7550` |

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
from web.routes import admin, report, review, schedule, settings, viewpoints
app.register_blueprint(admin.bp)
app.register_blueprint(report.bp)
app.register_blueprint(review.bp)
app.register_blueprint(schedule.bp)
app.register_blueprint(settings.bp)
app.register_blueprint(viewpoints.bp)
```

| Blueprint | url_prefix | 定義元 |
|---|---|---|
| `admin` | `/api/admin` | `web/routes/admin.py` |
| `report` | `(なし)` | `web/routes/report.py` |
| `review` | `(なし)` | `web/routes/review.py` |
| `schedule` | `(なし)` | `web/routes/schedule.py` |
| `settings` | `(なし)` | `web/routes/settings.py` |
| `viewpoints` | `(なし)` | `web/routes/viewpoints.py` |

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

- `src/generator/feature_catalog.py`
- `src/generator/heatmap_reporter.py`
- `src/graph/state_table.py`
- `web/auth.py`
- `web/config.py`
- `web/env_store.py`
- `web/services/export_xlsx.py`
- `web/services/notifier.py`
- `web/services/openai_qa.py`
- `web/services/retention.py`
- `web/services/run_store.py`
- `web/services/scheduler.py`
- `web/services/spec_ts_generator.py`
- `web/services/test_design_settings.py`
- `web/services/viewpoint_proposals.py`
- `web/services/viewpoint_sources.py`
- `web/services/viewpoint_store.py`
- `web/services/viewpoint_templates.py`
- `web/summary.py`
- `web/tenancy.py`
- `web/validation.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `flask` | flask==3.1.3 |
| `werkzeug` | **本リポジトリの requirements.txt に記載なし・要確認** |

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
| GET | `/preview` | `web/routes/report.py` |
| GET | `/download` | `web/routes/report.py` |
| GET | `/api/export/spec-xlsx` | `web/routes/report.py` |
| GET | `/download-zip` | `web/routes/report.py` |
| GET | `/api/report/<domain>/spec-ts` | `web/routes/report.py` |
| POST | `/api/sample-report` | `web/routes/report.py` |
| GET | `/api/result` | `web/routes/report.py` |
| GET | `/api/state-table` | `web/routes/report.py` |
| GET | `/api/coverage-heatmap` | `web/routes/report.py` |
| GET | `/open` | `web/routes/report.py` |
| GET | `/review/cases` | `web/routes/review.py` |
| POST | `/review/update` | `web/routes/review.py` |
| GET | `/review/export` | `web/routes/review.py` |
| GET | `/schedule/config` | `web/routes/schedule.py` |
| POST | `/schedule/config` | `web/routes/schedule.py` |
| POST | `/schedule/run-now` | `web/routes/schedule.py` |
| GET | `/schedule/status` | `web/routes/schedule.py` |
| GET | `/schedule/history` | `web/routes/schedule.py` |
| POST | `/schedule/notify/test` | `web/routes/schedule.py` |
| GET | `/api/settings` | `web/routes/settings.py` |
| GET | `/api/settings/llm-models` | `web/routes/settings.py` |
| POST | `/api/settings` | `web/routes/settings.py` |
| POST | `/api/settings/clear-key` | `web/routes/settings.py` |
| POST | `/api/settings/test-connection` | `web/routes/settings.py` |
| GET | `/api/settings/test-design` | `web/routes/settings.py` |
| POST | `/api/settings/test-design` | `web/routes/settings.py` |
| GET | `/api/settings/allow-local` | `web/routes/settings.py` |
| POST | `/api/settings/allow-local` | `web/routes/settings.py` |
| GET | `/api/viewpoint-sets` | `web/routes/viewpoints.py` |
| POST | `/api/viewpoint-sets` | `web/routes/viewpoints.py` |
| GET | `/api/viewpoint-sets/<set_id>` | `web/routes/viewpoints.py` |
| PATCH | `/api/viewpoint-sets/<set_id>` | `web/routes/viewpoints.py` |
| DELETE | `/api/viewpoint-sets/<set_id>` | `web/routes/viewpoints.py` |
| POST | `/api/viewpoint-sets/<set_id>/restore` | `web/routes/viewpoints.py` |
| GET | `/api/viewpoint-sets/<set_id>/versions` | `web/routes/viewpoints.py` |
| POST | `/api/viewpoint-sets/<set_id>/versions` | `web/routes/viewpoints.py` |
| GET | `/api/viewpoint-sets/<set_id>/versions/<int:version>/items` | `web/routes/viewpoints.py` |
| POST | `/api/viewpoint-sets/<set_id>/versions/<int:version>/items` | `web/routes/viewpoints.py` |
| PATCH | `/api/viewpoint-items/<item_id>` | `web/routes/viewpoints.py` |
| DELETE | `/api/viewpoint-items/<item_id>` | `web/routes/viewpoints.py` |
| POST | `/api/viewpoint-items/<item_id>/restore` | `web/routes/viewpoints.py` |
| POST | `/api/viewpoint-items/bulk` | `web/routes/viewpoints.py` |
| POST | `/api/viewpoint-sets/<set_id>/versions/<int:version>/publish` | `web/routes/viewpoints.py` |
| POST | `/api/viewpoint-sets/<set_id>/versions/<int:version>/rollback` | `web/routes/viewpoints.py` |
| GET | `/api/viewpoint-sets/<set_id>/versions/diff` | `web/routes/viewpoints.py` |
| GET | `/api/viewpoint-sets/<set_id>/assignments` | `web/routes/viewpoints.py` |
| POST | `/api/viewpoint-sets/<set_id>/assignments` | `web/routes/viewpoints.py` |
| PATCH | `/api/viewpoint-assignments/<assignment_id>` | `web/routes/viewpoints.py` |
| DELETE | `/api/viewpoint-assignments/<assignment_id>` | `web/routes/viewpoints.py` |
| GET | `/api/viewpoint-sets/<set_id>/proposals` | `web/routes/viewpoints.py` |
| POST | `/api/viewpoint-sets/<set_id>/proposals` | `web/routes/viewpoints.py` |
| POST | `/api/viewpoint-proposals/<proposal_id>/decision` | `web/routes/viewpoints.py` |
| GET | `/api/viewpoint-sets/<set_id>/export` | `web/routes/viewpoints.py` |
| POST | `/api/viewpoint-sets/<set_id>/import` | `web/routes/viewpoints.py` |
| GET | `/api/viewpoint-sets/<set_id>/tree` | `web/routes/viewpoints.py` |
| POST | `/api/viewpoint-sets/<set_id>/folders` | `web/routes/viewpoints.py` |
| GET | `/api/viewpoint-templates` | `web/routes/viewpoints.py` |
| GET | `/api/viewpoint-sources` | `web/routes/viewpoints.py` |
| GET | `/api/viewpoint-sources/resolve` | `web/routes/viewpoints.py` |
| POST | `/api/viewpoint-sets/<set_id>/templates/<template_key>/apply` | `web/routes/viewpoints.py` |
| POST | `/api/viewpoint-templates/<template_key>/create-set` | `web/routes/viewpoints.py` |
| PATCH | `/api/viewpoint-items/<item_id>/move` | `web/routes/viewpoints.py` |
| PATCH | `/api/viewpoint-sets/<set_id>/items/reorder` | `web/routes/viewpoints.py` |
| DELETE | `/api/viewpoint-folders/<item_id>` | `web/routes/viewpoints.py` |
| GET | `/api/viewpoint-selection` | `web/routes/viewpoints.py` |

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `admin_audit.jsonl`
- `admin audit API and view`

### 永続化

- `instance/tenants/{slug}/admin_audit.jsonl`

### 失敗経路（すべて実際に踏むこと）

- malformed_line
- secret_value
- permission_denied
- tenant_escape

### 対応テスト

- `happy_path`
- `error_path`
- `tenant_isolation`
- `authorization`
- `evidence`

## 6. 未検証事項（エクスポート側の申告）

- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる
  URL・実行時にのみ解決される参照は検出できない。
- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**
  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。
- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。
