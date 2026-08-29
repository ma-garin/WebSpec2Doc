# 組み込み手順: ログイン / セッション

| 項目 | 値 |
|---|---|
| feature_id | `login` |
| 版 | `20260829-5345533` |
| 生成元 | `WebSpec2Doc` @ `5345533` |
| 生成日時 (UTC) | 2026-08-29T07:50:11Z |
| リスク / 状態 | critical / implemented |
| 同梱ファイル数 | 9 |
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
| `web/routes/login.py` | 9843 | `1af6d8415c0a` |

### サービス / コア（6 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `src/crawler/auto_login.py` | 9774 | `71f81db594f9` |
| `src/analyzer/login_wall.py` | 1638 | `505c882f611d` |
| `src/crawler/auth_recorder.py` | 13067 | `99cd8b738900` |
| `src/crawler/auth.py` | 2430 | `1f60e9992c24` |
| `src/crawler/login_signal.py` | 864 | `f029eef578f9` |
| `src/crawler/session_guard.py` | 1088 | `7212619600ba` |

### UI（テンプレート・JS・CSS）（2 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `templates/partials/view-generate.html` | 21038 | `da6646d5d332` |
| `static/js/wizard.js` | 39556 | `3d6ef279e605` |

## 2. 配線する

### 2-1. Blueprint を登録する

受け側の `web/__init__.py`（アプリケーションファクトリ）に追記する。

```python
from web.routes import login
app.register_blueprint(login.bp)
```

| Blueprint | url_prefix | 定義元 |
|---|---|---|
| `login` | `(なし)` | `web/routes/login.py` |

### 2-2. SPA シェルに差し込む

受け側の `templates/index.html` に追記する（本リポジトリと同じ配線規約）。

```jinja
{% include 'partials/view-generate.html' %}
<script src="{{ url_for('static', filename='js/wizard.js') }}?v={{ _ver }}"></script>
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

- `src/crawler/link_extractor.py`
- `src/crawler/page_crawler.py`
- `web/config.py`
- `web/tenancy.py`
- `web/validation.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `flask` | flask==3.1.3 |
| `playwright` | playwright==1.61.0 |

### 3-3. 環境変数

- なし

### 3-4. 呼び出す API（受け側に実在が必要）

- `/api/cancel`
- `/api/discover-stream`
- `/api/login/record/cancel`
- `/api/login/record/complete`
- `/api/login/record/start`
- `/api/login/record/status`
- `/api/login/scrape`
- `/api/login/simple`
- `/api/login/submit`
- `/api/reference-docs`

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
| POST | `/api/login/simple` | `web/routes/login.py` |
| POST | `/api/login/scrape` | `web/routes/login.py` |
| POST | `/api/login/submit` | `web/routes/login.py` |
| POST | `/api/login/record/start` | `web/routes/login.py` |
| GET | `/api/login/record/status` | `web/routes/login.py` |
| POST | `/api/login/record/complete` | `web/routes/login.py` |
| POST | `/api/login/record/cancel` | `web/routes/login.py` |

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `auth.json`
- `login wall status`
- `login record status (.login_status.json)`

### 永続化

- `output/{domain}/auth.json`
- `output/{domain}/.login_signal`
- `output/{domain}/.login_status.json`

### 失敗経路（すべて実際に踏むこと）

- invalid_credentials
- mfa_required
- session_expired
- display_missing
- recorder_timeout
- browser_closed

### 対応テスト

- `happy_path`
- `error_path`
- `session_expiry_path`
- `evidence`
- `timeout_path`
- `cancel_path`

## 6. 未検証事項（エクスポート側の申告）

- 本バンドルの依存一覧は **静的解析による棚卸し**。動的 import・文字列組み立てによる
  URL・実行時にのみ解決される参照は検出できない。
- 実行検証（pytest / verify-ui / 実画面操作）は **未実行**
  （`.claude/rules/speed-harness.md` H-7 に従い、要求時のみ実行する）。
- 受け側での組み込み後の動作確認は **受け側の責任範囲**。第 5 節を実行して初めて完了とする。
