# 組み込み手順: ユーザーメニューと利用者フィードバック送信

| 項目 | 値 |
|---|---|
| feature_id | `user_menu_feedback` |
| 版 | `20260829-34d52a3` |
| 生成元 | `WebSpec2Doc` @ `34d52a3` |
| 生成日時 (UTC) | 2026-08-29T09:32:19Z |
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

### ルート（API）（1 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `web/routes/feedback.py` | 2854 | `05bca31f81bb` |

### サービス / コア（1 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `web/services/feedback_store.py` | 5860 | `14ebf9f4cdfc` |

### UI（テンプレート・JS・CSS）（8 件）

| パス | bytes | sha256 (先頭12) |
|---|---:|---|
| `templates/partials/topbar.html` | 4753 | `10e95e944ca2` |
| `templates/partials/view-account.html` | 3314 | `966a1af61677` |
| `templates/partials/view-feedback.html` | 2457 | `7e96ae77ca62` |
| `static/css/user-menu.css` | 3176 | `15b7d8c33f75` |
| `static/css/account-view.css` | 11800 | `5964be2979da` |
| `static/js/user-menu.js` | 2614 | `46b0c823b0b2` |
| `static/js/account-view.js` | 5647 | `5f2527c94b00` |
| `static/js/feedback-view.js` | 3208 | `ce7dc8227893` |

## 2. 配線する

### 2-1. Blueprint を登録する

受け側の `web/__init__.py`（アプリケーションファクトリ）に追記する。

```python
from web.routes import feedback
app.register_blueprint(feedback.bp)
```

| Blueprint | url_prefix | 定義元 |
|---|---|---|
| `feedback` | `(なし)` | `web/routes/feedback.py` |

### 2-2. SPA シェルに差し込む

受け側の `templates/index.html` に追記する（本リポジトリと同じ配線規約）。

```jinja
{% include 'partials/topbar.html' %}
{% include 'partials/view-account.html' %}
{% include 'partials/view-feedback.html' %}
<link rel="stylesheet" href="{{ url_for('static', filename='css/user-menu.css') }}?v={{ _ver }}">
<link rel="stylesheet" href="{{ url_for('static', filename='css/account-view.css') }}?v={{ _ver }}">
<script src="{{ url_for('static', filename='js/user-menu.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/account-view.js') }}?v={{ _ver }}"></script>
<script src="{{ url_for('static', filename='js/feedback-view.js') }}?v={{ _ver }}"></script>
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

- `web/auth.py`
- `web/tenancy.py`

### 3-2. サードパーティ

| import 名 | requirements の指定 |
|---|---|
| `flask` | flask==3.1.3 |
| `werkzeug` | **本リポジトリの requirements.txt に記載なし・要確認** |

### 3-3. 環境変数

- なし

### 3-4. 呼び出す API（受け側に実在が必要）

- `/api/auth/api-tokens`
- `/api/auth/api-tokens/`
- `/api/auth/me`
- `/api/auth/password`
- `/api/feedback`

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
| POST | `/api/feedback` | `web/routes/feedback.py` |
| GET | `/api/feedback` | `web/routes/feedback.py` |

## 5. 受け入れ確認（契約より）

組み込み後、受け側で次を確認する。**本バンドルの生成時には実行していない。**

### 出力

- `トップバーのユーザーメニュー（個人設定 / ユーザーガイド / フィードバック / ログアウト）`
- `個人設定ビュー（/account）とフィードバックビュー（/feedback）`
- `フィードバックの送信結果メッセージ`
- `/api/feedback JSON`

### 永続化

- `instance/tenants/{slug}/feedback.jsonl`

### 失敗経路（すべて実際に踏むこと）

- empty_or_oversized_message_rejected
- invalid_category_rejected
- write_failure_reported_not_silently_dropped
- identity_forged_by_client_ignored
- broken_line_does_not_break_listing
- non_admin_cannot_read_feedback

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
