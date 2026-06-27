# タスク: Phase 1-0 — ゴールデンパス・ヒーロー着地 + ナビ再構成（初見ユーザー学習容易性）

## ゴール

初見ユーザーが「触って理解できる」初回着地を実現する。ダッシュボード着地を「管理者テーブル」から
**ゴールデンパス・ヒーロー**に変える。ナビは初見者を圧倒しないようグループ分けする。

**なぜ必要か**: 現状、初見ユーザーはほぼ空の監視テーブルに着地し、何のツールでまず何をするか分からない。
主要フロー（生成ウィザード）はナビに無くボタン依存。ナビは専門ツール5種が先頭を占有。
（根拠: `docs/USABILITY_TEST_REPORT.md` M-1/M-2、実機観察 2026-06-26）

確定方針: ユーザーが「ゴールデンパス・ヒーロー着地」案を選択済み。入口は「ガイド付き(おすすめ)/全自動」を
1画面で選べるようにする。ナビは「はじめる/高度な機能」にグループ分けし、高度な機能は段階開示する。

---

## 触るファイル（これ以外は変更しない）

- `templates/partials/view-dashboard.html` — 先頭にヒーローブロックを追加（既存テーブルは下に残す）
- `templates/partials/nav.html` — ナビをグループ分け（既存の data-view ボタンは1つも削除・改名しない）
- `static/js/core.js` — ヒーローのボタン配線を追加（既存関数を再利用）
- `static/app-components.css` — ヒーロー/ナビグループのスタイルを末尾に追記（既存 Carbon トークンのみ使用）

**変更禁止**:
- 既存の `data-view` 属性・要素ID（`#add-site-btn`, `#add-site-btn-2`, `#discover-btn`, `#url-input`, 各 `.app-nav-item[data-view=...]`）の削除・改名
- `static/app.css` の `:root` / `html[data-theme="dark"]`（トークン定義は触らない）
- ダークモードの挙動（必ず既存トークン変数経由で配色する。hex 直書き禁止）
- git 操作（commit は Claude が行う）

---

## 既存コードの参照（必ず読んでから実装すること）

1. `static/js/core.js`:
   - `openAddSite()` … 生成ウィザードをStep1で開く（`switchView('generate')` → `#url-input` クリア → `showWizardStep(1)`）
   - `switchView(name)` … ビュー切替（`'generate'` / `'auto-run'` 等）
   - 既存: `document.getElementById('add-site-btn').addEventListener('click', openAddSite)`
2. `templates/partials/view-dashboard.html`:
   - 現状は `#view-dashboard` 直下に flex ヘッダ（説明文 + 再読み込み + +サイトを追加）と `#history-body`
3. `templates/partials/view-generate.html`:
   - Step1 に `#url-input`（type=url）と `#discover-btn`（画面分析）。ヒーローからはここへ橋渡しする
4. `templates/partials/view-auto-run.html`:
   - AutoRun の URL 入力は `#autorun-url`

---

## 実装の指示

### 1. ヒーローブロック（view-dashboard.html）

`<section class="view is-active" id="view-dashboard">` の**直後**（既存の flex ヘッダ `div` の前）に挿入する。
構造（クラス名は厳守。スタイルは §4 で定義）:

```html
<div class="dash-hero">
  <div class="dash-hero-main">
    <h1 class="dash-hero-title">URL から QA テスト文書を自動生成</h1>
    <p class="dash-hero-sub">稼働中の Web システムの URL を貼るだけ。画面解析 → 仕様書 → テスト設計までを自動で作ります。</p>
    <div class="dash-hero-form">
      <input type="url" id="hero-url" class="url-input dash-hero-input" placeholder="https://example.com   解析したい URL を貼り付け" autocomplete="url" />
      <button type="button" id="hero-start-btn" class="btn-primary dash-hero-start">始める</button>
    </div>
    <div class="dash-hero-steps">
      <span class="dash-hero-step"><b>①</b> 画面を解析</span>
      <span class="dash-hero-arrow">→</span>
      <span class="dash-hero-step"><b>②</b> 画面仕様書</span>
      <span class="dash-hero-arrow">→</span>
      <span class="dash-hero-step"><b>③</b> テスト設計</span>
      <span class="dash-hero-note">目安: 10画面で約2〜3分</span>
      <button type="button" id="hero-sample-btn" class="dash-hero-sample">サンプル(example.com)で試す</button>
    </div>
    <div class="dash-hero-modes">
      <button type="button" id="hero-guided-btn" class="dash-mode-card">
        <span class="dash-mode-icon">✍</span>
        <span class="dash-mode-body"><b>ガイド付き</b><small>1画面ずつ確認しながら作る・おすすめ</small></span>
      </button>
      <button type="button" id="hero-auto-btn" class="dash-mode-card">
        <span class="dash-mode-icon">⚡</span>
        <span class="dash-mode-body"><b>全自動 (AutoRun)</b><small>URL だけでテスト実行まで一括・最速</small></span>
      </button>
    </div>
  </div>
</div>
```

既存の flex ヘッダ内の説明文は「最近のサイト」セクションの位置づけにするため、
既存 `<p>` の文言を `監視対象サイト。再クロールで仕様ドリフトを検知できます。` のまま残し、
その `<p>` の直前に小見出し `<h2 class="dash-section-title">最近のサイト</h2>` を追加する（既存ボタンはそのまま）。

### 2. ヒーロー配線（static/js/core.js）

`openAddSite` 定義と `add-site-btn` のリスナー登録の**後**に、以下を追加する。既存関数を再利用し、推測でロジックを足さない。

