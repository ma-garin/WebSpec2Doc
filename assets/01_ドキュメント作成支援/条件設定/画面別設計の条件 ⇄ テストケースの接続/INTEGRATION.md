# 組み込み手順: 画面別設計の条件 ⇄ テストケースの接続

| 項目 | 値 |
|---|---|
| feature_id | `condition_to_testcase_link` |
| 版 | `20260829-5345533` |
| 生成元 | `WebSpec2Doc` @ `5345533` |
| 生成日時 (UTC) | 2026-08-29T07:50:13Z |
| リスク / 状態 | medium / implemented |
| 同梱ファイル数 | 8 |
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

### サービス / コア（2 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `web/services/screen_test_design.py` | 16445 | `1369bf1737f1` |
| `web/services/testcase_table_store.py` | 15875 | `d946a1027d64` |

### UI（テンプレート・JS・CSS）（5 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `templates/partials/view-generate.html` | 21038 | `da6646d5d332` |
| `static/js/view-design.js` | 41580 | `212932283ccd` |
| `static/js/view-testcase-grid.js` | 23932 | `35efccb607a6` |
| `static/app-report.css` | 49653 | `398642d43725` |
| `static/css/testcase-grid.css` | 6593 | `29da94c2af03` |

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

### 2-2. SPA シェルに差し込む

受け側の `templates/index.html` に追記する（本リポジトリと同じ配線規約）。

```jinja
{% include 'partials/view-generate.html' %}
<link rel="stylesheet" href="{{ url_for('static', filename='app-report.css') }}?v={{ _ver }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/testcase-grid.css') }}?v={{ _ver }}">
<script src="{{ url_for('static', filename='js/view-design.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/view-testcase-grid.js') }}?v={{ _ver }}"></script>
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

- `src/autorun/techniques.py`
- `src/crawler/url_safety.py`
- `src/generator/test_design.py`
- `src/generator/testcase_table.py`
- `src/llm/viewpoint_generator.py`
- `web/config.py`
- `web/env_store.py`
- `web/services/condition_run_status.py`
- `web/services/egress_gateway.py`
- `web/services/openai_qa.py`
- `web/services/playwright_executor.py`
- `web/services/qa/advanced_generator.py`
- `web/services/qa/doc_generator.py`
- `web/services/qa/helpers.py`
- `web/services/run_store.py`
- `web/services/test_design_settings.py`
- `web/services/testcase_spec_generator.py`
- `web/services/usage_tracker.py`
- `web/validation.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `flask` | flask==3.1.3 |

### 3-3. 環境変数

- なし

### 3-4. 呼び出す API（受け側に実在が必要）

- `/api/coverage-heatmap`
- `/api/test-design`
- `/api/test-design/by-screen`
- `/api/testcases/table`

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

- `テストケースタブの絞り込み結果（該当ケースのみ）`
- `絞り込み条件と件数の明示`

### 永続化

- なし

### 失敗経路（すべて実際に踏むこと）

- grid_not_loaded_when_filter_applied
- filter_matches_nothing_silently
- no_way_to_clear_the_filter
- keyboard_cannot_follow_the_link
- approximate_match_presented_as_exact

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
