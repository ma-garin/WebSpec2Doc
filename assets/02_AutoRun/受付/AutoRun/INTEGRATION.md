# 組み込み手順: AutoRun

| 項目 | 値 |
|---|---|
| feature_id | `autorun` |
| 版 | `20260829-5345533` |
| 生成元 | `WebSpec2Doc` @ `5345533` |
| 生成日時 (UTC) | 2026-08-29T07:50:11Z |
| リスク / 状態 | high / implemented |
| 同梱ファイル数 | 14 |
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

### サービス / コア（9 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `web/services/spec_ts_generator.py` | 32817 | `269e545eb992` |
| `web/services/playwright_executor.py` | 45033 | `14537e601aaa` |
| `web/services/auto_run_config.py` | 693 | `e4602daf020a` |
| `web/services/auto_run_job.py` | 12942 | `3b17dd692a20` |
| `web/services/auto_run_pipeline.py` | 51642 | `8b0e9425df84` |
| `web/services/auto_run_preview.py` | 2004 | `732a9088fa60` |
| `web/services/failure_classifier.py` | 9868 | `c23109417c98` |
| `src/crawler/data_flow.py` | 3667 | `cb39435c4c7b` |
| `src/crawler/form_navigator.py` | 4293 | `10a540750d6b` |

### UI（テンプレート・JS・CSS）（4 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `templates/partials/view-auto-run.html` | 27151 | `1e5f7d80fcdd` |
| `static/js/autorun.js` | 60389 | `fd73d9bc299c` |
| `static/js/autorun-approval.js` | 5113 | `b9883d8de36d` |
| `static/js/view-test-runs.js` | 14254 | `98e87562eaa7` |

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
<script src="{{ url_for('static', filename='js/autorun.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/autorun-approval.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/view-test-runs.js') }}?v={{ _ver }}"></script>
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

- `src/autorun/automation_plan.py`
- `src/autorun/stages.py`
- `src/crawler/playwright_runtime.py`
- `src/crawler/url_safety.py`
- `web/config.py`
- `web/services/__init__.py`
- `web/services/document_autorun.py`
- `web/services/egress_gateway.py`
- `web/services/evidence_pack_service.py`
- `web/services/failure_hypothesis.py`
- `web/services/mutation_verifier.py`
- `web/services/nonfunctional_judge.py`
- `web/services/observation_coverage.py`
- `web/services/qa/advanced_generator.py`
- `web/services/qa/doc_generator.py`
- `web/services/qa/helpers.py`
- `web/services/run_notifier.py`
- `web/services/run_store.py`
- `web/services/usage_tracker.py`
- `web/services/viewpoint_store.py`
- `web/tenancy.py`
- `web/validation.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `flask` | flask==3.1.3 |

### 3-3. 環境変数

- `WEBSPEC2DOC_PW_MAX_EXEC_SEC`

### 3-4. 呼び出す API（受け側に実在が必要）

- `/api/autorun/cancel`
- `/api/autorun/jobs`
- `/api/autorun/live-screenshot`
- `/api/autorun/preview`
- `/api/autorun/status`
- `/api/autorun/submit-input`
- `/api/history`
- `/api/testcases/live-progress`
- `/api/testcases/live-screenshot`
- `/api/testcases/run`
- `/api/viewpoint-selection`
- `/preview`

### 3-5. データファイル

- なし

### 3-6. 同梱外のテンプレート / 静的ファイル参照

- なし

### 3-7. 同梱 JS が参照するグローバル

他アセット由来のものが混ざっていれば、そのアセットも併せて受け渡す。

- `_autoRunLastData`
- `autorunCancel`
- `autorunLeadBar`
- `autorunReview`
- `autorunStages`

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

- `QA artifacts`
- `Playwright candidates`
- `execution logs`
- `data reflection flows`
- `page object spec.ts`

### 永続化

- `output/{domain}/qa_process/`

### 失敗経路（すべて実際に踏むこと）

- approval_timeout
- login_wait_timeout
- dependency_missing
- cancel
- execution_timeout_partial_result
- result_parse_failure
- form_submit_disabled_by_default

### 対応テスト

- `happy_path`
- `approval_path`
- `cancel_path`
- `error_path`
- `timeout_path`
- `evidence`

## 6. 未検証事項（エクスポート側の申告）

- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる
  URL・実行時にのみ解決される参照は検出できない。
- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**
  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。
- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。
