# 組み込み手順: CLI モード（System 03・画面なし）

| 項目 | 値 |
|---|---|
| feature_id | `cli_mode` |
| 版 | `20260829-5345533` |
| 生成元 | `WebSpec2Doc` @ `5345533` |
| 生成日時 (UTC) | 2026-08-29T07:50:13Z |
| リスク / 状態 | high / implemented |
| 同梱ファイル数 | 7 |
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
| `web/routes/pages.py` | 4771 | `eb3c13a97fdb` |

### サービス / コア（2 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `src/cli.py` | 36593 | `5fdc88ee4566` |
| `web/services/cli_runner.py` | 11535 | `8bea060b04e3` |

### UI（テンプレート・JS・CSS）（4 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `templates/system-select.html` | 7882 | `bd63b8b7a0d9` |
| `templates/cli.html` | 6695 | `c5a51a7c71f5` |
| `static/js/cli-mode.js` | 2591 | `a654ac170690` |
| `static/css/cli-mode.css` | 3131 | `6f88fddaf934` |

## 2. 配線する

### 2-1. Blueprint を登録する

受け側の `web/__init__.py`（アプリケーションファクトリ）に追記する。

```python
from web.routes import pages
app.register_blueprint(pages.bp)
```

| Blueprint | url_prefix | 定義元 |
|---|---|---|
| `pages` | `(なし)` | `web/routes/pages.py` |

### 2-2. SPA シェルに差し込む

受け側の `templates/index.html` に追記する（本リポジトリと同じ配線規約）。

```jinja
{% include 'system-select.html' %}
{% include 'cli.html' %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/cli-mode.css') }}?v={{ _ver }}">
<script src="{{ url_for('static', filename='js/cli-mode.js') }}?v={{ _ver }}"></script>
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

- `src/ci_drift.py`
- `src/ci_gate.py`
- `src/crawler/url_safety.py`
- `web/auth.py`
- `web/config.py`
- `web/routes/__init__.py`
- `web/routes/review.py`
- `web/services/auto_run_job.py`
- `web/services/auto_run_pipeline.py`
- `web/services/egress_gateway.py`
- `web/services/playwright_executor.py`
- `web/services/testcase_spec_generator.py`
- `web/services/testcase_table_store.py`
- `web/services/viewpoint_store.py`
- `web/services/viewpoint_templates.py`
- `web/tenancy.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `flask` | flask==3.1.3 |

### 3-3. 環境変数

- `GITHUB_STEP_SUMMARY`

### 3-4. 呼び出す API（受け側に実在が必要）

- なし

### 3-5. データファイル

- なし

### 3-6. 同梱外のテンプレート / 静的ファイル参照

- `static/css/system-select.css`
- `static/tokens.css`

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
| GET | `/` | `web/routes/pages.py` |
| GET | `/systems` | `web/routes/pages.py` |
| GET | `/cli` | `web/routes/pages.py` |
| GET | `/settings/<tab>` | `web/routes/pages.py` |
| GET | `/<view_name>` | `web/routes/pages.py` |

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `端末出力（人が読む形）`
- `JSON 出力（--json・自動化向け）`
- `終了コード（0/1/2/130）`
- `output/{domain}/ 配下の成果物`

### 永続化

- `output/{domain}/`
- `output/{domain}/testcases/run_result.json`

### 失敗経路（すべて実際に踏むこと）

- login_required_without_credentials
- target_unreachable
- zero_tests_executed_reported_as_success
- stage_approval_auto_passed_without_human
- timeout_cancelled
- unknown_option_silently_ignored

### 対応テスト

- `happy_path`
- `error_path`
- `exit_code_path`
- `evidence`

## 6. 未検証事項（エクスポート側の申告）

- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる
  URL・実行時にのみ解決される参照は検出できない。
- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**
  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。
- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。
