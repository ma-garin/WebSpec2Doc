# タスク: Phase 2-D — 用語・Trace ID ツールチップを全画面に拡張

## ゴール

ダッシュボードに既存の `.term` ツールチップパターンを、QA ビュー・レポートビューの
Trace ID 列ヘッダー・用語ラベルに拡張する。

- `SCR`（画面）/ `FLD`（入力項目）/ `TRN`（画面遷移）/ `BTN`（操作要素）/ `COND`（テスト条件）
- 「Trace」「仕様ドリフト」「カバレッジ」「クロール」などの QA 専門用語

**なぜ必要か**: 第三者検証会社の新人・ステークホルダーが Trace ID の意味を知らないまま
レポートを受け取ると混乱する。ホバーで即座に意味が分かることで、説明コストが下がる。

---

## 触るファイル（これ以外は変更しない）

- `static/js/view-utils.js` — ユーティリティ関数 `wrapTraceTerms(html)` を追加
- `static/js/qa-tools.js` — レンダリング後に `wrapTraceTerms()` を適用
- `templates/partials/view-qa-automation.html` — 「Trace」列ヘッダーを `.term` でラップ
- `templates/partials/view-qa-quality.html` — 同上
- `templates/partials/view-qa-models.html` — 「Trace率」ラベルを `.term` でラップ

**変更禁止**:
- `static/app-report.css` / 他の CSS（`.term` スタイルは定義済みのためそのまま使う）
- `web/routes/*.py`
- git 操作（commit は Claude が行う）

---

## 既存コードの参照（必ず読んでから実装すること）

### `.term` CSS（`static/app-report.css` 211〜212行目）

```css
.term { border-bottom: 1px dotted var(--primary); cursor: help; position: relative; }
.term:hover::after {
  content: attr(data-term);
  position: absolute; bottom: calc(100% + 6px); left: 0;
  background: #1a1a2e; color: #fff; font-size: 12px;
  border-radius: 5px; padding: 8px 12px;
  white-space: normal; width: 280px; max-width: 80vw; line-height: 1.6;
  z-index: 600; box-shadow: 0 4px 12px rgba(0,0,0,.25);
}
```

### 既存の使用例（`templates/partials/view-dashboard.html` 4行目）

```html
<strong class="term" data-term="再クロール: 同じサイトをもう一度読み取って最新の画面構成を取得すること">再クロール</strong>
<span class="term" data-term="仕様ドリフト: 前回取得時から画面・入力項目・遷移が変わってしまっていること。テスト資産の陳腐化を意味します">仕様ドリフト</span>
```

パターン: `<span class="term" data-term="用語: 説明文">用語</span>` を使う。

### `static/js/view-utils.js`

このファイルに既存のユーティリティ関数がある。末尾に追加すること。

### `static/js/qa-tools.js`

`setQaToolStatus`, `renderQaModelTool`, `renderQaAutomationTool`, `renderQaQualityTool` が定義されている。
各 `render*` 関数が `document.getElementById(cfg.content).innerHTML = ...` で HTML を書き込んでいる。
その直後に `wrapTraceTerms()` を呼ぶ。

---

## 実装の指示

### 1. `static/js/view-utils.js` — `wrapTraceTerms(containerEl)` を追加

```js
// Trace ID プレフィックスと QA 用語にホバーツールチップを付与する。
// containerEl: DOM 要素。その innerHTML のうち、対象用語を .term span でラップする。
// 注意: innerHTML を直接操作するため XSS リスクなし（escHtml 済みの静的 HTML のみが対象）。
const TRACE_TERM_MAP = {
  'SCR': '画面（Screen）: クロールで検出した個々のページ。SCR-001 のように番号で識別します。',
  'FLD': '入力項目（Field）: フォーム内の個々の入力欄・選択肢。FLD-001 のように番号で識別します。',
  'TRN': '画面遷移（Transition）: リンクやボタン操作で画面が切り替わる経路。TRN-001 で識別します。',
  'BTN': '操作要素（Button）: ボタン・リンクなどのクリック可能な要素。BTN-001 で識別します。',
  'COND': 'テスト条件（Condition）: 境界値・同値分割などから機械導出したテスト観点。',
};

function wrapTraceTerms(containerEl) {
  if (!containerEl) return;
  // テーブルのヘッダー「Trace」列ラベルをラップ
  containerEl.querySelectorAll('th').forEach(th => {
    if (th.textContent.trim() === 'Trace' && !th.querySelector('.term')) {
      th.innerHTML = `<span class="term" data-term="Trace ID: 画面(SCR)・項目(FLD)・遷移(TRN)・操作(BTN)・条件(COND)の識別子。テストケースと仕様の紐付けに使います。">Trace</span>`;
    }
  });
  // テーブルのデータセルに含まれる Trace ID プレフィックス（例: "SCR-001"）をラップ
  containerEl.querySelectorAll('td').forEach(td => {
    const text = td.textContent.trim();
    const m = text.match(/^(SCR|FLD|TRN|BTN|COND)-\d+$/);
    if (m && !td.querySelector('.term')) {
      const prefix = m[1];
      const def = TRACE_TERM_MAP[prefix] || prefix;
      td.innerHTML = `<span class="term" data-term="${escHtml(def)}">${escHtml(text)}</span>`;
    }
  });
}
```

