# タスク: Phase 2-B UI — ローカルURL許可トグルを設定画面に追加

## 前提

このタスクは `docs/tasks/codex-phase2-b-allow-local-api.md` の **API が実装済み** であることを前提とする。
`GET /api/settings/allow-local` と `POST /api/settings/allow-local` が存在しない場合は実装を中断し、
その旨をコメントに残すこと。

## ゴール

設定画面の「クロール既定値」タブに `WEBSPEC2DOC_ALLOW_LOCAL` トグルを追加する。
チェックをオンにすると `localhost` / `*.local` / プライベートIPへのクロールが有効になる。

**なぜ必要か**: 社内ステージングや開発環境をクロールするには現在 `.env` を手動編集する必要があり、
第三者検証会社・開発者ペルソナの離脱要因になっている。

---

## 触るファイル（これ以外は変更しない）

- `templates/partials/view-settings.html` — クロール既定値パネルにトグル行を追加
- `static/js/settings.js` — 読み込みと保存の関数を追加

**変更禁止**:
- `web/routes/settings.py`（API は Phase 2-B API タスク側で実装済み）
- `static/app.css` / `static/css/` ファイル（スタイル変更なし）
- 他の HTML テンプレート
- git 操作（commit は Claude が行う）

---

## 既存コードの参照（必ず読んでから実装すること）

### `templates/partials/view-settings.html`

`set-panel-crawl` セクションを読む。現在の末尾付近:

```html
<div class="set-panel" id="set-panel-crawl">
  <div class="input-card">
    <h2 class="set-card-title">クロール既定値</h2>
    ...
    <div class="options-grid">
      <div class="field">...</div>
      <div class="field">...</div>
      <div class="field full">...</div>
    </div>
    <button class="btn-primary" id="save-settings" ...>設定を保存</button>
    <div class="settings-msg" id="settings-msg">...</div>
  </div>
</div>
```

### `static/js/settings.js`

`loadServerSettings()` と `saveApiKey()` のパターンを参考にする。
`fetch('/api/settings')` / `fetch('/api/settings', {method:'POST', body: form})` の実装スタイル。

---

## 実装の指示

### 1. `templates/partials/view-settings.html`

`set-panel-crawl` の `.options-grid` の**直後**（`<button ... id="save-settings"` の直前）に
以下のブロックを挿入する:

```html
<div class="field full" style="margin-top:18px;padding-top:18px;border-top:1px solid var(--border)">
  <label class="checkbox-chip" style="align-items:flex-start;gap:10px">
    <input type="checkbox" id="allow-local-toggle" style="margin-top:2px">
    <span>
      <strong>ローカル/ステージング環境のクロールを許可</strong>
      <br>
      <span style="font-size:12px;color:var(--text-muted)">
        <code>localhost</code>・<code>*.local</code>・プライベートIPへのクロールを有効にします。
        <br>
        <span style="color:var(--warn,#c08c00)">⚠️ 信頼できる環境でのみ使用してください（SSRF保護をバイパスします）。</span>
      </span>
    </span>
  </label>
  <div class="settings-msg" id="allow-local-msg" style="margin-top:8px">保存しました</div>
</div>
```

### 2. `static/js/settings.js`

#### 2-1. `loadServerSettings()` の拡張

既存の `loadServerSettings()` 関数の `try` ブロック末尾（`} catch (e)` の直前）に追加:

```js
// ローカルクロール許可トグル
await loadAllowLocalToggle();
```

#### 2-2. 新規関数 `loadAllowLocalToggle()`

ファイル末尾に追記:

```js
async function loadAllowLocalToggle() {
  try {
    const data = await fetch('/api/settings/allow-local').then(r => r.json());
    const el = document.getElementById('allow-local-toggle');
    if (el) el.checked = !!data.allow_local;
  } catch (e) { /* トグル読み込み失敗は無視 */ }
}
```

#### 2-3. 新規関数 `saveAllowLocal()`

ファイル末尾に追記:

```js
async function saveAllowLocal() {
  const enabled = document.getElementById('allow-local-toggle')?.checked ?? false;
  try {
    const res = await fetch('/api/settings/allow-local', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    });
    const data = await res.json();
    if (data.ok) {
      const msg = document.getElementById('allow-local-msg');
      if (msg) { msg.classList.add('show'); setTimeout(() => msg.classList.remove('show'), 2000); }
    }
  } catch (e) { /* トースト通知があれば呼ぶ */ }
}
```

#### 2-4. イベントリスナー登録

ファイル末尾（既存の `document.getElementById('save-settings')?.addEventListener` の近く）に追記:

```js
document.getElementById('allow-local-toggle')?.addEventListener('change', saveAllowLocal);
```

---

## セキュリティノート

- チェックボックスの `change` イベントで即時保存（保存ボタン不要）。
- 警告テキスト「SSRF保護をバイパスします」は必ず表示すること（削除禁止）。
- `escHtml()` 等のサニタイズは今回不要（ユーザー入力をHTMLに埋め込まない）。

---

## 完了条件

- [ ] 設定画面の「クロール既定値」タブにトグルが表示される
- [ ] ページ読み込み時に `GET /api/settings/allow-local` の値でチェック状態が初期化される
- [ ] チェック変更時に `POST /api/settings/allow-local` が呼ばれ「保存しました」が表示される
- [ ] `python -m pytest tests/ -q` が全 PASS する（既存テストに影響しないはず）
- [ ] 変更が上記「触るファイル」の2ファイルのみに収まっている

---

## スコープ外（やらないこと）

- `web/routes/settings.py` の変更（API は実装済みのはず）
- CSS の追加（`.checkbox-chip` / `.settings-msg` / `var(--border)` は既存クラスを使う）
- git 操作
- 保存ボタンのフォームに組み込むこと（change イベントで即時保存が正しい）
