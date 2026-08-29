# 組み込み手順: クロール / レポート生成

| 項目 | 値 |
|---|---|
| feature_id | `crawl` |
| 版 | `20260829-81e4c84` |
| 生成元 | `WebSpec2Doc` @ `81e4c84` |
| 生成日時 (UTC) | 2026-08-29T11:24:07Z |
| リスク / 状態 | critical / implemented |
| 同梱ファイル数 | 27 |
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
| `web/routes/crawl.py` | 9778 | `9cb5a2303935` |

### サービス / コア（22 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `src/crawler/page_crawler.py` | 61123 | `e90a414ce2be` |
| `src/crawler/parallel_crawler.py` | 17700 | `7c84d2596da5` |
| `src/crawler/politeness.py` | 11767 | `45ee49c05923` |
| `src/crawler/action_explorer.py` | 14225 | `5d4697176708` |
| `src/crawler/link_extractor.py` | 23977 | `eb1c0339d43f` |
| `src/analyzer/canonicalizer.py` | 4284 | `74787f78e51c` |
| `src/analyzer/form_analyzer.py` | 690 | `577830c0f309` |
| `src/analyzer/html_analyzer.py` | 1563 | `b63d10dc46e6` |
| `src/analyzer/stack_detector.py` | 6831 | `ffe71315a422` |
| `src/crawler/network_interceptor.py` | 10194 | `395e4b061ecb` |
| `src/crawler/spa_monitor.py` | 3080 | `e24da90b91b8` |
| `src/graph/transition_graph.py` | 12767 | `80ad3e73f9cd` |
| `src/generator/markdown_generator.py` | 2029 | `c4d4ff6d4120` |
| `src/generator/markdown_util.py` | 618 | `225ad5952a12` |
| `src/generator/mermaid_generator.py` | 2393 | `2a1f3b51186c` |
| `src/generator/excel_reporter.py` | 5657 | `f15a55d2cb0a` |
| `src/generator/csv_reporter.py` | 3674 | `715f33ee15ca` |
| `src/generator/pdf_reporter.py` | 1172 | `74557bdee49a` |
| `src/generator/architecture_generator.py` | 4885 | `8f0b937f6e10` |
| `src/generator/feature_catalog.py` | 3161 | `8d67e5d28741` |
| `src/generator/test_design.py` | 17422 | `e053e11c002f` |
| `src/crawler/performance_probe.py` | 4214 | `b27a7cb5038b` |

### UI（テンプレート・JS・CSS）（4 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `templates/partials/view-generate.html` | 21038 | `da6646d5d332` |
| `static/js/execution.js` | 20310 | `d56f390e4abb` |
| `static/js/results.js` | 33264 | `454d49c8a241` |
| `static/js/ui-states.js` | 3611 | `7a21bccae083` |

## 2. 配線する

### 2-1. Blueprint を登録する

受け側の `web/__init__.py`（アプリケーションファクトリ）に追記する。

```python
from web.routes import crawl
app.register_blueprint(crawl.bp)
```

| Blueprint | url_prefix | 定義元 |
|---|---|---|
| `crawl` | `(なし)` | `web/routes/crawl.py` |

### 2-2. SPA シェルに差し込む

受け側の `templates/index.html` に追記する（本リポジトリと同じ配線規約）。

```jinja
{% include 'partials/view-generate.html' %}
<script src="{{ url_for('static', filename='js/execution.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/results.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/ui-states.js') }}?v={{ _ver }}"></script>
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

- `src/analyzer/bva.py`
- `src/analyzer/login_wall.py`
- `src/analyzer/test_conditions.py`
- `src/crawler/playwright_runtime.py`
- `src/crawler/session_guard.py`
- `src/crawler/url_safety.py`
- `src/ingest/loader.py`
- `src/llm/screen_classifier.py`
- `src/techniques/combinatorial.py`
- `src/ux/axe_runner.py`
- `web/config.py`
- `web/process.py`
- `web/routes/site.py`
- `web/services/run_store.py`
- `web/services/usage_tracker.py`
- `web/summary.py`
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

- `/api/`
- `/api/cancel`
- `/api/doc-fusion`
- `/api/export/spec-xlsx`
- `/api/history`
- `/api/live-screenshot`
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

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `report.html`
- `report.json`
- `screenshots`
- `snapshot`
- `audit.jsonl`
- `performance samples (LCP/CLS/TTFB)`

### 永続化

- `output/{domain}/`
- `output/{domain}/snapshots/`

### 失敗経路（すべて実際に踏むこと）

- login_wall_during_crawl
- restricted_url
- timeout
- cancel
- partial_checkpoint
- robots_disallowed
- rate_limit_backoff
- mutation_blocked
- mutation_blocked_audit
- cross_origin_iframe
- closed_shadow_root

### 対応テスト

- `happy_path`
- `error_path`
- `cancel_path`
- `checkpoint_path`
- `evidence`

## 6. 未検証事項（エクスポート側の申告）

- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる
  URL・実行時にのみ解決される参照は検出できない。
- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**
  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。
- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。