> `escHtml` は既存のグローバル関数（`core.js` で定義済み）を使うこと。

### 2. `static/js/qa-tools.js` — `renderQa*Tool` 関数の直後に呼び出す

各 `renderQaModelTool` / `renderQaAutomationTool` / `renderQaQualityTool` の末尾で、
コンテンツ要素への innerHTML 書き込みの直後に追記:

```js
// 書き込み後の DOM 要素を取得してツールチップを付与
const contentEl = document.getElementById(QA_TOOL_CONFIG[viewName].content);
if (typeof wrapTraceTerms === 'function') wrapTraceTerms(contentEl);
```

`renderQa*Tool` 関数がどのように `cfg.content` に書き込んでいるかを確認してから追加位置を決めること。

### 3. `templates/partials/view-qa-automation.html` の列ヘッダー

「Trace」テキストが直接 `<th>` に書かれている箇所（JS で動的生成される場合は手順2で対応済みのためスキップ可）。
静的 HTML に `<th>Trace</th>` があれば `.term` でラップする:

```html
<th><span class="term" data-term="Trace ID: SCR(画面)・FLD(項目)・TRN(遷移)・BTN(操作)・COND(条件)の識別子">Trace</span></th>
```

### 4. `templates/partials/view-qa-quality.html` / `view-qa-models.html` も同様

「Trace率」ラベルがある場合:

```html
<span class="term" data-term="Trace率: テスト条件にTrace IDが紐付いている割合。高いほどトレーサビリティが確保されています。">Trace率</span>
```

---

## 用語定義一覧（`data-term` に使う説明文）

| 用語 | 定義 |
|------|------|
| SCR | 画面（Screen）: クロールで検出した個々のページ。SCR-001 のように番号で識別します。 |
| FLD | 入力項目（Field）: フォーム内の個々の入力欄・選択肢。FLD-001 のように番号で識別します。 |
| TRN | 画面遷移（Transition）: リンクやボタン操作で画面が切り替わる経路。TRN-001 で識別します。 |
| BTN | 操作要素（Button）: ボタン・リンクなどのクリック可能な要素。BTN-001 で識別します。 |
| COND | テスト条件（Condition）: 境界値・同値分割などから機械導出したテスト観点。 |
| Trace | Trace ID: 画面・項目・遷移・操作・条件の識別子。テストケースと仕様の紐付けに使います。 |
| クロール | Webサイトを自動巡回してページ構成・フォーム・リンクを収集すること。 |
| 仕様ドリフト | 前回取得時から画面・入力項目・遷移が変わってしまっていること。テスト資産の陳腐化を意味します。 |
| カバレッジ | テスト条件のうち、テストケースで検証済みのものの割合。 |

---

## 完了条件

- [ ] QA ツールビューの「Trace」列ヘッダーにホバーツールチップが表示される
- [ ] テーブルセルの `SCR-001` / `FLD-001` 等にホバーツールチップが表示される
- [ ] `wrapTraceTerms()` が `view-utils.js` に追加されている
- [ ] `python -m pytest tests/ -q` が全 PASS する
- [ ] 変更が上記「触るファイル」の範囲に収まっている

---

## スコープ外（やらないこと）

- CSS の変更（`.term` スタイルは `app-report.css` に定義済みのため追加不要）
- `report.html` 出力（`src/generator/html_reporter.py`）の変更
- `view-dashboard.html` の既存 `.term` 要素の変更（触らない）
- git 操作
- 全テキストノードへの再帰的置換（セル単位の exact match のみ実装すること）
