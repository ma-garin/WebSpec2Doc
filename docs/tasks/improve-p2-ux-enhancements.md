# タスク: P2 — UX 小改善 2本

**優先度**: P2  
**背景**: テスト観点マップの CSV エクスポートと、概要タブの動的な次アクション提案。どちらも JS のみで実装可能な小改善。

---

## 機能A: テスト観点マップ CSV ダウンロード

**対象ファイル**: `static/js/view-quality.js`, `templates/partials/view-quality.html`（または対応パーシャル）

「品質観点」ビューの「テスト観点マップ」セクションに「↓ CSV」ボタンを追加する。

```js
function exportViewpointsCsv(rows) {
  const headers = ['カテゴリ', '観点', 'リスクレベル', '確認例'];
  const lines = [headers, ...rows.map(r =>
    [r.category, r.viewpoint, r.risk_level, r.example_cases?.join('|') ?? '']
  )];
  const csv = lines.map(cols =>
    cols.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')
  ).join('\n');
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' });
  const a = Object.assign(document.createElement('a'),
    { href: URL.createObjectURL(blob), download: 'viewpoints.csv' });
  a.click();
  URL.revokeObjectURL(a.href);
}
```

**完了条件**:
- [ ] 「↓ CSV」ボタンが観点マップセクションに表示される
- [ ] クリックで `viewpoints.csv` がダウンロードされる（BOM付き、Excel対応）

---

## 機能B: 概要タブの「次のアクション」動的化

**対象ファイル**: `static/js/view-overview.js`

クロール結果に応じて動的な案内カードを表示する。

| 条件 | メッセージ | ジャンプ先 |
|------|-----------|----------|
| フォームが5件以上 | 「入力フォームが{n}件あります → テスト条件で絞り込みましょう」 | matrix |
| 遷移先3以上の画面あり | 「複数の遷移がある画面があります → テストモデリングで確認」 | transition |
| 必須項目が0件 | 「必須項目が検出されませんでした → 仕様の確認を推奨します」 | report |
| デフォルト | 「設計タブでテスト技法推奨マトリクスを確認しましょう」 | design |

```js
function _buildNextActionHints(report) {
  const hints = [];
  const fields = report.fields_total ?? 0;
  const required = report.required_total ?? 0;
  const maxTrans = Math.max(0, ...(report.screens ?? []).map(s => (s.links ?? []).length));
  if (fields >= 5)   hints.push({ msg: `入力フォームが${fields}件あります — テスト条件で絞り込みましょう`, tab: 'matrix' });
  if (maxTrans >= 3) hints.push({ msg: '複数の遷移がある画面があります — テストモデリングで確認', tab: 'transition' });
  if (required === 0) hints.push({ msg: '必須項目が検出されませんでした — 仕様の確認を推奨します', tab: 'report' });
  if (!hints.length)  hints.push({ msg: '設計タブでテスト技法推奨マトリクスを確認しましょう', tab: 'design' });
  return hints;
}
```

**完了条件**:
- [ ] 概要タブに動的ヒントカードが表示される
- [ ] カードクリックで対応タブに切り替わる

---

## 共通完了条件

- [ ] `python -m pytest tests/ -q` が全 PASS
- [ ] `make verify-ui` が PASS
