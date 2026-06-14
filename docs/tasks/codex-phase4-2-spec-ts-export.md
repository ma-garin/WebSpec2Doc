# タスク: Phase 4-2 — レポートから .spec.ts を直接エクスポートする

## ゴール

レポートビュー（ステップ4）のエクスポートドロップダウンに
「↓ Playwright .spec.ts」ボタンを追加する。
クリックすると `playwright_candidates.json` から `.spec.ts` を生成してダウンロードする。

**なぜ必要か**: AutoRun を経由しないとテストコードを取得できず、
「解析 → すぐ Playwright で使いたい」ペルソナの離脱要因になっている。

---

## 触るファイル（これ以外は変更しない）

- `web/routes/report.py` — `GET /api/report/<domain>/spec-ts` エンドポイントを追加
- `static/js/view-export-settings.js` — エクスポートドロップダウンにボタンを追加

**変更禁止**:
- `web/services/spec_ts_generator.py`（既存ロジックをそのまま使う）
- `web/routes/auto_run.py`（AutoRun の spec.ts 生成は別経路）
- `templates/partials/*.html`
- git 操作（commit は Claude が行う）

---

## 既存コードの参照（必ず読んでから実装すること）

### `web/services/spec_ts_generator.py`

`generate_spec_ts(domain, candidates_path, output_path, filter_mode)` が実装済み。
`candidates_path` は `playwright_candidates.json` のパス。

### `web/routes/report.py`

既存の `download()` / `download_zip()` エンドポイントのパターンを参考にする:
```python
@bp.get("/download")
def download() -> Response:
    ...
    return send_file(target, as_attachment=True, download_name=target.name)
```
`from flask import send_file` が既に import されているか確認すること。

### `web/config.py`

`OUTPUT_DIR = Path("output")` が定義されている。
`playwright_candidates.json` のパスは:
`OUTPUT_DIR / domain / "qa" / "playwright_candidates.json"`

### `static/js/view-export-settings.js`

エクスポートドロップダウンのボタンを動的に追加している関数を読む。
`/download?path=...` パターンでファイルダウンロードを実装している。

---

## 実装の指示

### 1. `web/routes/report.py` に新規エンドポイントを追加

```python
import tempfile
from pathlib import Path

from web.services.spec_ts_generator import generate_spec_ts
from web.validation import _valid_domain  # 既存のバリデーション関数

@bp.get("/api/report/<domain>/spec-ts")
def download_spec_ts(domain: str):
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    candidates_path = OUTPUT_DIR / domain / "qa" / "playwright_candidates.json"
    if not candidates_path.exists():
        return {"error": "playwright_candidates.json が見つかりません。先に QA 分析を実行してください。"}, 404
    filter_mode = request.args.get("filter", "all")
    if filter_mode not in ("all", "smoke", "transition", "form"):
        filter_mode = "all"
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / f"{domain}.spec.ts"
        generate_spec_ts(domain, candidates_path, out_path, filter_mode=filter_mode)
        return send_file(
            out_path,
            as_attachment=True,
            download_name=f"{domain}.spec.ts",
            mimetype="text/plain",
        )
```

> 注意: `send_file` はファイルが存在する間だけ機能する。`TemporaryDirectory` が
> レスポンス送信前に消えないよう、`send_file` のレスポンスを返す前に内容を読む。
> `send_file` は Flask がレスポンスを送信するまでファイルを保持するので問題ない。
> ただしOSによってはコンテキストマネージャ終了時に削除されるため、
> `out_path.read_bytes()` で内容を読んで `io.BytesIO` 経由で返す方が安全:

```python
import io
from flask import send_file

# TemporaryDirectory を使わず直接メモリで返す
@bp.get("/api/report/<domain>/spec-ts")
def download_spec_ts(domain: str):
    if not _valid_domain(domain):
        return {"error": "invalid domain"}, 400
    candidates_path = OUTPUT_DIR / domain / "qa" / "playwright_candidates.json"
    if not candidates_path.exists():
        return {"error": "playwright_candidates.json が見つかりません"}, 404
    filter_mode = request.args.get("filter", "all")
    if filter_mode not in ("all", "smoke", "transition", "form"):
        filter_mode = "all"
    import tempfile
    from pathlib import Path as _Path
    with tempfile.TemporaryDirectory() as tmp:
        out = _Path(tmp) / f"{domain}.spec.ts"
        generate_spec_ts(domain, candidates_path, out, filter_mode=filter_mode)
        content = out.read_bytes()
    buf = io.BytesIO(content)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"{domain}.spec.ts", mimetype="text/plain")
```

### 2. `static/js/view-export-settings.js` にボタンを追加

エクスポートドロップダウンを構築している関数（`buildExportMenu` 等）を読む。
`playwright_candidates.json` が存在するかどうかは、現在のレポートデータから判断できないため、
ボタンを常に表示し、404 時にトースト通知を表示する方針で実装する。

ドロップダウンメニューに以下のボタンを追加（他のエクスポートボタンの後）:

```js
// Playwright .spec.ts ダウンロード
const specTsBtn = document.createElement('button');
specTsBtn.type = 'button';
specTsBtn.className = 'export-dropdown-item';
specTsBtn.textContent = '↓ Playwright .spec.ts';
specTsBtn.addEventListener('click', () => {
  const domain = currentDomain; // 既存の domain 変数を使う
  if (!domain) return;
  window.location.href = `/api/report/${encodeURIComponent(domain)}/spec-ts?filter=all`;
});
menu.appendChild(specTsBtn);
```

> 既存のエクスポートドロップダウンが `currentDomain` や `domain` をどう参照しているかを
> 確認してから実装すること。変数名は実際のコードに合わせる。

---

## 完了条件

- [ ] `GET /api/report/<domain>/spec-ts` が 200 で `.spec.ts` を返す
- [ ] `playwright_candidates.json` が存在しない場合は 404 を返す
- [ ] エクスポートドロップダウンに「↓ Playwright .spec.ts」ボタンが表示される
- [ ] `python -m pytest tests/ -q` が全 PASS する
- [ ] `web/routes/report.py` と `static/js/view-export-settings.js` のみ変更されている

---

## スコープ外（やらないこと）

- フィルターモード選択 UI（クエリパラメータ `filter=all` 固定で十分）
- `spec_ts_generator.py` の変更
- git 操作
