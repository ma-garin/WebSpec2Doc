# タスク: P1-6 — 技法詳細タブの折りたたみ改善

**優先度**: P1（今すぐ）  
**背景**: 技法詳細タブは全画面が展開表示され、20画面超だと非常に長くなる。ユーザーから「ケースが見づらい」と指摘あり。

## ゴール

`技法詳細` タブの各画面ブロックを `<details>` 要素でラップし、デフォルト折りたたみにする。
「全展開」「全折りたたみ」ボタンを追加する。

## 触るファイル

- `static/js/view-design.js` — `renderTechniqueDetail()` の HTML 生成部分を変更
- `static/app-report.css` — details/summary のスタイルを追加（最小限）

**変更禁止**:
- `src/analyzer/technique_recommender.py`
- `static/js/results.js`

## 実装の指針

### `renderTechniqueDetail()` の変更（`view-design.js`）

現在の構造（画面ごとの div）を以下に変更:

```html
<!-- ヘッダー: 全展開・全折りたたみボタン -->
<div class="technique-detail-header">
  <button id="td-expand-all">全展開</button>
  <button id="td-collapse-all">全折りたたみ</button>
</div>

<!-- 画面ごとに <details> でラップ -->
<details class="technique-detail-screen">
  <summary class="technique-detail-summary">
    <strong>P001</strong> ログイン画面 — 推奨技法: ep, bva, st
  </summary>
  <!-- 既存のケーステーブル -->
</details>
```

### イベントリスナー

```js
document.getElementById('td-expand-all')?.addEventListener('click', () => {
  document.querySelectorAll('.technique-detail-screen').forEach(d => d.open = true);
});
document.getElementById('td-collapse-all')?.addEventListener('click', () => {
  document.querySelectorAll('.technique-detail-screen').forEach(d => d.open = false);
});
```

## 完了条件

- [ ] 技法詳細タブを開いた時、各画面ブロックがデフォルト折りたたみで表示される
- [ ] 「全展開」で全画面が開く
- [ ] 「全折りたたみ」で全画面が閉じる
- [ ] summary にページID・ページ名・推奨技法一覧が表示される
- [ ] `python -m pytest tests/ -q` が全 PASS
- [ ] `make verify-ui` が PASS

## スコープ外

- 折りたたみ状態の localStorage 保存
- アニメーション追加
