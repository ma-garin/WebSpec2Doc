# 組み込み手順: テスト技法の網羅的適用（分類ツリー法・直交表・原因結果グラフ・ドメイン分析・エラー推測・ユースケース）

| 項目 | 値 |
|---|---|
| feature_id | `autorun_extended_techniques` |
| 版 | `20260829-5345533` |
| 生成元 | `WebSpec2Doc` @ `5345533` |
| 生成日時 (UTC) | 2026-08-29T07:50:12Z |
| リスク / 状態 | high / implemented |
| 同梱ファイル数 | 11 |
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
| `web/routes/autorun_stages.py` | 22599 | `bdc0b19a6d30` |

### サービス / コア（8 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `src/autorun/classification_tree.py` | 9384 | `fcdbc775d48b` |
| `src/autorun/orthogonal_array.py` | 8035 | `b9a4a24ccb35` |
| `src/autorun/cause_effect.py` | 10779 | `874fa0e1220b` |
| `src/autorun/domain_analysis.py` | 8703 | `c7ad973ae243` |
| `src/autorun/error_guessing.py` | 13521 | `9bcc1a66d4e1` |
| `src/autorun/use_case_testing.py` | 11971 | `852d756b81d9` |
| `src/autorun/techniques.py` | 16068 | `74947c22ca8a` |
| `src/autorun/stages.py` | 50949 | `03029be4e207` |

### UI（テンプレート・JS・CSS）（2 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `templates/partials/view-auto-run.html` | 27151 | `1e5f7d80fcdd` |
| `static/js/autorun-stages.js` | 31671 | `5c7d40c582cd` |

## 2. 配線する

### 2-1. Blueprint を登録する

受け側の `web/__init__.py`（アプリケーションファクトリ）に追記する。

```python
from web.routes import autorun_stages
app.register_blueprint(autorun_stages.bp)
```

| Blueprint | url_prefix | 定義元 |
|---|---|---|
| `autorun_stages` | `(なし)` | `web/routes/autorun_stages.py` |

### 2-2. SPA シェルに差し込む

受け側の `templates/index.html` に追記する（本リポジトリと同じ配線規約）。

```jinja
{% include 'partials/view-auto-run.html' %}
<script src="{{ url_for('static', filename='js/autorun-stages.js') }}?v={{ _ver }}"></script>
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

- `src/autorun/decisions.py`
- `src/autorun/qf_schema.py`
- `src/autorun/review_queue.py`
- `src/autorun/suggest.py`
- `src/llm/activity_log.py`
- `web/config.py`
- `web/routes/auto_run.py`
- `web/tenancy.py`
- `web/validation.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `flask` | flask==3.1.3 |

### 3-3. 環境変数

- なし

### 3-4. 呼び出す API（受け側に実在が必要）

- `/api/autorun/stages`
- `/api/autorun/stages/adopt`
- `/api/autorun/stages/approve`
- `/api/autorun/stages/generate`
- `/api/autorun/stages/item`
- `/api/autorun/stages/proceed`
- `/api/autorun/stages/skip`
- `/api/autorun/stages/suggest`
- `/api/autorun/stages/testcases`

### 3-5. データファイル

- なし

### 3-6. 同梱外のテンプレート / 静的ファイル参照

- なし

### 3-7. 同梱 JS が参照するグローバル

他アセット由来のものが混ざっていれば、そのアセットも併せて受け渡す。

- `_autoRunLastData`
- `autorunCancel`
- `autorunChat`
- `autorunDecisions`
- `autorunLeadBar`
- `autorunStages`

## 3-8. 併せて渡す必要のある他機能の資産

このアセットと対で動くが、**別の機能契約に属している**ファイル。
受け側に無ければ、その機能のアセットも別途エクスポートして渡す。

- なし

## 4. このアセットが提供する API

| メソッド | ルール | 定義元 |
|---|---|---|
| GET | `/api/autorun/stages` | `web/routes/autorun_stages.py` |
| GET | `/api/autorun/decisions` | `web/routes/autorun_stages.py` |
| POST | `/api/autorun/decisions` | `web/routes/autorun_stages.py` |
| GET | `/api/autorun/review-queue` | `web/routes/autorun_stages.py` |
| POST | `/api/autorun/review-queue/auto-approve` | `web/routes/autorun_stages.py` |
| POST | `/api/autorun/stages/generate` | `web/routes/autorun_stages.py` |
| POST | `/api/autorun/stages/approve` | `web/routes/autorun_stages.py` |
| POST | `/api/autorun/stages/skip` | `web/routes/autorun_stages.py` |
| POST | `/api/autorun/stages/item` | `web/routes/autorun_stages.py` |
| POST | `/api/autorun/stages/reset` | `web/routes/autorun_stages.py` |
| POST | `/api/autorun/stages/suggest` | `web/routes/autorun_stages.py` |
| POST | `/api/autorun/stages/adopt` | `web/routes/autorun_stages.py` |
| POST | `/api/autorun/stages/proceed` | `web/routes/autorun_stages.py` |
| GET | `/api/autorun/stages/testcases` | `web/routes/autorun_stages.py` |

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `分類ツリーとクラス被覆の組合せ表`
- `直交表（均等割付け・直交性検査の結果付き）`
- `原因結果グラフと導出された判定表`
- `1x1 ドメイン行列（ON/OFF/IN/OUT）`
- `欠陥タクソノミの適用結果（未実測である旨付き）`
- `ユースケース候補（基本/代替/例外フロー）`

### 永続化

- `instance/autorun/{run_id}/stages.json`

### 失敗経路（すべて実際に踏むこと）

- no_measured_constraints
- too_many_levels_for_orthogonal_array
- no_transitions_observed
- unknown_field_type

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
