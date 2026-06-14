# タスク: Phase 2-A — QAビューの空白状態を解消する

## ゴール

QAツールビュー（品質観点・自動テスト候補・QAモデル）を開いたとき、
解析済みサイトが1件以上あれば**自動で最初のサイトを選択**し、コンテンツを即時表示する。
サイトが0件のときは、「生成ウィザードへ」誘導バナーを表示する。

**なぜ必要か**: 現在は `<option value="">解析済みサイトを選択</option>` がデフォルト選択のため、
サイトを選び直すまで本文エリアが空白になる（体験の離脱要因）。

---

## 触るファイル（これ以外は変更しない）

- `static/js/qa-tools.js` — `loadQaToolSites()` に自動選択ロジックを追加

**変更禁止**:
- `templates/partials/*.html`（HTML構造変更なし）
- `web/routes/*.py`
- `static/app.css` や `static/css/` ファイル（スタイル変更なし）
- git 操作（commit は Claude が行う）

---

## 既存コードの参照（必ず読んでから実装すること）

`static/js/qa-tools.js` の `loadQaToolSites(viewName, force)` を読む。
現在のコード（関連箇所）:

```js
// 現在: 全ビューのドロップダウンを埋めるが、最初の選択はしない
for (const toolName of Object.keys(QA_TOOL_CONFIG)) {
  const select = document.getElementById(QA_TOOL_CONFIG[toolName].select);
  if (!select) continue;
  const previous = select.value;
  select.innerHTML = '<option value="">解析済みサイトを選択</option>' +
    items.map(it => `<option value="${escHtml(it.domain)}">${escHtml(it.domain)}</option>`).join('');
  if (previous && items.some(it => it.domain === previous)) select.value = previous;
}
qaToolSitesLoaded = true;
setQaToolStatus(viewName, items.length
  ? '対象サイトを選択してください。'
  : '解析済みサイトがありません。先にサイトを追加してください。');
```

`loadQaToolData(viewName, domain)` の `domain` が空文字のときの空白メッセージ表示も確認すること。

---

## 実装の指示

### 1. 自動選択ロジック

`loadQaToolSites()` の各ドロップダウン更新ループの中で、
`previous` が未選択 (`""`) かつ `items.length > 0` のとき、
`select.value = items[0].domain` をセットする。

```
条件: !previous && items.length > 0
処理: select.value = items[0].domain
```

### 2. 自動選択後にコンテンツをトリガー

ループの後、`viewName` に対応する select の値が決まったら、
`loadQaToolData(viewName, selectEl.value)` を呼び出す。
（`selectEl.value` が空文字の場合は呼ばない）

### 3. 0件のときの誘導メッセージ

`items.length === 0` のとき、`setQaToolStatus` で表示するメッセージを以下に変更:

```
解析済みサイトがありません。「+ サイトを追加」から最初のサイトを登録してください。
```

また、全ビューのコンテンツエリア（`cfg.content` の要素）に以下 HTML を置く:

```html
<div class="empty" style="text-align:center;padding:40px 20px">
  <p style="font-size:15px;font-weight:700;margin-bottom:8px">まだ解析済みサイトがありません</p>
  <p style="font-size:13px;color:var(--text-muted);margin-bottom:20px">
    生成ウィザードでサイトを解析すると、ここにデータが表示されます。
  </p>
  <button type="button" class="btn-primary qa-empty-goto-wizard"
    style="height:40px;padding:0 24px;font-size:14px">
    生成ウィザードへ →
  </button>
</div>
```

ボタンにイベントを付ける:
```js
document.querySelectorAll('.qa-empty-goto-wizard').forEach(btn => {
  btn.addEventListener('click', () => {
    // core.js の switchView 関数でウィザードビューへ遷移
    const navItem = document.querySelector('.app-nav-item[data-view="generate"]');
    if (navItem) navItem.click();
  });
});
```

---

## 変更しないこと

- `QA_TOOL_CONFIG` の構造
- `loadQaToolData` の本体ロジック
- `setQaToolStatus` のシグネチャ
- HTML テンプレート（`templates/partials/*.html`）

---

## 完了条件

- [ ] QAビューを開いたとき、解析済みサイトが1件以上あれば最初のサイトが自動選択されコンテンツが表示される
- [ ] サイト0件のとき「生成ウィザードへ →」ボタンが表示される
- [ ] ボタンクリックで生成ビューに遷移する
- [ ] `python -m pytest tests/ -q` が全 PASS する（JS変更のみのため既存テストに影響しないはず）
- [ ] 変更が `static/js/qa-tools.js` のみに収まっている

---

## スコープ外（やらないこと）

- HTML テンプレートの変更
- CSS の追加（既存の `.btn-primary` / `.empty` クラスを使うこと）
- 新しい API エンドポイントの追加
- git 操作
