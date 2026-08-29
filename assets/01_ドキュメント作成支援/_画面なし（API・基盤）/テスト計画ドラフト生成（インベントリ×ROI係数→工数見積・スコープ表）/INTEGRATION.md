# 組み込み手順: テスト計画ドラフト生成（インベントリ×ROI係数→工数見積・スコープ表）

| 項目 | 値 |
|---|---|
| feature_id | `test_plan` |
| 版 | `20260829-81e4c84` |
| 生成元 | `WebSpec2Doc` @ `81e4c84` |
| 生成日時 (UTC) | 2026-08-29T11:24:08Z |
| リスク / 状態 | medium / implemented |
| 同梱ファイル数 | 10 |
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
| `web/routes/qa_process.py` | 19970 | `aeb59facf1ae` |

### サービス / コア（9 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `src/generator/test_plan_generator.py` | 13561 | `ab26ac44e3fe` |
| `src/main.py` | 62520 | `f051a3bef57a` |
| `web/services/qa/doc_generator.py` | 25108 | `2d720b7e0b42` |
| `web/services/qa/advanced_generator.py` | 17577 | `99a88c51ed91` |
| `web/services/qa/advanced_html.py` | 11168 | `7b23fa9b0c42` |
| `web/services/qa/helpers.py` | 16329 | `80d8f1800eed` |
| `web/services/qa/markdown_lite.py` | 4991 | `df124c8fdba1` |
| `web/services/qa/testcase_docs.py` | 5442 | `4835ada5afa3` |
| `web/services/test_design_settings.py` | 8193 | `762e502d9c58` |

## 2. 配線する

### 2-1. Blueprint を登録する

受け側の `web/__init__.py`（アプリケーションファクトリ）に追記する。

```python
from web.routes import qa_process
app.register_blueprint(qa_process.bp)
```

| Blueprint | url_prefix | 定義元 |
|---|---|---|
| `qa_process` | `(なし)` | `web/routes/qa_process.py` |

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

- `src/analyzer/form_analyzer.py`
- `src/analyzer/html_analyzer.py`
- `src/analyzer/rule_injector.py`
- `src/capture/burndown.py`
- `src/capture/coverage.py`
- `src/capture/finding_reporter.py`
- `src/capture/reverse_generator.py`
- `src/capture/session_recorder.py`
- `src/ci_drift.py`
- `src/crawler/auth.py`
- `src/crawler/auth_recorder.py`
- `src/crawler/auto_login.py`
- `src/crawler/page_crawler.py`
- `src/crawler/session_guard.py`
- `src/crawler/url_safety.py`
- `src/diff/comparison.py`
- `src/diff/differ.py`
- `src/diff/impact_analyzer.py`
- `src/diff/snapshot.py`
- `src/generator/accessibility_reporter.py`
- `src/generator/architecture_generator.py`
- `src/generator/comparison_reporter.py`
- `src/generator/coverage_gap.py`
- `src/generator/diff_reporter.py`
- `src/generator/excel_reporter.py`
- `src/generator/fusion_reporter.py`
- `src/generator/html_reporter.py`
- `src/generator/json_reporter.py`
- `src/generator/markdown_generator.py`
- `src/generator/mermaid_generator.py`
- `src/generator/pdf_reporter.py`
- `src/generator/refresh_reporter.py`
- `src/generator/test_design.py`
- `src/generator/trace_reporter.py`
- `src/generator/ux_reporter.py`
- `src/graph/transition_graph.py`
- `src/health/technical_health.py`
- `src/ingest/loader.py`
- `src/ingest/matcher.py`
- `src/ingest/req_tracer.py`
- `src/llm/provider.py`
- `src/llm/screen_classifier.py`
- `src/llm/viewpoint_generator.py`
- `src/ux/axe_runner.py`
- `src/viewport/runner.py`
- `web/config.py`
- `web/env_store.py`
- `web/services/condition_run_status.py`
- `web/services/egress_gateway.py`
- `web/services/openai_qa.py`
- `web/services/playwright_executor.py`
- `web/services/run_store.py`
- `web/services/screen_test_design.py`
- `web/services/testcase_spec_generator.py`
- `web/services/testcase_table_store.py`
- `web/services/usage_tracker.py`
- `web/services/viewpoint_store.py`
- `web/summary.py`
- `web/tenancy.py`
- `web/validation.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `flask` | flask==3.1.3 |
| `networkx` | networkx==3.3 |
| `openpyxl` | openpyxl==3.1.4 |
| `python-dotenv` | python-dotenv==1.2.2 |

### 3-3. 環境変数

- `OPENAI_API_KEY`
- `WEBSPEC2DOC_RECORD_HEADLESS`

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
| GET | `/api/qa-process/input` | `web/routes/qa_process.py` |
| POST | `/api/qa-process/generate` | `web/routes/qa_process.py` |
| GET | `/api/qa-process/result` | `web/routes/qa_process.py` |
| GET | `/api/testcases` | `web/routes/qa_process.py` |
| GET | `/api/testcases/table` | `web/routes/qa_process.py` |
| GET | `/api/testcases/count` | `web/routes/qa_process.py` |
| GET | `/api/testcases/history` | `web/routes/qa_process.py` |
| POST | `/api/testcases/cell` | `web/routes/qa_process.py` |
| POST | `/api/testcases/cell/reset` | `web/routes/qa_process.py` |
| POST | `/api/testcases/run` | `web/routes/qa_process.py` |
| GET | `/api/testcases/live-progress` | `web/routes/qa_process.py` |
| GET | `/api/testcases/live-screenshot` | `web/routes/qa_process.py` |
| POST | `/api/testcases/row` | `web/routes/qa_process.py` |
| GET | `/api/test-design` | `web/routes/qa_process.py` |
| GET | `/api/test-design/by-screen` | `web/routes/qa_process.py` |
| GET | `/api/qa-process/advanced` | `web/routes/qa_process.py` |
| POST | `/api/qa-process/generate-advanced` | `web/routes/qa_process.py` |

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `test_plan.md`
- `test_plan.xlsx`

### 永続化

- `output/{domain}/test_plan.md`
- `output/{domain}/test_plan.xlsx`

### 失敗経路（すべて実際に踏むこと）

- no_inventory
- report_corrupt
- empty_screens
- xlsx_write_failure
- invalid_env_override

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
