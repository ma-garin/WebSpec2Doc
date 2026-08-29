# 組み込み手順: Drift Check as Code（CI組み込みドリフト監視）

| 項目 | 値 |
|---|---|
| feature_id | `ci_drift_monitor` |
| 版 | `20260829-34d52a3` |
| 生成元 | `WebSpec2Doc` @ `34d52a3` |
| 生成日時 (UTC) | 2026-08-29T09:32:20Z |
| リスク / 状態 | high / implemented |
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

### サービス / コア（7 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `src/main.py` | 62520 | `f051a3bef57a` |
| `src/ci_drift.py` | 2897 | `80f91df9e72f` |
| `scripts/notify_drift.py` | 2313 | `2ebe97a0b30d` |
| `web/services/drift_summary.py` | 898 | `bda53e9aa0f1` |
| `web/services/notifier.py` | 14315 | `e61d0747fc08` |
| `web/services/job_queue.py` | 6917 | `0a2eab674457` |
| `.github/workflows/spec-drift.yml` | 3064 | `764948c957b3` |

### UI（テンプレート・JS・CSS）（3 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `templates/partials/view-settings.html` | 39538 | `8df7d8ecb0f0` |
| `static/js/results.js` | 33264 | `454d49c8a241` |
| `static/app.css` | 52176 | `a8ecf80ce6e4` |

## 2. 配線する

### 2-1. Blueprint を登録する

- このアセットに Blueprint は含まれない（登録作業なし）。

### 2-2. SPA シェルに差し込む

受け側の `templates/index.html` に追記する（本リポジトリと同じ配線規約）。

```jinja
{% include 'partials/view-settings.html' %}
<link rel="stylesheet" href="{{ url_for('static', filename='app.css') }}?v={{ _ver }}">
<script src="{{ url_for('static', filename='js/results.js') }}?v={{ _ver }}"></script>
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

- `src/analyzer/form_analyzer.py`
- `src/analyzer/html_analyzer.py`
- `src/analyzer/rule_injector.py`
- `src/capture/burndown.py`
- `src/capture/coverage.py`
- `src/capture/finding_reporter.py`
- `src/capture/reverse_generator.py`
- `src/capture/session_recorder.py`
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
- `src/generator/test_plan_generator.py`
- `src/generator/trace_reporter.py`
- `src/generator/ux_reporter.py`
- `src/graph/transition_graph.py`
- `src/health/technical_health.py`
- `src/ingest/loader.py`
- `src/ingest/matcher.py`
- `src/ingest/req_tracer.py`
- `src/llm/provider.py`
- `src/ux/axe_runner.py`
- `src/viewport/runner.py`
- `web/services/metrics.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `jinja2` | jinja2==3.1.6 |
| `networkx` | networkx==3.3 |
| `python-dotenv` | python-dotenv==1.2.2 |

### 3-3. 環境変数

- `OPENAI_API_KEY`
- `SLACK_WEBHOOK_URL`
- `SMTP_FROM`
- `SMTP_HOST`
- `SMTP_PASSWORD`
- `SMTP_PORT`
- `SMTP_TO`
- `SMTP_USER`
- `WEBSPEC2DOC_RECORD_HEADLESS`

### 3-4. 呼び出す API（受け側に実在が必要）

- `/api/`
- `/api/admin/backup-guide`
- `/api/doc-fusion`
- `/api/export/spec-xlsx`
- `/api/result`
- `/api/snapshot-diff-summary`
- `/api/snapshots`
- `/api/testcases/count`
- `/preview`

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

| ファイル | 所属する機能 | 関係 |
|---|---|---|
| `static/js/settings.js` | `settings`, `snapshot_retention`, `admin_audit` | `templates/partials/view-settings.html` を動かす JS と見られるが未同梱 |

## 4. このアセットが提供する API

- なし

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `drift_summary.json`
- `CI_SUMMARY stdout record`
- `Slack drift notification`

### 永続化

- `output/{domain}/snapshots/`
- `output/{domain}/drift_summary.json`
- `GitHub Actions snapshot cache`

### 失敗経路（すべて実際に踏むこと）

- missing_webhook
- notify_http_error
- missing_summary
- first_run
- session_expired
- missing_target
- accessibility_asset_error
- crawl_execution_failure

### 対応テスト

- `happy_path`
- `error_path`
- `no_change_path`
- `exit_code_contract`
- `evidence`

## 6. 未検証事項（エクスポート側の申告）

- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる
  URL・実行時にのみ解決される参照は検出できない。
- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**
  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。
- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。
