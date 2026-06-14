# タスク: Phase 4-4 — favicon 404 を解消する

## ゴール

ブラウザコンソールに出ている `GET /favicon.ico 404` を解消する。
`W` 文字を青い丸角背景に載せた SVG ファビコンを作成し、HTML に参照を追加する。

---

## 触るファイル（これ以外は変更しない）

- `static/favicon.svg` — 新規作成（SVGファビコン）
- `templates/index.html` — `<head>` に `<link rel="icon">` を追加

**変更禁止**:
- `app.py` / Flask ルーティング（静的ファイルは Flask が自動配信）
- CSS / JS ファイル
- git 操作（commit は Claude が行う）

---

## 実装の指示

### 1. `static/favicon.svg` を新規作成

以下の内容をそのまま書き込む:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="6" fill="#2563EB"/>
  <text x="16" y="23" font-family="Arial,Helvetica,sans-serif" font-size="19"
        font-weight="700" fill="white" text-anchor="middle">W</text>
</svg>
```

### 2. `templates/index.html` の `<head>` 内に追加

`<meta charset="utf-8">` などの既存 `<meta>` タグの直後（`<title>` より前）に挿入:

```html
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
```

> Flask は `static/` 以下のファイルを `/static/<path>` で自動配信するため、
> ルート追加は不要。

---

## 完了条件

- [ ] `static/favicon.svg` が存在する
- [ ] `templates/index.html` に `<link rel="icon">` が追加されている
- [ ] `python -m pytest tests/ -q` が全 PASS する（既存テストに影響しないはず）
- [ ] ブラウザで `http://127.0.0.1:8765/static/favicon.svg` にアクセスすると SVG が表示される

---

## スコープ外（やらないこと）

- `.ico` 形式の生成（SVG で十分。IE11 は対象外）
- Flask ルートの追加
- git 操作
