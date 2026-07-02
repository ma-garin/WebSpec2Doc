# タスク: Phase 2-B — ローカルURL許可トグル（API + UI）

**優先度**: P2  
**背景**: 社内ステージング等のプライベートアドレスをGUIから許可できるようにする。現状はCLIの環境変数 `WEBSPEC2DOC_ALLOW_LOCAL=1` のみ。

## ゴール

設定画面に「ローカルURLを許可」トグルを追加し、GUIから `WEBSPEC2DOC_ALLOW_LOCAL` を切り替えられるようにする。

---

## Step 1: サーバーAPI（`web/routes/settings.py`）

`GET /api/settings/allow-local` と `POST /api/settings/allow-local` を追加する。

```python
@bp.get('/api/settings/allow-local')
def get_allow_local():
    return jsonify({'allow_local': os.environ.get('WEBSPEC2DOC_ALLOW_LOCAL') == '1'})

@bp.post('/api/settings/allow-local')
def set_allow_local():
    value = request.json.get('allow_local', False)
    if value:
        os.environ['WEBSPEC2DOC_ALLOW_LOCAL'] = '1'
    else:
        os.environ.pop('WEBSPEC2DOC_ALLOW_LOCAL', None)
    return jsonify({'ok': True})
```

**注意**: プロセス内環境変数の変更のみ。永続化しない（再起動でリセット）。

---

## Step 2: 設定画面UI（`static/js/settings.js` + `templates/partials/view-settings.html`）

「クロール設定」セクションにトグルを追加:

```html
<label class="checkbox-chip">
  <input type="checkbox" id="allow-local-toggle">
  ローカルURL（192.168.x.x / localhost 等）を許可
</label>
<p style="font-size:12px;color:var(--text-muted)">
  ※ SSRF保護が無効になります。社内ステージング環境専用。
</p>
```

```js
// 初期値取得
fetch('/api/settings/allow-local')
  .then(r => r.json())
  .then(d => { document.getElementById('allow-local-toggle').checked = d.allow_local; });

// 変更時
document.getElementById('allow-local-toggle')?.addEventListener('change', e => {
  fetch('/api/settings/allow-local', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ allow_local: e.target.checked }),
  });
});
```

---

## 触るファイル

- `web/routes/settings.py`
- `static/js/settings.js`
- `templates/partials/view-settings.html`
- `tests/test_settings.py` — APIエンドポイントのテストを追加

## 完了条件

- [ ] `GET /api/settings/allow-local` が `{"allow_local": bool}` を返す
- [ ] `POST /api/settings/allow-local` でトグルが切り替わる
- [ ] 設定画面にトグルが表示される
- [ ] トグルON時にローカルURLのクロールが通る
- [ ] `python -m pytest tests/ -q` が全 PASS
- [ ] `make verify-ui` が PASS
