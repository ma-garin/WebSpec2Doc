# 組み込み手順: 文書駆動MBT（要件×実測からのテスト設計）

| 項目 | 値 |
|---|---|
| feature_id | `document_mbt` |
| 版 | `20260829-34d52a3` |
| 生成元 | `WebSpec2Doc` @ `34d52a3` |
| 生成日時 (UTC) | 2026-08-29T09:32:20Z |
| リスク / 状態 | critical / implemented |
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

### ルート（API）（1 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `web/routes/auto_run.py` | 28109 | `9d4beccc5ddd` |

### サービス / コア（8 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `src/mbt/document_model.py` | 15755 | `1f0923d78baf` |
| `src/mbt/manual_procedures.py` | 7503 | `b1a5c23be00b` |
| `src/mbt/test_data.py` | 11830 | `de54b0938d5e` |
| `src/mbt/validation_observer.py` | 11280 | `29499a0e94ae` |
| `web/services/document_autorun.py` | 9494 | `a330b19e1012` |
| `src/mbt/pairwise.py` | 4140 | `e39cab526190` |
| `src/mbt/metamorphic.py` | 7050 | `ce8529209378` |
| `src/mbt/trace_suggestions.py` | 5802 | `b78e441ae958` |

### UI（テンプレート・JS・CSS）（3 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `templates/partials/view-auto-run.html` | 27151 | `1e5f7d80fcdd` |
| `static/js/autorun-document.js` | 10587 | `ab4d325323cd` |
| `static/css/autorun-document.css` | 2424 | `e52aba672693` |

## 2. 配線する

### 2-1. Blueprint を登録する

受け側の `web/__init__.py`（アプリケーションファクトリ）に追記する。

```python
from web.routes import auto_run
app.register_blueprint(auto_run.bp)
```

| Blueprint | url_prefix | 定義元 |
|---|---|---|
| `auto_run` | `(なし)` | `web/routes/auto_run.py` |

### 2-2. SPA シェルに差し込む

受け側の `templates/index.html` に追記する（本リポジトリと同じ配線規約）。

```jinja
{% include 'partials/view-auto-run.html' %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/autorun-document.css') }}?v={{ _ver }}">
<script src="{{ url_for('static', filename='js/autorun-document.js') }}?v={{ _ver }}"></script>
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

- `src/autorun/stages.py`
- `src/techniques/combinatorial.py`
- `web/config.py`
- `web/services/auto_run_config.py`
- `web/services/auto_run_job.py`
- `web/services/auto_run_pipeline.py`
- `web/services/auto_run_preview.py`
- `web/services/playwright_executor.py`
- `web/services/qa/helpers.py`
- `web/services/usage_tracker.py`
- `web/services/viewpoint_store.py`
- `web/tenancy.py`
- `web/validation.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `flask` | flask==3.1.3 |
| `networkx` | networkx==3.3 |
| `openpyxl` | openpyxl==3.1.4 |
| `playwright` | playwright==1.61.0 |

### 3-3. 環境変数

- なし

### 3-4. 呼び出す API（受け側に実在が必要）

- `/api/autorun/start`
- `/api/reference-docs`

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
| POST | `/api/autorun/start` | `web/routes/auto_run.py` |
| GET | `/api/autorun/status` | `web/routes/auto_run.py` |
| POST | `/api/autorun/cancel` | `web/routes/auto_run.py` |
| GET | `/api/history/runs` | `web/routes/auto_run.py` |
| POST | `/api/autorun/submit-input` | `web/routes/auto_run.py` |
| GET | `/api/autorun/preview` | `web/routes/auto_run.py` |
| POST | `/api/autorun/approve` | `web/routes/auto_run.py` |
| GET | `/api/autorun/report` | `web/routes/auto_run.py` |
| GET | `/api/autorun/live-screenshot` | `web/routes/auto_run.py` |
| GET | `/api/autorun/jobs` | `web/routes/auto_run.py` |

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `document_mbt.json`
- `manual_procedures.md/xlsx`
- `test_data.json/csv`
- `validation_observations.json`
- `pairwise_cases.json`
- `metamorphic_checks.json`
- `prime_path selection criterion`
- `unmatched_requirement_suggestions`

### 永続化

- `output/{domain}/qa_process/`

### 失敗経路（すべて実際に踏むこと）

- missing_reference_docs
- unmatched_requirements
- no_reachable_path
- path_limit_truncation
- validation_browser_failure
- empty_measured_graph

### 対応テスト

- `happy_path`
- `error_path`
- `coverage_path`
- `no_submit_guarantee`
- `evidence`

## 6. 未検証事項（エクスポート側の申告）

- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる
  URL・実行時にのみ解決される参照は検出できない。
- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**
  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。
- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。
