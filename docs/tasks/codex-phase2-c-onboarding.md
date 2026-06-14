# タスク: Phase 2-C — 生成ウィザード Step 1 のオンボーディング強化

## ゴール

生成ウィザードの Step 1（URL 入力パネル）に、初めて使うユーザーが迷わないための
3 つの情報を追加する:

1. **所要時間の目安** — 「10画面で約2〜3分」
2. **サンプルURLで試すボタン** — クリックで `https://example.com` をURLフィールドに入力
3. **ログイン必須サイトの案内** — 「ログインが必要な場合は解析後に認証情報を追加できます」

**なぜ必要か**: 初回ユーザーが「何を入力すればいいか」「どのくらいかかるか」「ログイン壁はどうするか」
を把握できず離脱している。

---

## 触るファイル（これ以外は変更しない）

- `templates/partials/view-generate.html` — `wizard-p1` ブロックに追加

**変更禁止**:
- `static/js/wizard.js`（JS ロジックの変更なし）
- `static/app.css` / `static/css/` ファイル（スタイル変更なし）
- 他のウィザードステップ（wizard-p2 / execution-view / result-panel）
- git 操作（commit は Claude が行う）

---

## 既存コードの参照（必ず読んでから実装すること）

`templates/partials/view-generate.html` の `#wizard-p1` ブロックを読む。
現在の構造:

```html
<div id="wizard-p1" class="input-card">
  <label for="url-input" class="form-label">クロール対象 URL <span ...>*</span></label>
  <div class="input-row" ...>
    <input type="url" id="url-input" ...>
    <datalist id="url-history-list"></datalist>
    <input type="hidden" id="crawl-depth" value="5" />
    <input type="hidden" id="max-pages" value="300" />
    <button type="button" id="discover-btn" ...>画面分析</button>
  </div>
  <div id="url-input-message" class="input-field-message"></div>
  <div id="discover-loading" ...>...</div>
  <div id="discover-status" class="discover-status"></div>
  <!-- 解析完了サマリー -->
  <div id="p1-summary" ...>...</div>
</div>
```

---

## 実装の指示

### 挿入位置

`<div id="url-input-message" ...></div>` の**直後**、`<div id="discover-loading" ...>` の直前に
以下のブロックを丸ごと挿入する。

```html
<!-- オンボーディングヒント -->
<div class="wizard-p1-hints" style="margin-top:10px;display:flex;flex-direction:column;gap:8px">
  <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
    <span style="font-size:12px;color:var(--text-muted)">
      ⏱ 目安: 10画面のサイトで約2〜3分
    </span>
    <button type="button" id="sample-url-btn"
      style="font-size:12px;padding:2px 10px;border:1px solid var(--border);border-radius:12px;background:var(--surface);color:var(--primary);cursor:pointer;white-space:nowrap">
      サンプルURL（example.com）で試す
    </button>
  </div>
  <p style="font-size:12px;color:var(--text-muted);margin:0">
    💡 ログインが必要なサイトは「画面分析」後に認証情報を追加できます。
    <br>
    認証済みページもテスト設計対象にしたい場合は「上級設定」からログインURLを指定してください。
  </p>
</div>
```

### サンプルURLボタンのイベントリスナー

`templates/partials/view-generate.html` の末尾（`</section>` の直前）に `<script>` ブロックを追加:

```html
<script>
(function () {
  const btn = document.getElementById('sample-url-btn');
  if (!btn) return;
  btn.addEventListener('click', function () {
    const input = document.getElementById('url-input');
    if (input) {
      input.value = 'https://example.com';
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
  });
}());
</script>
```

> **注意**: `view-generate.html` は `templates/index.html` から include される partial。
> `<script>` ブロックを partial 末尾に書くことは既存の他 partial でも行われているパターン。
> ただし、`static/js/wizard.js` の `validateUrlInput()` が `url-input` の `input` イベントを
> リッスンしているため、`dispatchEvent(new Event('input'))` を使って連携させること。

---

## 完了条件

- [ ] URL 入力フォームの下に「⏱ 目安」テキストと「サンプルURL で試す」ボタンが表示される
- [ ] ボタンをクリックすると `#url-input` に `https://example.com` がセットされる
- [ ] ログイン案内テキストが表示される
- [ ] `discover-loading` / `p1-summary` など既存要素の表示ロジックに影響しない
- [ ] `python -m pytest tests/ -q` が全 PASS する（HTML 変更のみ）
- [ ] 変更が `templates/partials/view-generate.html` のみに収まっている

---

## スコープ外（やらないこと）

- `static/js/wizard.js` の変更
- CSS の追加（`var(--border)` / `var(--surface)` / `var(--primary)` / `var(--text-muted)` は既存変数）
- Step 2 以降のウィザードへの変更
- git 操作
