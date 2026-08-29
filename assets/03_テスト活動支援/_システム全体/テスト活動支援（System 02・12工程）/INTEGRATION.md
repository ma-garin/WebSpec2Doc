# 組み込み手順: テスト活動支援（System 02・12工程）

| 項目 | 値 |
|---|---|
| feature_id | `test_activity_support` |
| 版 | `20260829-81e4c84` |
| 生成元 | `WebSpec2Doc` @ `81e4c84` |
| 生成日時 (UTC) | 2026-08-29T11:24:09Z |
| リスク / 状態 | high / implemented |
| 同梱ファイル数 | 36 |
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
| `web/routes/test_activity.py` | 20388 | `45de838ed3d9` |

### サービス / コア（6 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `web/services/completion_criteria.py` | 4486 | `81346b507250` |
| `web/services/defect_store.py` | 8234 | `3fd468df07e0` |
| `web/services/manual_execution_store.py` | 6210 | `6498633ce101` |
| `web/services/process_gate.py` | 5992 | `1d8e6c178852` |
| `web/services/test_data_store.py` | 9464 | `157bd83ff3c8` |
| `web/services/ta_ai.py` | 13870 | `5ab480685bec` |

### UI（テンプレート・JS・CSS）（29 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `templates/partials/view-ta-analysis.html` | 7950 | `2dac06d2993d` |
| `templates/partials/view-ta-codefix.html` | 7382 | `705cdb777111` |
| `templates/partials/view-ta-completion.html` | 3392 | `8aa0ffddff30` |
| `templates/partials/view-ta-defect.html` | 8222 | `dd4187c7ca8a` |
| `templates/partials/view-ta-design.html` | 7208 | `7320e2d56631` |
| `templates/partials/view-ta-execution.html` | 6765 | `b26318c89f07` |
| `templates/partials/view-ta-home.html` | 8705 | `0046b42c2149` |
| `templates/partials/view-ta-implementation.html` | 10443 | `1a76d510045a` |
| `templates/partials/view-ta-integrations.html` | 11884 | `72330ae476c9` |
| `templates/partials/view-ta-manual.html` | 7805 | `f0cf3c0fa1c0` |
| `templates/partials/view-ta-plan.html` | 14360 | `8637dd78286d` |
| `templates/partials/view-ta-strategy.html` | 4820 | `cf205a7b892d` |
| `static/js/ta-ai-panel.js` | 8812 | `a0626611209f` |
| `static/js/ta-analysis.js` | 20062 | `5f843834acfc` |
| `static/js/ta-codefix.js` | 10878 | `1c3584e831bd` |
| `static/js/ta-completion.js` | 9334 | `e6e5520f816a` |
| `static/js/ta-defect.js` | 20482 | `22978f7f93d8` |
| `static/js/ta-design.js` | 16479 | `e8392501bce8` |
| `static/js/ta-execution.js` | 20220 | `1ee66193fbe3` |
| `static/js/ta-home.js` | 13781 | `79a7ec7427b5` |
| `static/js/ta-implementation.js` | 8995 | `b3157d316d68` |
| `static/js/ta-integrations.js` | 10496 | `31f8f45bd2f7` |
| `static/js/ta-manual.js` | 15444 | `77ae09c7151c` |
| `static/js/ta-plan.js` | 12834 | `81b6d7c3d42c` |
| `static/js/ta-process-gate.js` | 7704 | `f705d01d7c30` |
| `static/js/ta-process-nav.js` | 4564 | `00549a9a76cd` |
| `static/js/ta-strategy.js` | 4649 | `d4abf03d5447` |
| `static/css/ta-design-system.css` | 26534 | `0b0b89409ac1` |
| `static/css/test-activity.css` | 7236 | `894b57acf7a2` |

## 2. 配線する

### 2-1. Blueprint を登録する

受け側の `web/__init__.py`（アプリケーションファクトリ）に追記する。

```python
from web.routes import test_activity
app.register_blueprint(test_activity.bp)
```

| Blueprint | url_prefix | 定義元 |
|---|---|---|
| `test_activity` | `(なし)` | `web/routes/test_activity.py` |

### 2-2. SPA シェルに差し込む

受け側の `templates/index.html` に追記する（本リポジトリと同じ配線規約）。

