# タスク: Phase 3-B — 決定的 / AI補完バッジを表示する

## ゴール

QA ビューのテスト観点・異常系シナリオの各行に、生成元を示すバッジを表示する。

- `⚙️ 決定的` — ルールベースで機械導出（`source: "rules"`）
- `✨ AI補完` — OpenAI で生成（`source: "openai"`）

**なぜ必要か**: ステークホルダーから「このテスト観点はどう作られたのか」という信頼性の
問いに答えるため。過剰宣伝を排し、どこが機械、どこがAIかを明示する。

## 前提

`codex-phase3-c-llm-provider.md` が完了して `source` フィールドが各観点に付いていること。

---

## 触るファイル（これ以外は変更しない）

- `static/js/qa-tools.js` — QA ビューのレンダリングにバッジ表示を追加
- `static/js/qa-process.js` — QA プロセスビューのテストケース行にバッジ追加

**変更禁止**:
- `web/routes/*.py`（バッジは UI のみの変更）
- `src/llm/*.py`（Phase 3-C で対応済みのはず）
- CSS ファイル（既存の `.badge-ok` / `.badge-info` 等を流用する）
- git 操作（commit は Claude が行う）

---

## 既存コードの参照（必ず読んでから実装すること）

### `static/js/qa-tools.js`

- `renderQaQualityTool(data)` — 品質観点テーブルを描画
- `renderQaAutomationTool(data)` — 自動テスト候補を描画
- テーブルの `<td>` 生成部分を読む

### `static/js/qa-process.js`

- テストケース行（`case_id`, `title`, `trace_id` 等）のレンダリング部分を読む

### バッジ CSS（既存クラスを使う）

ダッシュボードや設定ビューで使われている既存スタイル:
```html
<!-- 既存の例 -->
<span class="badge-ok" style="display:inline-block;padding:2px 8px;border-radius:12px;...">AI機能：有効</span>
```

`badge-ok`（緑系）を `✨ AI補完`、カスタムスタイルを `⚙️ 決定的` に使う。

---

## 実装の指示

### 1. バッジ生成ヘルパー関数

`static/js/qa-tools.js` か `static/js/view-utils.js` の末尾に追加:

```js
function sourceBadge(source) {
  if (source === 'openai') {
    return '<span style="display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:700;background:var(--info-bg,#e8f4fd);color:var(--primary-dark,#1a56db);white-space:nowrap">✨ AI補完</span>';
  }
  return '<span style="display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;font-weight:700;background:var(--surface,#f4f5f7);color:var(--text-muted,#666);white-space:nowrap">⚙️ 決定的</span>';
}
```

### 2. `renderQaQualityTool` 内のテーブル行にバッジ列を追加

品質観点テーブルの構造を確認し、`観点` 列の末尾か、独立した列にバッジを追加する。

```js
// 例: 観点テキストの後ろにバッジを inline で追加
`<td>${escHtml(item.viewpoint || item.name || '')} ${sourceBadge(item.source)}</td>`
```

`source` フィールドがない古いデータ（`source` キー未定義）は `'rules'` として扱う:
```js
const source = item.source || 'rules';
```

### 3. `renderQaAutomationTool` 内の候補行にバッジを追加

自動テスト候補の各行（`status` 列か `title` 列の近く）に `sourceBadge(item.source || 'rules')` を追加。

### 4. `qa-process.js` のテストケース行にバッジを追加

QA プロセスのテストケース `cases` 配列の各行に同様にバッジを追加。

---

## 完了条件

- [ ] QA ビューの観点・候補・ケース行に `⚙️ 決定的` または `✨ AI補完` バッジが表示される
- [ ] `source` フィールドのない旧データは `⚙️ 決定的` にフォールバックする
- [ ] `python -m pytest tests/ -q` が全 PASS する
- [ ] バッジが他のテキストや表示を崩さない（既存テーブルレイアウト維持）

---

## スコープ外（やらないこと）

- CSS ファイルへのクラス追加（インラインスタイルで十分）
- サーバー側の変更（`source` フィールドは Phase 3-C で追加済みのはず）
- ダッシュボードや概要タブへのバッジ追加（QA ビューのみ）
- git 操作
