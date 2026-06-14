# タスク: Phase 4-3 — 非エンジニア向け / 技術者向けビューを切り替える

## ゴール

レポートビュー（ステップ4）の結果バーに「ビュー切り替え」トグルを追加する。

- **サマリービュー**（非エンジニア向け）: 概要・画面別仕様・テスト条件・画面遷移図のみ表示
- **詳細ビュー**（技術者向け）: 全8タブを表示（現在のデフォルト）

選択はブラウザの `localStorage` に保存し、次回起動時も維持する。

**なぜ必要か**: ステークホルダーや品質管理職は「設計・技法詳細・遷移表・履歴」タブが
ノイズになっている。「必要な人に必要なタブだけ」を出すことで信頼性が上がる。

---

## 触るファイル（これ以外は変更しない）

- `static/js/results.js` — ビュー切り替えロジックとタブ表示制御
- `templates/partials/view-generate.html` — トグルボタンの HTML を追加

**変更禁止**:
- CSS ファイル（既存の `display:none` で制御）
- 他のビューファイル（dashboard / settings 等）
- git 操作（commit は Claude が行う）

---

## 既存コードの参照（必ず読んでから実装すること）

### `templates/partials/view-generate.html`

`result-bar` 内の構造:
```html
<div class="result-bar">
  <div class="result-tabs" role="tablist" ...>
    <button ... data-tab="overview">概要</button>
    <button ... data-tab="report">画面別仕様</button>
    <button ... data-tab="matrix">テスト条件</button>
    <button ... data-tab="design">設計</button>
    <button ... data-tab="technique-detail">技法詳細</button>
    <button ... data-tab="transition">画面遷移図</button>
    <button ... data-tab="transition-table">遷移表</button>
    <button ... data-tab="history">履歴・差分</button>
  </div>
  <div class="result-bar-actions">
    <button ... id="r-maximize-btn">⛶ 最大化</button>
    <button ... id="r-new-btn">ダッシュボードへ</button>
  </div>
</div>
```

### `static/js/results.js`

タブ切り替えロジック（`data-tab` を使った `is-active` 制御）を読む。

---

## 実装の指示

### 1. `templates/partials/view-generate.html` にトグルを追加

`result-bar-actions` の `id="r-maximize-btn"` の直前に挿入:

```html
<div class="view-mode-toggle" style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-muted)">
  <span>ビュー:</span>
  <button type="button" id="view-mode-summary" class="btn-outline-sm view-mode-btn is-active"
    style="font-size:11px;padding:2px 8px" title="概要・仕様・テスト条件・遷移図のみ">サマリー</button>
  <button type="button" id="view-mode-detail" class="btn-outline-sm view-mode-btn"
    style="font-size:11px;padding:2px 8px" title="全タブを表示">詳細</button>
</div>
```

### 2. `static/js/results.js` にロジックを追加

#### 2-1. 定数定義（ファイル先頭付近に追加）

```js
const VIEW_MODE_KEY = 'wsd_view_mode'; // localStorage キー
// サマリービューで非表示にするタブの data-tab 値
const SUMMARY_HIDE_TABS = new Set(['design', 'technique-detail', 'transition-table', 'history']);
```

#### 2-2. `applyViewMode(mode)` 関数を追加

```js
function applyViewMode(mode) {
  // 'summary' または 'detail'
  const tabs = document.querySelectorAll('.result-tabs .result-tab[data-tab]');
  tabs.forEach(tab => {
    const hide = mode === 'summary' && SUMMARY_HIDE_TABS.has(tab.dataset.tab);
    tab.style.display = hide ? 'none' : '';
    // 非表示になったタブが選択中の場合は「概要」に切り替える
    if (hide && tab.classList.contains('is-active')) {
      document.querySelector('.result-tab[data-tab="overview"]')?.click();
    }
  });
  // ボタンの is-active を更新
  document.getElementById('view-mode-summary')?.classList.toggle('is-active', mode === 'summary');
  document.getElementById('view-mode-detail')?.classList.toggle('is-active', mode !== 'summary');
  // localStorage に保存
  try { localStorage.setItem(VIEW_MODE_KEY, mode); } catch (_) {}
}
```

#### 2-3. イベント登録と初期化（ファイル末尾に追加）

```js
document.getElementById('view-mode-summary')?.addEventListener('click', () => applyViewMode('summary'));
document.getElementById('view-mode-detail')?.addEventListener('click', () => applyViewMode('detail'));

// 初期化: 保存済みモードを反映（デフォルトは 'summary'）
(function initViewMode() {
  let saved = 'summary';
  try { saved = localStorage.getItem(VIEW_MODE_KEY) || 'summary'; } catch (_) {}
  applyViewMode(saved);
}());
```

---

## 完了条件

- [ ] レポートビューに「サマリー」「詳細」ボタンが表示される
- [ ] サマリーモードで「設計・技法詳細・遷移表・履歴・差分」タブが非表示になる
- [ ] 詳細モードで全8タブが表示される
- [ ] ページリロード後も選択したモードが維持される
- [ ] `python -m pytest tests/ -q` が全 PASS する
- [ ] 変更が `results.js` と `view-generate.html` のみに収まっている

---

## スコープ外（やらないこと）

- CSS クラスの追加（`display:none` / `display:''` のインライン制御で十分）
- タブカウントバッジ（非表示タブのバッジは隠れても構わない）
- URL パラメータへの永続化
- git 操作
