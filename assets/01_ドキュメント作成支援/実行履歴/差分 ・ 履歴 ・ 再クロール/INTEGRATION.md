# 組み込み手順: 差分 / 履歴 / 再クロール

| 項目 | 値 |
|---|---|
| feature_id | `diff_history` |
| 版 | `20260829-34d52a3` |
| 生成元 | `WebSpec2Doc` @ `34d52a3` |
| 生成日時 (UTC) | 2026-08-29T09:32:20Z |
| リスク / 状態 | critical / implemented |
| 同梱ファイル数 | 15 |
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

### ルート（API）（3 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `web/routes/history.py` | 14845 | `6a74dcf728a7` |
| `web/routes/site.py` | 2102 | `182d46fa54cd` |
| `web/routes/runs.py` | 7513 | `e13e33a5b716` |

### サービス / コア（5 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `src/diff/snapshot.py` | 10140 | `fc1c8fabd4ee` |
| `src/diff/differ.py` | 11714 | `77dba116e9d8` |
| `src/registry/site_registry.py` | 2908 | `6d48d69e3d73` |
| `src/diff/impact_analyzer.py` | 8507 | `bd566da0cf09` |
| `web/services/run_store.py` | 17526 | `794bae53d53a` |

### UI（テンプレート・JS・CSS）（7 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `static/js/history.js` | 8469 | `f6e36ff3c539` |
| `static/js/recrawl.js` | 6235 | `05cd6dfee467` |
| `static/js/results.js` | 33264 | `454d49c8a241` |
| `static/js/view-run-result.js` | 14233 | `79b50219af5d` |
| `templates/partials/view-run-history.html` | 7906 | `ba96674f9380` |
| `templates/partials/view-run-result.html` | 667 | `d1220bd5ae9e` |
| `static/js/view-run-history.js` | 24602 | `d40199fe0efd` |

## 2. 配線する

### 2-1. Blueprint を登録する

受け側の `web/__init__.py`（アプリケーションファクトリ）に追記する。

```python
from web.routes import history, runs, site
app.register_blueprint(history.bp)
app.register_blueprint(runs.bp)
app.register_blueprint(site.bp)
```

| Blueprint | url_prefix | 定義元 |
|---|---|---|
| `history` | `(なし)` | `web/routes/history.py` |
| `site` | `(なし)` | `web/routes/site.py` |
| `runs` | `(なし)` | `web/routes/runs.py` |

### 2-2. SPA シェルに差し込む

受け側の `templates/index.html` に追記する（本リポジトリと同じ配線規約）。

```jinja
{% include 'partials/view-run-history.html' %}
{% include 'partials/view-run-result.html' %}
<script src="{{ url_for('static', filename='js/history.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/recrawl.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/results.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/view-run-result.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/view-run-history.js') }}?v={{ _ver }}"></script>
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
- `src/analyzer/stack_detector.py`
- `src/crawler/page_crawler.py`
- `src/diff/comparison.py`
- `src/generator/comparison_reporter.py`
- `src/generator/diff_reporter.py`
- `web/config.py`
- `web/services/__init__.py`
- `web/services/comparison_workspace.py`
- `web/services/run_trends.py`
- `web/summary.py`
- `web/tenancy.py`
- `web/validation.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `flask` | flask==3.1.3 |

### 3-3. 環境変数

- なし

### 3-4. 呼び出す API（受け側に実在が必要）

- `/api/`
- `/api/doc-fusion`
- `/api/export/spec-xlsx`
- `/api/history`
- `/api/history/runs`
- `/api/history/runs/`
- `/api/result`
- `/api/runs/`
- `/api/site`
- `/api/site/`
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

- `_appBooted`
- `rtSetSites`

## 3-8. 併せて渡す必要のある他機能の資産

このアセットと対で動くが、**別の機能契約に属している**ファイル。
受け側に無ければ、その機能のアセットも別途エクスポートして渡す。

- なし

## 4. このアセットが提供する API

| メソッド | ルール | 定義元 |
|---|---|---|
| GET | `/api/history` | `web/routes/history.py` |
| DELETE | `/api/site/<domain>` | `web/routes/history.py` |
| GET | `/api/snapshots` | `web/routes/history.py` |
| GET | `/api/snapshot-diff` | `web/routes/history.py` |
| GET | `/api/snapshot-diff-summary` | `web/routes/history.py` |
| GET | `/api/snapshot-comparison` | `web/routes/history.py` |
| GET | `/api/snapshot-comparison.json` | `web/routes/history.py` |
| GET | `/api/site` | `web/routes/site.py` |
| GET | `/runs/<domain>/<run_id>` | `web/routes/runs.py` |
| GET | `/api/runs/<domain>` | `web/routes/runs.py` |
| GET | `/api/run-trends/sites` | `web/routes/runs.py` |
| GET | `/api/runs/<domain>/trends` | `web/routes/runs.py` |
| GET | `/api/runs/<domain>/<run_id>` | `web/routes/runs.py` |
| GET | `/api/runs/<domain>/<run_id>/exists` | `web/routes/runs.py` |
| GET | `/api/runs/<domain>/<run_id>/artifact` | `web/routes/runs.py` |

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `snapshots`
- `diff_report.html`
- `site.json`

### 永続化

- `output/{domain}/snapshots/`
- `output/{domain}/site.json`

### 失敗経路（すべて実際に踏むこと）

- missing_snapshot
- session_expired_false_diff
- snapshot_overwrite
- login_required_flags_lost_on_recrawl
- recrawl_lands_on_overview_instead_of_diff
- diff_shown_without_stating_compared_snapshots

### 対応テスト

- `happy_path`
- `breaking_change_path`
- `error_path`
- `evidence`

## 6. 未検証事項（エクスポート側の申告）

- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる
  URL・実行時にのみ解決される参照は検出できない。
- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**
  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。
- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。
