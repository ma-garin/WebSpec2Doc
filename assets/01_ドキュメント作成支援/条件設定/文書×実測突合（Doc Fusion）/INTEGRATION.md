# 組み込み手順: 文書×実測突合（Doc Fusion）

| 項目 | 値 |
|---|---|
| feature_id | `doc_fusion` |
| 版 | `20260829-5345533` |
| 生成元 | `WebSpec2Doc` @ `5345533` |
| 生成日時 (UTC) | 2026-08-29T07:50:11Z |
| リスク / 状態 | high / implemented |
| 同梱ファイル数 | 23 |
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
| `web/routes/crawl.py` | 9778 | `9cb5a2303935` |
| `web/routes/traceability.py` | 4003 | `f4345c811eb1` |

### サービス / コア（16 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `src/ingest/loader.py` | 7680 | `dd37badf0755` |
| `src/ingest/matcher.py` | 16656 | `dcb949b55c4f` |
| `src/generator/fusion_reporter.py` | 9080 | `3f176032925a` |
| `src/ingest/llm_extractor.py` | 10859 | `98b0891a3010` |
| `src/analyzer/rule_injector.py` | 5390 | `6385472d07ed` |
| `src/generator/json_reporter.py` | 8823 | `db852bb9ba7d` |
| `src/ingest/req_tracer.py` | 8112 | `61227e1b9c4f` |
| `src/generator/trace_reporter.py` | 6745 | `d30f742dc7fc` |
| `src/ingest/tables.py` | 11535 | `e9761e9668f8` |
| `src/generator/refresh_reporter.py` | 20539 | `03e7e79b2ec3` |
| `src/ingest/models.py` | 3267 | `db0e93d734de` |
| `src/ingest/office_reader.py` | 5035 | `c1f34c3560e6` |
| `src/ingest/text_reader.py` | 3618 | `206820e8e6a7` |
| `src/ingest/data_reader.py` | 6187 | `67ac5ed88557` |
| `src/ingest/excel_reader.py` | 2269 | `5ebdf8ed8b11` |
| `src/ingest/gherkin_reader.py` | 4678 | `a90c9f0dc243` |

### UI（テンプレート・JS・CSS）（5 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `templates/partials/view-generate.html` | 21038 | `da6646d5d332` |
| `static/js/wizard.js` | 39556 | `3d6ef279e605` |
| `static/js/execution.js` | 20310 | `d56f390e4abb` |
| `static/js/results.js` | 33264 | `454d49c8a241` |
| `static/js/doc-fusion.js` | 2910 | `4973a88ac1bd` |

## 2. 配線する

### 2-1. Blueprint を登録する

受け側の `web/__init__.py`（アプリケーションファクトリ）に追記する。

```python
from web.routes import crawl, traceability
app.register_blueprint(crawl.bp)
app.register_blueprint(traceability.bp)
```

| Blueprint | url_prefix | 定義元 |
|---|---|---|
| `crawl` | `(なし)` | `web/routes/crawl.py` |
| `traceability` | `(なし)` | `web/routes/traceability.py` |

### 2-2. SPA シェルに差し込む

受け側の `templates/index.html` に追記する（本リポジトリと同じ配線規約）。

```jinja
{% include 'partials/view-generate.html' %}
<script src="{{ url_for('static', filename='js/wizard.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/execution.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/results.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/doc-fusion.js') }}?v={{ _ver }}"></script>
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

- `src/analyzer/canonicalizer.py`
- `src/analyzer/html_analyzer.py`
- `src/analyzer/test_conditions.py`
- `src/analyzer/text_similarity.py`
- `src/crawler/page_crawler.py`
- `src/generator/markdown_util.py`
- `src/llm/provider.py`
- `web/config.py`
- `web/process.py`
- `web/routes/site.py`
- `web/services/run_store.py`
- `web/services/traceability.py`
- `web/services/usage_tracker.py`
- `web/summary.py`
- `web/tenancy.py`
- `web/validation.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `PyYAML` | PyYAML==6.0.1 |
| `defusedxml` | defusedxml==0.7.1 |
| `flask` | flask==3.1.3 |
| `networkx` | networkx==3.3 |
| `openpyxl` | openpyxl==3.1.4 |
| `pypdf` | pypdf==6.15.0 |

### 3-3. 環境変数

- なし

### 3-4. 呼び出す API（受け側に実在が必要）

- `/api/`
- `/api/cancel`
- `/api/discover-stream`
- `/api/doc-fusion`
- `/api/export/spec-xlsx`
- `/api/history`
- `/api/live-screenshot`
- `/api/login/record/cancel`
- `/api/login/record/complete`
- `/api/login/record/start`
- `/api/login/record/status`
- `/api/login/scrape`
- `/api/login/simple`
- `/api/login/submit`
- `/api/reference-docs`
- `/api/result`
- `/api/snapshot-diff-summary`
- `/api/snapshots`
- `/api/testcases/count`
- `/preview`
- `/run`

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
| POST | `/run` | `web/routes/crawl.py` |
| POST | `/api/cancel` | `web/routes/crawl.py` |
| GET | `/api/live-screenshot` | `web/routes/crawl.py` |
| POST | `/api/reference-docs` | `web/routes/crawl.py` |
| GET | `/api/doc-fusion` | `web/routes/crawl.py` |
| GET | `/traceability/matrix` | `web/routes/traceability.py` |
| GET | `/traceability/view` | `web/routes/traceability.py` |

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `doc_fusion.json`
- `doc_fusion.md`
- `official_name in report.json`
- `documented_rules in doc_fusion.json`
- `document_conditions/test_conditions_detail in report.json`
- `requirement_trace.json`
- `traceability_matrix.md`
- `document_requirements in /traceability/matrix`
- `refreshed_spec.md`
- `refresh_log.json`

### 永続化

- `output/{domain}/doc_fusion.json`
- `output/{domain}/reference_docs/`
- `output/{domain}/requirement_trace.json`
- `output/{domain}/traceability_matrix.md`
- `output/{domain}/refreshed_spec.md`
- `output/{domain}/refresh_log.json`

### 失敗経路（すべて実際に踏むこと）

- unsupported_format
- missing_file
- legacy_binary_format
- no_match
- llm_schema_reject
- hallucinated_quote
- rule_unmatched
- rule_value_unparsable
- upload_rejected
- path_traversal_attempt
- requirement_unmatched
- duplicate_requirement_id
- candidates_file_missing_or_corrupt
- refresh_selector_lookup_failed
- refresh_no_screens_skip
- refresh_flag_without_reference_doc

### 対応テスト

- `happy_path`
- `error_path`
- `mismatch_detection`
- `evidence`

## 6. 未検証事項（エクスポート側の申告）

- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる
  URL・実行時にのみ解決される参照は検出できない。
- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**
  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。
- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。