```js
// ---- ダッシュボード・ヒーロー（ゴールデンパス入口） ----
function _heroStartGuided(prefillUrl) {
  openAddSite();
  const input = document.getElementById('url-input');
  if (input && prefillUrl) {
    input.value = prefillUrl;
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }
}
document.getElementById('hero-start-btn')?.addEventListener('click', () => {
  const v = (document.getElementById('hero-url')?.value || '').trim();
  _heroStartGuided(v);
  // URL があれば画面分析まで自動で進める（既存 discover フローを再利用）
  if (v) document.getElementById('discover-btn')?.click();
});
document.getElementById('hero-guided-btn')?.addEventListener('click', () => {
  _heroStartGuided((document.getElementById('hero-url')?.value || '').trim());
});
document.getElementById('hero-auto-btn')?.addEventListener('click', () => {
  const v = (document.getElementById('hero-url')?.value || '').trim();
  switchView('auto-run');
  const a = document.getElementById('autorun-url');
  if (a && v) { a.value = v; a.dispatchEvent(new Event('input', { bubbles: true })); }
});
document.getElementById('hero-sample-btn')?.addEventListener('click', () => {
  const input = document.getElementById('hero-url');
  if (input) { input.value = 'https://example.com'; input.dispatchEvent(new Event('input', { bubbles: true })); }
});
```

`#hero-url` で Enter を押したら `#hero-start-btn` と同じ動作にする keydown リスナーも追加する。

### 3. ナビ再構成（nav.html）

既存の `.app-nav-item` ボタン（data-view と svg と label）は**そのまま流用**し、グループの見出しと
ラッパだけ追加する。順序:

- グループ「はじめる」: `dashboard`
- グループ「高度な機能」(`<details class="nav-group" >` で折りたたみ可能・既定は open):
  `qa-process`, `qa-models`, `qa-automation`, `qa-quality`, `auto-run`
- グループ「ヘルプ」: `user-guide`, `settings`

既存の `<div class="app-nav-group">メニュー</div>` は削除し、上記グループ見出しに置換する。
`<details>` の `<summary class="app-nav-group nav-group-summary">高度な機能</summary>` とし、中に該当ボタンを入れる。
**data-view 値・ボタンのclass・svg・label文言は一切変更しない**（E2E とハンドラ互換のため）。

### 4. スタイル（static/app-components.css 末尾に追記）

`/* ===== ゴールデンパス・ヒーロー (Phase 1-0) ===== */` コメントを付けて追記。配色は既存トークン変数のみ:
`var(--surface) / --surface-soft / --border / --primary / --primary-dark / --text / --text-muted / --shadow-sm / --radius-lg` 等。

- `.dash-hero`: `background: var(--surface); border:1px solid var(--border); border-radius: var(--radius-lg); padding: 24px; margin-bottom: 18px; box-shadow: var(--shadow-sm);`
- `.dash-hero-title`: 22px / 700 / `var(--text)`
- `.dash-hero-sub`: 13px / `var(--text-muted)` / margin 6px 0 14px
- `.dash-hero-form`: flex / gap 8px / max-width 640px。`.dash-hero-input` は flex:1 height 44px。`.dash-hero-start` は height 44px padding 0 24px
- `.dash-hero-steps`: flex / wrap / gap 8px / align-center / margin-top 12px / font 12px / `var(--text-muted)`。`.dash-hero-step b` は `var(--primary)`
- `.dash-hero-sample`: ピル型ボタン（`border:1px solid var(--border); border-radius: var(--radius-lg); background: var(--surface); color: var(--primary); font-size:12px; padding:4px 12px; min-height: 32px`）
- `.dash-hero-modes`: flex / gap 12px / margin-top 16px / wrap
- `.dash-mode-card`: flex / align-center / gap 10px / padding 12px 16px / `border:1px solid var(--border)` / `border-radius: var(--radius-lg)` / `background: var(--surface-soft)` / cursor pointer / min-height 44px / text-align left。hover で `border-color: var(--primary)`
- `.dash-mode-body b` 13px/700、`.dash-mode-body small` 11px/`var(--text-muted)`（block 表示）
- `.dash-section-title`: 14px / 700 / margin 4px 0 8px
- `.nav-group-summary`: 既存 `.app-nav-group` を踏襲した見出し。`details.nav-group` の三角は CSS で控えめに。
- レスポンシブ: `@media (max-width: 640px)` で `.dash-hero-form` と `.dash-hero-modes` を縦積み、`.dash-mode-card` を全幅。
- 最小フォント 11px 以上、タッチターゲット 44px 以上、コントラスト AA を守る。

---

## 完了条件

- [ ] ダッシュボード着地の最上部にヒーロー（タイトル/URL入力/始める/3ステップ/サンプル/2モードカード）が表示される
- [ ] `#hero-start-btn`: URL入力ありで生成ウィザードに遷移し `#url-input` に値が入り画面分析が走る。空なら生成ウィザードStep1を開くだけ
- [ ] `#hero-auto-btn`: AutoRun ビューへ遷移し、URLがあれば `#autorun-url` に転記される
- [ ] `#hero-sample-btn`: `#hero-url` に `https://example.com` が入る
- [ ] ナビが「はじめる/高度な機能(折りたたみ)/ヘルプ」にグループ化され、既存 data-view ボタンは全て機能する
- [ ] ライト/ダーク両モードで配色が破綻しない（hex 直書きが無い）
- [ ] `bash scripts/verify.sh` が ALL GREEN（既存 pytest 全 PASS）
- [ ] 変更が上記「触るファイル」4つに収まっている

---

## スコープ外（やらないこと）

- AutoRun 画面内部・実行結果画面の再設計（Phase 1-1 で別途）
- トークン（`:root`）の変更、MD3 への色置換
- 既存 E2E テストの書き換え（壊れる場合は報告）
- 用語ツールチップ辞書の大改修（今回はヒーロー文言を平易化するのみ）
- git 操作（commit は Claude）
