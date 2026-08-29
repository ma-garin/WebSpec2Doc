# 組み込み手順: ステップ編集（ノーコードでテストを組み立てる）

| 項目 | 値 |
|---|---|
| feature_id | `nocode_step_editor` |
| 版 | `20260829-81e4c84` |
| 生成元 | `WebSpec2Doc` @ `81e4c84` |
| 生成日時 (UTC) | 2026-08-29T11:24:09Z |
| リスク / 状態 | high / implemented |
| 同梱ファイル数 | 5 |
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
| `web/routes/test_steps.py` | 6366 | `35c1dd236dad` |

### サービス / コア（1 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `web/services/test_step_store.py` | 16475 | `6d63ed80a293` |

### UI（テンプレート・JS・CSS）（3 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `templates/partials/view-ta-implementation.html` | 10443 | `1a76d510045a` |
| `static/js/test-step-editor.js` | 12362 | `7ddfbb9d17db` |
| `static/css/test-step-editor.css` | 2881 | `b05d915524c4` |

## 2. 配線する

### 2-1. Blueprint を登録する

受け側の `web/__init__.py`（アプリケーションファクトリ）に追記する。

```python
from web.routes import test_steps
app.register_blueprint(test_steps.bp)
```

| Blueprint | url_prefix | 定義元 |
|---|---|---|
| `test_steps` | `(なし)` | `web/routes/test_steps.py` |

### 2-2. SPA シェルに差し込む

受け側の `templates/index.html` に追記する（本リポジトリと同じ配線規約）。

```jinja
{% include 'partials/view-ta-implementation.html' %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/test-step-editor.css') }}?v={{ _ver }}">
<script src="{{ url_for('static', filename='js/test-step-editor.js') }}?v={{ _ver }}"></script>
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

- `web/config.py`
- `web/services/__init__.py`
- `web/tenancy.py`
- `web/validation.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `flask` | flask==3.1.3 |

### 3-3. 環境変数

- なし

### 3-4. 呼び出す API（受け側に実在が必要）

- `/api/test-steps/`
- `/api/test-steps/actions`
- `/api/test-steps/sites`

### 3-5. データファイル

- なし

### 3-6. 同梱外のテンプレート / 静的ファイル参照

- なし

### 3-7. 同梱 JS が参照するグローバル

他アセット由来のものが混ざっていれば、そのアセットも併せて受け渡す。

- `nsReload`

## 3-8. 併せて渡す必要のある他機能の資産

このアセットと対で動くが、**別の機能契約に属している**ファイル。
受け側に無ければ、その機能のアセットも別途エクスポートして渡す。

| ファイル | 所属する機能 | 関係 |
|---|---|---|
| `static/js/ta-implementation.js` | `test_activity_support` | `templates/partials/view-ta-implementation.html` を動かす JS と見られるが未同梱 |

## 4. このアセットが提供する API

| メソッド | ルール | 定義元 |
|---|---|---|
| GET | `/api/test-steps/actions` | `web/routes/test_steps.py` |
| GET | `/api/test-steps/sites` | `web/routes/test_steps.py` |
| GET | `/api/test-steps/<domain>` | `web/routes/test_steps.py` |
| PUT | `/api/test-steps/<domain>` | `web/routes/test_steps.py` |
| POST | `/api/test-steps/<domain>/import` | `web/routes/test_steps.py` |
| POST | `/api/test-steps/<domain>/generate` | `web/routes/test_steps.py` |

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `output/<domain>/qa_process/test_steps.json`
- `output/<domain>/qa_process/edited.spec.ts`

### 永続化

- `output/<domain>/qa_process/test_steps.json`

### 失敗経路（すべて実際に踏むこと）

- 未知の動作・重複 test_id・空ステップは、どこが悪いか名指しして 400 で拒否する
- 対象や値が必要な動作でそれが空なら保存させない（画面側も入力欄を無効化する）
- 画面を開く の値が http(s) URL でなければ拒否する
- 保存済みファイルが壊れている場合は空として上書きせず 409 で知らせる
- 取り込みは保存せず候補を返すのみ（既存の編集を勝手に消さない）
- 未保存の状態で生成しようとした場合は先に保存を促す

### 対応テスト

- `happy_path`
- `validation_path`
- `error_path`
- `evidence`

## 6. 未検証事項（エクスポート側の申告）

- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる
  URL・実行時にのみ解決される参照は検出できない。
- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**
  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。
- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。