```jinja
{% include 'partials/view-ta-analysis.html' %}
{% include 'partials/view-ta-codefix.html' %}
{% include 'partials/view-ta-completion.html' %}
{% include 'partials/view-ta-defect.html' %}
{% include 'partials/view-ta-design.html' %}
{% include 'partials/view-ta-execution.html' %}
{% include 'partials/view-ta-home.html' %}
{% include 'partials/view-ta-implementation.html' %}
{% include 'partials/view-ta-integrations.html' %}
{% include 'partials/view-ta-manual.html' %}
{% include 'partials/view-ta-plan.html' %}
{% include 'partials/view-ta-strategy.html' %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/ta-design-system.css') }}?v={{ _ver }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/test-activity.css') }}?v={{ _ver }}">
<script src="{{ url_for('static', filename='js/ta-ai-panel.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/ta-analysis.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/ta-codefix.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/ta-completion.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/ta-defect.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/ta-design.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/ta-execution.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/ta-home.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/ta-implementation.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/ta-integrations.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/ta-manual.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/ta-plan.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/ta-process-gate.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/ta-process-nav.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/ta-strategy.js') }}?v={{ _ver }}"></script>
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

- `src/llm/openai_client.py`
- `src/llm/prompt_guard.py`
- `web/auth.py`
- `web/config.py`
- `web/routes/qa_process.py`
- `web/services/__init__.py`
- `web/services/qa/helpers.py`
- `web/services/testcase_table_store.py`
- `web/tenancy.py`
- `web/validation.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `flask` | flask==3.1.3 |
| `werkzeug` | **本リポジトリの requirements.txt に記載なし・要確認** |

### 3-3. 環境変数

- なし

### 3-4. 呼び出す API（受け側に実在が必要）

- `/api/doc-fusion`
- `/api/history`
- `/api/history/runs`
- `/api/integrations`
- `/api/integrations/jira/issues`
- `/api/llm/chat`
- `/api/reference-docs`
- `/api/result`
- `/api/settings/test-design`
- `/api/ta/ai/generate`
- `/api/ta/completion`
- `/api/ta/datasets`
- `/api/ta/defects`
- `/api/ta/export`
- `/api/ta/manual-runs`
- `/api/ta/process`
- `/api/ta/process/complete`
- `/api/ta/process/reopen`
- `/api/ta/rca`
- `/api/testcases/live-progress`
- `/api/testcases/run`
- `/api/testcases/table`
- `/preview`

### 3-5. データファイル

- なし

### 3-6. 同梱外のテンプレート / 静的ファイル参照

- なし

### 3-7. 同梱 JS が参照するグローバル

他アセット由来のものが混ざっていれば、そのアセットも併せて受け渡す。

- `TA_PROCESS`
- `switchView`
- `taAiPanel`
- `taProcessGate`

## 3-8. 併せて渡す必要のある他機能の資産

このアセットと対で動くが、**別の機能契約に属している**ファイル。
受け側に無ければ、その機能のアセットも別途エクスポートして渡す。

- なし

## 4. このアセットが提供する API

| メソッド | ルール | 定義元 |
|---|---|---|
| GET | `/api/ta/datasets` | `web/routes/test_activity.py` |
| POST | `/api/ta/datasets` | `web/routes/test_activity.py` |
| DELETE | `/api/ta/datasets/<dataset_id>` | `web/routes/test_activity.py` |
| GET | `/api/ta/manual-runs` | `web/routes/test_activity.py` |
| POST | `/api/ta/manual-runs` | `web/routes/test_activity.py` |
| GET | `/api/ta/defects` | `web/routes/test_activity.py` |
| POST | `/api/ta/defects` | `web/routes/test_activity.py` |
| PATCH | `/api/ta/defects/<defect_id>` | `web/routes/test_activity.py` |
| GET | `/api/ta/completion` | `web/routes/test_activity.py` |
| POST | `/api/ta/ai/generate` | `web/routes/test_activity.py` |
| POST | `/api/ta/rca` | `web/routes/test_activity.py` |
| GET | `/api/ta/export` | `web/routes/test_activity.py` |
| GET | `/api/ta/process` | `web/routes/test_activity.py` |
| POST | `/api/ta/process/complete` | `web/routes/test_activity.py` |
| POST | `/api/ta/process/reopen` | `web/routes/test_activity.py` |

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `output/<domain>/defects/`
- `output/<domain>/process/`
- `output/<domain>/qa_process/`

### 永続化

- `output/<domain>/defects/*.json`
- `output/<domain>/process/state.json`

### 失敗経路（すべて実際に踏むこと）

- domain 未指定で 400 を返す
- 対象ドメインが存在しない場合に空の一覧を返す
- 工程ゲートで未到達工程をロックする
- LLM 未設定時に 503 と理由を返す
- 外部連携（GitHub 等）の認証情報が未設定の場合は操作を無効化し理由を表示する

### 対応テスト

- `tests/test_ta_process_gate.py`
- `tests/test_ta_defect_store.py`

## 6. 未検証事項（エクスポート側の申告）

- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる
  URL・実行時にのみ解決される参照は検出できない。
- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**
  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。
- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。
