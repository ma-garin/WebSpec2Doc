# 組み込み手順: 現新比較モード（移行検証支援）

| 項目 | 値 |
|---|---|
| feature_id | `old_new_comparison` |
| 版 | `20260829-34d52a3` |
| 生成元 | `WebSpec2Doc` @ `34d52a3` |
| 生成日時 (UTC) | 2026-08-29T09:32:20Z |
| リスク / 状態 | high / implemented |
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

### ルート（API）（1 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `web/routes/history.py` | 14845 | `6a74dcf728a7` |

### サービス / コア（10 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `src/diff/pair_matcher.py` | 5184 | `c415d46aba9e` |
| `src/diff/comparison.py` | 26226 | `63724f9cc71a` |
| `src/diff/link_checker.py` | 5408 | `9a9f99ea83ce` |
| `src/diff/screenshot_diff.py` | 23741 | `4b18624aff68` |
| `src/diff/snapshot.py` | 10140 | `fc1c8fabd4ee` |
| `src/diff/differ.py` | 11714 | `77dba116e9d8` |
| `src/generator/comparison_reporter.py` | 14977 | `77c0f977bf47` |
| `src/analyzer/text_similarity.py` | 1048 | `e18c10a4b240` |
| `web/services/comparison_workspace.py` | 10226 | `f3b98b1fb9a9` |
| `src/main.py` | 62520 | `f051a3bef57a` |

### UI（テンプレート・JS・CSS）（4 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `static/js/view-compare.js` | 19492 | `9f9a579365a3` |
| `static/js/results.js` | 33264 | `454d49c8a241` |
| `static/app-report.css` | 49653 | `398642d43725` |
| `templates/partials/view-generate.html` | 21038 | `da6646d5d332` |

## 2. 配線する

### 2-1. Blueprint を登録する

受け側の `web/__init__.py`（アプリケーションファクトリ）に追記する。

```python
from web.routes import history
app.register_blueprint(history.bp)
```

| Blueprint | url_prefix | 定義元 |
|---|---|---|
| `history` | `(なし)` | `web/routes/history.py` |

### 2-2. SPA シェルに差し込む

受け側の `templates/index.html` に追記する（本リポジトリと同じ配線規約）。

```jinja
{% include 'partials/view-generate.html' %}
<link rel="stylesheet" href="{{ url_for('static', filename='app-report.css') }}?v={{ _ver }}">
<script src="{{ url_for('static', filename='js/view-compare.js') }}?v={{ _ver }}"></script>
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

- `src/analyzer/canonicalizer.py`
- `src/analyzer/form_analyzer.py`
- `src/analyzer/html_analyzer.py`
- `src/analyzer/rule_injector.py`
- `src/analyzer/stack_detector.py`
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
- `src/crawler/politeness.py`
- `src/crawler/session_guard.py`
- `src/crawler/url_safety.py`
- `src/diff/impact_analyzer.py`
- `src/generator/accessibility_reporter.py`
- `src/generator/architecture_generator.py`
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
- `src/registry/site_registry.py`
- `src/ux/axe_runner.py`
- `src/viewport/runner.py`
- `web/config.py`
- `web/summary.py`
- `web/tenancy.py`
- `web/validation.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `Pillow` | Pillow>=11.0.0 |
| `flask` | flask==3.1.3 |
| `networkx` | networkx==3.3 |
| `numpy` | numpy>=2.0.0 |
| `playwright` | playwright==1.61.0 |
| `python-dotenv` | python-dotenv==1.2.2 |

### 3-3. 環境変数

- `OPENAI_API_KEY`
- `WEBSPEC2DOC_RECORD_HEADLESS`

### 3-4. 呼び出す API（受け側に実在が必要）

- `/api/`
- `/api/doc-fusion`
- `/api/export/spec-xlsx`
- `/api/result`
- `/api/snapshot-comparison.json`
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

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `comparison.json`
- `comparison.html`
- `old/dynamic_masks.json`
- `comparison.html「網羅性サマリ」節`
- `comparison.html「見た目の変化」節（before/after 並置＋変更領域の赤枠）`
- `new/screenshot_diffs/{page_id}.png`

### 永続化

- `output/{domain}/compare_*/old/`
- `output/{domain}/compare_*/new/`
- `output/{domain}/compare_*/new/screenshot_diffs/`
- `output/{domain}/compare_*/comparison.json`
- `output/{domain}/compare_*/comparison.html`

### 失敗経路（すべて実際に踏むこと）

- one_side_empty
- no_pairs
- link_timeout
- screenshot_missing
- mask_detection_failed
- diff_overlay_unavailable_without_pillow
- insignificant_diff_shown_as_change
- diff_boxes_cover_the_whole_page

### 対応テスト

- `happy_path`
- `error_path`
- `evidence`
- `unclassified_fallback`

## 6. 未検証事項（エクスポート側の申告）

- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる
  URL・実行時にのみ解決される参照は検出できない。
- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**
  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。
- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。
