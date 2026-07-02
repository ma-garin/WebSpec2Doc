# タスク: P3-7 — テストモデリング図の参加者ラベル簡略化

**優先度**: P3（次スプリント）  
**背景**: シーケンス図の `participant` ラベルが「P001 HOTEL PLANISPHERE - テスト自動化練習サイト」のように長く、図が横長になって読みにくい。`_shortVisLabel` 関数が既に存在するが Mermaid の `participant ... as ...` 出力に反映されていない。

## ゴール

Mermaid のシーケンス図・コミュニケーション図で参加者ラベルを短縮表示する。
表示: `P001\nログイン` のように「ID + 改行 + 短縮ページ名」形式にする。

## 触るファイル

- `static/js/view-transition.js` — Mermaid ソース生成部分の participant 行を変更

**変更禁止**:
- `static/app-report.css`
- バックエンドファイル

## 実装の指針

### `_buildSeqDiagram()` の participant 出力変更（`view-transition.js`）

```js
// 変更前
lines.push(`participant ${pageId} as "${fullLabel}"`);

// 変更後（_shortVisLabel を利用）
const shortLabel = _shortVisLabel(page, 20);  // 最大20文字
lines.push(`participant ${pageId} as "${pageId}\\n${shortLabel}"`);
```

### `_shortVisLabel(page, maxLen)` の確認

既存関数を確認し、ページタイトルから `maxLen` 文字に切り詰めた文字列を返すことを確認する。
必要なら `maxLen` パラメータを追加する。

## 完了条件

- [ ] シーケンス図の参加者ラベルが「P001\nログイン」形式で表示される
- [ ] 長いページタイトルが20文字以内に切り詰められる
- [ ] コミュニケーション図にも同じ簡略化が適用される
- [ ] `make verify-ui` が PASS（図が正常にレンダリングされる）

## スコープ外

- ラベル長の設定 UI（20文字固定で十分）
- アクティビティ図・テスト観点マップへの適用（今回はシーケンス・コミュニケーション図のみ）
