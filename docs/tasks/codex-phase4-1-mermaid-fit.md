# タスク: Phase 4-1 — 遷移図の初期表示を Fit に自動化する

## ゴール

遷移図タブを開いたとき、図がビューポートに収まった状態（Fit済み）で初期表示される。
現在は zoom=100% で表示されるため、大きな遷移図がはみ出す。

**なぜ必要か**: 初回表示で図がはみ出すと、ユーザーは Fit ボタンを自分で探す必要があり、
「壊れている」と誤解される。

---

## 触るファイル（これ以外は変更しない）

- `static/js/view-transition.js` — Mermaid 描画完了後に `_fitUmlZoom()` を自動呼び出し

**変更禁止**:
- `templates/partials/*.html`
- CSS ファイル
- git 操作（commit は Claude が行う）

---

## 既存コードの参照（必ず読んでから実装すること）

`static/js/view-transition.js` の以下の関数を読む:

```js
// 現在の _showUmlPanel の末尾（Mermaid 描画を開始する部分）
function _showUmlPanel(type, screens) {
  ...
  umlZoom = 1;          // ← ここで zoom=1 にリセット
  area.innerHTML = ...;  // ← HTML を構築
  _loadMermaid(() => _renderUmlDiagram(type, screens, rows)); // ← 描画開始
}

// 既存の Fit 関数
function _fitUmlZoom() {
  const canvas = document.getElementById('uml-render-target');
  const stage = document.getElementById('uml-zoom-stage');
  if (!canvas || !stage) return;
  const canvasW = canvas.clientWidth;
  const baseWidth = parseInt(stage.dataset.baseWidth || stage.offsetWidth, 10);
  const next = Math.min(1.0, (canvasW - 40) / (baseWidth || 1));
  _setUmlZoom(next);
}
```

`_renderUmlDiagram` の末尾でも Mermaid のレンダリングが完了する。
`_fitUmlZoom()` は SVG の実寸が確定した後に呼ぶ必要がある。

---

## 実装の指示

### 変更箇所: `_showUmlPanel` の `_loadMermaid` 呼び出し部分

`_loadMermaid(() => _renderUmlDiagram(type, screens, rows))` を以下のように変更:

```js
_loadMermaid(() => {
  _renderUmlDiagram(type, screens, rows);
  // Mermaid SVG の描画が完了してから Fit を適用する（100ms で十分）
  setTimeout(_fitUmlZoom, 100);
});
```

**なぜ setTimeout が必要か**: `_renderUmlDiagram` 内の Mermaid レンダリングは
非同期で SVG を DOM に書き込む。100ms 後には SVG の実寸が確定しているため、
`_fitUmlZoom()` が正しい幅を取得できる。

### 変更してはいけないこと

- `umlZoom = 1` の初期化（必要）
- `_fitUmlZoom()` 本体
- `_setUmlZoom()` 本体
- ズームコントロールボタンのロジック

---

## 完了条件

- [ ] 遷移図タブを開いたとき、図が自動で幅に収まって表示される
- [ ] 手動 Fit ボタンは引き続き動作する
- [ ] 全画面ボタン（⛶）押下時の Fit も引き続き動作する
- [ ] `python -m pytest tests/ -q` が全 PASS する

---

## スコープ外（やらないこと）

- 全画面時の Fit ロジック変更（既存の `setTimeout(() => _fitUmlZoom(), 50)` を触らない）
- ズーム保持（画面切り替えのたびに Fit が再適用されて構わない）
- git 操作
