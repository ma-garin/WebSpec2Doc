# 組み込み手順: REST API拡充とOpenAPI公開

| 項目 | 値 |
|---|---|
| feature_id | `api_v1_openapi` |
| 版 | `20260829-81e4c84` |
| 生成元 | `WebSpec2Doc` @ `81e4c84` |
| 生成日時 (UTC) | 2026-08-29T11:24:08Z |
| リスク / 状態 | high / implemented |
| 同梱ファイル数 | 4 |
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
| `web/routes/api_v1.py` | 11288 | `7f8fccc7adff` |
| `web/routes/api_v1_schedule.py` | 6941 | `7e1fd1d300e2` |

### サービス / コア（2 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `web/services/openapi_spec.py` | 4375 | `0c094bd1335c` |
| `web/services/openapi_docs.py` | 5199 | `e7d6baf989b5` |

## 2. 配線する

### 2-1. Blueprint を登録する

受け側の `web/__init__.py`（アプリケーションファクトリ）に追記する。

```python
from web.routes import api_v1, api_v1_schedule
app.register_blueprint(api_v1.bp)
app.register_blueprint(api_v1_schedule.bp)
```

| Blueprint | url_prefix | 定義元 |
|---|---|---|
| `api_v1` | `/api/v1` | `web/routes/api_v1.py` |
| `api_v1_schedule` | `/api/v1` | `web/routes/api_v1_schedule.py` |

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

- `src/diff/differ.py`
- `src/diff/snapshot.py`
- `src/registry/site_registry.py`
- `web/audit_context.py`
- `web/auth.py`
- `web/config.py`
- `web/routes/schedule.py`
- `web/services/job_queue.py`
- `web/services/notifier.py`
- `web/services/scheduler.py`
- `web/tenancy.py`
- `web/validation.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `flask` | flask==3.1.3 |

### 3-3. 環境変数

- なし

### 3-4. 呼び出す API（受け側に実在が必要）

- なし

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
| GET | `/healthz` | `web/routes/api_v1.py` |
| GET | `/sites` | `web/routes/api_v1.py` |
| GET | `/sites/<domain>/report` | `web/routes/api_v1.py` |
| GET | `/sites/<domain>/snapshots` | `web/routes/api_v1.py` |
| GET | `/sites/<domain>/diff` | `web/routes/api_v1.py` |
| POST | `/sites/<domain>/crawl` | `web/routes/api_v1.py` |
| GET | `/jobs/<job_id>` | `web/routes/api_v1.py` |
| GET | `/sites/<domain>/jobs` | `web/routes/api_v1.py` |
| GET | `/sites/<domain>/test-cases` | `web/routes/api_v1.py` |
| GET | `/openapi.json` | `web/routes/api_v1.py` |
| GET | `/docs` | `web/routes/api_v1.py` |
| GET | `/sites/<domain>/schedule` | `web/routes/api_v1_schedule.py` |
| PUT | `/sites/<domain>/schedule` | `web/routes/api_v1_schedule.py` |
| DELETE | `/sites/<domain>/schedule` | `web/routes/api_v1_schedule.py` |
| GET | `/sites/<domain>/notifications` | `web/routes/api_v1_schedule.py` |
| PUT | `/sites/<domain>/notifications` | `web/routes/api_v1_schedule.py` |

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `/api/v1/openapi.json`
- `/api/v1/docs`

### 永続化

- `output/{domain}/schedule.json`

### 失敗経路（すべて実際に踏むこと）

- invalid_domain
- forbidden_non_admin
- invalid_interval
- invalid_notify_type
- cross_tenant_access

### 対応テスト

- `happy_path`
- `error_path`
- `authorization_path`
- `implemented_paths_only`
- `evidence`

## 6. 未検証事項（エクスポート側の申告）

- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる
  URL・実行時にのみ解決される参照は検出できない。
- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**
  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。
- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。
