# タスク: Phase 2-B — ローカルURL許可トグルのサーバーAPI追加

## ゴール

`WEBSPEC2DOC_ALLOW_LOCAL` 環境変数を GUI から切り替えられるよう、
Flask の設定エンドポイントに 2 本の API を追加する。

**なぜ必要か**: 現在、社内ステージングやローカル開発環境（`localhost`, `*.local`）への
クロールは `WEBSPEC2DOC_ALLOW_LOCAL=1` を `.env` に手動記載しないと使えない。
これが第三者検証会社・開発者ペルソナの離脱要因になっている（Phase 2 施策）。

クローラーは `subprocess` で `src/main.py` を起動し、その中で `load_dotenv()` を呼ぶ。
よって `.env` を更新すれば次回クロール時に自動反映される。Flask 本体は `.env` を
ロードしないため、`os.environ` の書き換えは不要。

---

## 触るファイル（これ以外は変更しない）

- `web/routes/settings.py` — 2 エンドポイントを追加
- `tests/test_settings_allow_local.py` — 新規テストファイル

**変更禁止**:
- `src/crawler/url_safety.py`（`ALLOW_LOCAL_ENV` 定数はそのまま）
- `web/env_store.py`（`_read_env` / `_write_env` をそのまま使う）
- `web/config.py`
- JavaScript / テンプレート / CSS（UI は Claude が担当）
- git 操作（commit は Claude が行う）

---

## 既存コードの参照（パターン踏襲）

`web/env_store.py` の `_read_env()` / `_write_env()` と
`web/config.py` の `ENV_KEY_RE` が使えるインフラ。
`web/routes/settings.py` の既存エンドポイントと同じスタイルで実装する。

### `web/routes/settings.py` の現在の末尾（追記位置）

```python
# ファイル末尾に追記する（既存の post_settings 関数の後）

from src/crawler/url_safety.py に `ALLOW_LOCAL_ENV = "WEBSPEC2DOC_ALLOW_LOCAL"` が定義済み。
ただしここでは文字列リテラル `"WEBSPEC2DOC_ALLOW_LOCAL"` を直接使って依存を増やさないこと。
```

---

## 実装の指示

### 1. `GET /api/settings/allow-local`

`.env` の `WEBSPEC2DOC_ALLOW_LOCAL` の値を読んで返す。

```
レスポンス: {"allow_local": <bool>}
```

- `_read_env()` で `.env` を読む
- `env.get("WEBSPEC2DOC_ALLOW_LOCAL", "") == "1"` が `True` なら `allow_local: true`
- それ以外は `allow_local: false`

### 2. `POST /api/settings/allow-local`

JSON ボディ `{"enabled": true|false}` を受け取り `.env` を書き換える。

```
リクエスト: Content-Type: application/json, ボディ: {"enabled": true}
レスポンス: {"ok": true, "allow_local": <bool>}
```

- `request.get_json()` でパース。`None` または `"enabled"` キーなしは 400 を返す
- `enabled=True` なら `_write_env({"WEBSPEC2DOC_ALLOW_LOCAL": "1"})`
- `enabled=False` なら `_write_env({"WEBSPEC2DOC_ALLOW_LOCAL": ""})`
  - 注: `_write_env` は空文字でも `.env` に行を書く（削除でなく空セット）。これで OK。
- 更新後に `_read_env()` で再読みして `allow_local` を返す（書いた値を echo）

### セキュリティノート

- SSRF 保護の opt-in バイパスなので、`enabled` の値は bool 型のみ受け付ける
- `request.get_json(force=False, silent=True)` を使い、JSON 以外のボディは 400 を返す
- ログに変更を記録する（`logging.warning("WEBSPEC2DOC_ALLOW_LOCAL changed to %s", ...)`）

---

## テストの指示（`tests/test_settings_allow_local.py`）

既存の `tests/test_api_v1.py` のパターンを参考にする:
- `import app as appmod` → `appmod.app.test_client()` で Flask テストクライアント
- `monkeypatch` で `.env` への副作用を tmp_path に向ける

```python
# 必要な import
from __future__ import annotations
import json
from pathlib import Path
import pytest
import app as appmod
import web.routes.settings as settings_mod

def _client():
    return appmod.app.test_client()
```

### テストケース（最低5件）

1. `test_get_allow_local_default_false`
   - `.env` が存在しない（tmp_path 内）→ `GET /api/settings/allow-local` → `{"allow_local": false}`

2. `test_get_allow_local_true_when_env_set`
   - tmp_path に `.env` を作り `WEBSPEC2DOC_ALLOW_LOCAL=1` を書いておく
   - `GET /api/settings/allow-local` → `{"allow_local": true}`

3. `test_post_allow_local_enable`
   - `POST /api/settings/allow-local` with `{"enabled": true}`
   - ステータス 200 / `{"ok": true, "allow_local": true}`
   - `.env` を実際に読んで `WEBSPEC2DOC_ALLOW_LOCAL=1` が書かれていること

4. `test_post_allow_local_disable`
   - まず enabled=true でセット後、`{"enabled": false}` で無効化
   - `{"ok": true, "allow_local": false}` / `.env` の値が `""` になること

5. `test_post_allow_local_invalid_json_returns_400`
   - Content-Type を application/json にして `"not-json"` を送る
   - ステータス 400

### monkeypatch の使い方

```python
def test_xxx(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_mod, "ENV_FILE", tmp_path / ".env")
    # または web.env_store の ENV_FILE を patch する
    # settings.py は web.env_store._read_env / _write_env 経由で ENV_FILE を使う
```

`web/config.py` の `ENV_FILE = Path(".env")` を `monkeypatch` で差し替えてよい。
`web.config.ENV_FILE` / `web.env_store` どちらの参照を patch するかは実装を見て判断すること。

---

## 完了条件

- [ ] `GET /api/settings/allow-local` と `POST /api/settings/allow-local` が追加されている
- [ ] `bash scripts/verify.sh` が `ALL GREEN`（pytest 含む）
- [ ] `tests/test_settings_allow_local.py` が 5 件以上存在し、すべて PASS する
- [ ] 変更が上記「触るファイル」内に収まっている

---

## スコープ外（やらないこと）

- JavaScript / HTML テンプレート / CSS の変更（UI は Claude が担当）
- `url_safety.py` の変更（既存ロジックをそのまま使う）
- `os.environ` の書き換え（`.env` に書くだけで次回起動時に反映される）
- git 操作（commit は Claude が行う）
- 既存テストの書き換え（壊れる場合は Claude に報告するだけでよい）

---

## 参照ファイル（読むと実装の手がかりになる）

- `web/routes/settings.py` — 既存パターン（`_read_env`/`_write_env`/`_mask_key` の使い方）
- `web/env_store.py` — `_read_env()` / `_write_env()` の実装
- `web/config.py` — `ENV_FILE`, `ENV_KEY_RE`
- `src/crawler/url_safety.py` — `ALLOW_LOCAL_ENV = "WEBSPEC2DOC_ALLOW_LOCAL"` の定数名
- `tests/test_api_v1.py` — Flask テストクライアントのパターン
