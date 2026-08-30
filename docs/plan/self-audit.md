# WebSpec2Doc 自己検証（WCAG 2.2 / ISO 25010 / ASVS）

対象は WebSpec2Doc **自身のワークスペース UI**。顧客サイトを検査するために同梱している
`src/ux/assets/axe.min.js`（axe-core, MPL-2.0）を、同じ手順で自社 UI に向けた結果である。

- 実施日: 2026-08-31 / 対象: `http://127.0.0.1:8765`（`WEBSPEC2DOC_AUTH_MODE=off`）
- 測定環境: Chromium headless 1440×900・`wait_until="domcontentloaded"`・ページ読み込み後 1.8 秒待機
- axe 実行条件: `runOnly: {type:'tag', values:['wcag2a','wcag2aa','wcag22aa']}`
- 生データ: scratchpad の `p_root.json` / `p_spec.json` / `p_tests.json` / `p_sched.json` / `p_report.json`

---

## A. axe-core による機械判定（ページ別）

同梱バンドルの読み込みは **成功**（`page.add_script_tag(path=src/ux/assets/axe.min.js)`）。
5 ページで実測、`/team` は未測定（理由は「測れなかったこと」）。

| ページ | critical | serious | moderate | minor | 違反ルール数 | 違反ノード総数 |
|---|---|---|---|---|---|---|
| `/` | 0 | 2 | 0 | 0 | 2 | 70 |
| `/sites/demomart/spec` | 1 | 1 | 0 | 0 | 2 | 26 |
| `/sites/demomart/tests` | 0 | 1 | 0 | 0 | 1 | 40 |
| `/sites/demomart/schedule` | 0 | 1 | 0 | 0 | 1 | 36 |
| `/sites/demomart/report` | 0 | 1 | 0 | 0 | 1 | 17 |
| `/team` | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 | 未測定 |
| **計（5 ページ）** | **1** | **6** | 0 | 0 | 7 | **189** |

※ impact は「違反ルール」単位の件数。ノード総数は各ルールの `nodes` 長の合計。

### 違反ルールの内訳

**1. `color-contrast`（serious）— 5 ページすべてで検出・164 ノード**

- 失敗セレクタ（代表）: `button[data-view="spec"] > .lb`、`button[data-view="test"] > .lb`、`button[data-view="drift"] > .lb`
- axe の報告値: `contrast 2.57 / foreground #98a2b3 / background #ffffff / font-size 7.5pt (10px) / weight normal`
- ノード数: `/` 46、`/tests` 40、`/schedule` 36、`/spec` 25、`/report` 17
- 該当: **1.4.3 Contrast (Minimum) — AA 不適合**（10px は「大きい文字」に該当しないため 4.5:1 が必要）

**2. `nested-interactive`（serious）— `/` のみ・24 ノード**

- 失敗セレクタ: `div[data-domain="demomart"]`、`div[data-domain="127.0.0.1:8766"]`、`.it[role="option"]:nth-child(4)`
- 失敗内容: `Element has focusable descendants`
- 構造: `role="option" tabindex="0"` の行 `<div class="it">` の内部に `<button class="del">✕</button>` が入っている
- 該当: **4.1.2 Name, Role, Value — A 不適合**（listbox の option は子に対話要素を持てない。支援技術が ✕ を到達不能または誤った role で提示する）

**3. `aria-required-children`（critical）— `/spec` のみ・1 ノード**

- 失敗セレクタ: `#screen-items`
- 失敗内容: `Element has children which are not allowed: [role=button]`
- 構造: `<div class="items" id="screen-items" role="listbox" aria-label="画面一覧">` の直下に `role=button` の子が描画される
- 該当: **1.3.1 Info and Relationships — A 不適合**

---

## B. 機械判定できない項目（手動確認）

| 項目 | 対応 SC | 結果 | 根拠 |
|---|---|---|---|
| `lang` 属性 | 3.1.1 (A) | **適合** | 全 5 ページで `<html lang="ja">` |
| ランドマーク | 1.3.1 (A) | 適合 | 全ページ `NAV` / `MAIN` / `HEADER` / `NAV` を検出 |
| キーボード到達性 | 2.1.1 (A) | **重大な問題なし（一部未計測）** | 下記参照 |
| フォーカス可視 | 2.4.7 (AA) | **一部要確認** | 下記参照 |
| ターゲットサイズ | 2.5.8 (AA) | **不適合 2 件** | 下記参照 |
| 一貫したヘルプ | 3.2.6 (A) | **適合** | 下記参照 |
| 重複入力 | 3.3.7 (A) | 違反を観測せず | 下記参照 |
| 見出し順序 | 1.3.1 / 2.4.6 | **不適合** | 下記参照 |
| フォームのラベル | 1.3.1 / 3.3.2 | **1 件要改善** | 下記参照 |
| 小さい灰色文字の色比 | 1.4.3 (AA) | **不適合** | 下記参照 |

### B-1. キーボード到達性（2.1.1 Keyboard, A）

Tab を最大 45 回押して `document.activeElement` を記録した。

- **クリック可能だがフォーカス不能な要素は 5 ページとも 0 件**（`[onclick]` / `[role=button]` / `.list-row` などを走査）。
  `div` にハンドラだけ載せる典型的な失敗はしていない。行 `<div class="it">` には `tabindex` が付与されている（`static/js/ta2/list.js:108`、`static/js/ta2/ws-home.js:86`）。
- ただし B-1 は **フォーカス到達の有無** のみを検証した。listbox 内の矢印キー操作（APG のロービングタブインデックス）が正しいかは未検証。
- 計測の限界: `/` は Tab 45 回の上限に達し（可視フォーカス可能要素 69）巡回を完走していない。`/tests` は
  ページ読み込み時のフォーカス位置が先頭になかったため、タブ順の**後半のみ**を記録した（28 停止）。
  よって「到達できない要素はない」と断定はできない。`/spec`・`/schedule`・`/report` は巡回を完走した。

### B-2. フォーカスの可視性（2.4.7 Focus Visible, AA）

- 全ページで大域規則 `:focus-visible { outline: 2px solid var(--ac); outline-offset: 2px; }` が有効。
  レール（`.rail button:focus-visible`）、リスト行（`.it:focus-visible` ほか）にも個別指定があり、**基本設計は適合**。
- 破壊操作の ✕ は既定 `opacity:0` だが `.it .del:focus-visible{opacity:1}`（`static/css/ws.css:33`）と
  `.st:focus-within .x, .st .x:focus-visible{opacity:1}`（`static/css/ta2.css:260`）でキーボード時に可視化される。適切。
- **要確認 2 件**: `/schedule` の `#sched-window-start` / `#sched-window-end`（`input[type=time]`）にフォーカスした時点の
  計算値が `outline-style:none` かつ `box-shadow:none` だった。
  一方 `static/css/ws.css:103` が `.fld input{outline:none}`、`:104` が `.fld input:focus{box-shadow:0 0 0 3px var(--ac-bg)}` を与えており、
  **計測値とスタイルシートが矛盾する**。修正着手の前に再現確認が必要（断定しない）。
- `/report` の `#report-preview`（iframe）はフォーカスを受けるが指標がない。影響は小。

### B-3. ターゲットサイズ（2.5.8 Target Size (Minimum), AA）

| 要素 | 実測 | 判定 | 根拠 |
|---|---|---|---|
| レールのボタン | 72×43 px | **適合** | 24×24 を満たす |
| サイト一覧の行 `.it` | 279×66 px | 適合 | |
| 画面一覧の行 `.it` | 279×51 px | 適合 | |
| テスト手順の行 `.st` | 359×61 px | 適合 | |
| **`.it .del`（✕ 削除）** | **22×22 px** | **不適合** | `static/css/ws.css:31`。行自体もターゲットのため「間隔」の例外は成立しない |
| **`.st .x`（✕ 削除）** | **22×22 px** | **不適合** | `static/css/ta2.css:101`。同上 |
| `#go-fail`（失敗 2 件から直す） | 108×22.5 px | **要確認** | 高さ 22.5 px。インライン例外に該当するか未判定 |
| パンくず `a.ws-brand` ほか | 83×17.3 px | 例外に該当の見込み | インラインのテキストリンク（Inline 例外） |
| `/report` のチェックボックス | 14×14 px | **要確認** | `<label>` が入力を包むため実効ターゲットが拡大する可能性。ラベル矩形は未計測 |

### B-4. 一貫したヘルプ（3.2.6 Consistent Help, A）

計測した 5 ページすべてで `#help-btn`（「? 使い方」）がレール内の同一位置に 1 個だけ存在し、
タブ順でも常に `#user-btn` の直後（各ページ 11 番目）に現れた。**適合**。

### B-5. 重複入力（3.3.7 Redundant Entry, A）

- `/schedule` のフォーム（`#sched-form`）は 9 コントロール、`/team` は 5 コントロール。
  同一プロセス内で同じ情報を再入力させる箇所は**観測されなかった**。
- ただし `#sched-endpoint` は「保存済みの値は伏せて表示されます。変更するときだけ入力してください。」と明記しており、
  変更時のみ再入力を求める設計。単一ステップのため 3.3.7 の対象外と判断する。
- 複数ステップのプロセス（ウィザード等）は今回の 6 画面に含まれないため未検証。

### B-6. 見出し順序（1.3.1 Info and Relationships / 2.4.6 Headings and Labels）

axe の `heading-order` は best-practice タグのため、今回の `wcag2a/aa/22aa` 実行では検出されない。手動で確認した。

| ページ | 実際の見出し列 | 問題 |
|---|---|---|
| `/` | h2「サイト」→ **h1「ホーム」** | h1 より前に h2。文書順が逆 |
| `/spec` | h2「demomart」→ h1「分析・設計」→ **h1「DemoMart - お支払い・決済」** | h1 が 2 個 |
| `/tests` | h2「demomart 125 tests」→ h1「自動化」→ **h1「デモストア トップ画面が…」** | h1 が 2 個 |
| `/schedule` | h2 → **h4「demomart」** → h1 → h1 → h3 | h2→h4 のレベル飛ばし、h1 が 2 個 |
| `/report` | h2 → **h4「demomart」** → h1 → h1 → h3 | 同上 |

3 ペイン構成（レール／リスト／詳細）を各ペインで独立に見出し付けした結果と見られる。

### B-7. フォームのラベル（1.3.1 / 3.3.2 Labels or Instructions）

- `/schedule`（9 件）・`/team`（静的確認・5 件）のコントロールは**すべて** `<label for>` または `aria-label` を持つ。
  `#sched-window-start` / `#sched-window-end` も `aria-label="開始時刻" / "終了時刻"`（`templates/workspace.html:238`）で補われている。良好。
- **`/tests` の `#q` のみ**、`<div class="search"><input id="q" placeholder="検索 / 絞り込み">`（`templates/workspace.html:70`）で
  可視ラベルも `aria-label` もない。placeholder がアクセシブル名の最終手段として計算されるため axe は違反として報告しないが、
  **入力を始めると名前が消える**。3.3.2 の観点で要改善。

### B-8. 小さい灰色文字のコントラスト比（1.4.3 Contrast (Minimum), AA）

`--tx3:#98A2B3`（`static/css/ta2.css:3`）を実測計算した（WCAG 相対輝度式）。

| 前景 | 背景 | 比 | 通常文字 4.5:1 | 大きい文字 3:1 |
|---|---|---|---|---|
| **#98A2B3** | **#FFFFFF** | **2.58** | **不適合** | **不適合** |
| **#98A2B3** | **#F6F7F9** | **2.40** | **不適合** | **不適合** |
| #667085（`--tx2` 相当の中間色） | #FFFFFF | 4.97 | 適合 | 適合 |
| #475467（`--tx2`） | #FFFFFF | 7.69 | 適合 | 適合 |

`--tx3` は 3:1 にも届かないため、**文字サイズを問わず不適合**。適用箇所はレールのラベル（10px, `static/css/ws.css:214`）、
リストのサブテキスト（`ws.css:22`）、`.it .grow small`（10.5px, `ws.css:30`）、`#team-meta` / `#sched-meta`（11.5px, インライン指定）など広範。

---

## C. ISO/IEC 25010 自己評価

外形から観測できる特性のみ、1 行ずつ。25010:2023 では Usability→Interaction Capability、Portability→Flexibility に改称されているが、依頼の呼称に従う。

| 特性 | この製品の自社 UI に存在する証拠 | 欠けているもの |
|---|---|---|
| Functional Suitability | `quality/feature_contracts.yml` と `scripts/quality_harness.py` で機能契約を定義し、6 画面すべてが 200 応答で描画された | 自社 UI のアクセシビリティを対象にした契約項目がなく、機能の「正しさ」の定義にa11yが入っていない |
| Performance Efficiency | サーバ応答は `/` 1.2ms・`/team` 12.0ms（curl 実測）と十分速い | クライアント側の予算・計測がない。`/` は可視フォーカス可能要素 69 個と DOM が重く、`/team` はヘッドレスで完了しなかった |
| Usability | 全ページ同一位置の「? 使い方」（3.2.6 適合）、日本語の平易なラベル、`.hint` による補足文が全フォームに付く | 自社 UI に 164 ノードのコントラスト違反。顧客サイトに対して同じ検査を売っている以上、最も直接的な欠落 |
| Reliability | 5/6 ページで axe 実行が再現的に完了し、同一の違反集合を返した | `/team` はヘッドレス Chromium で 3 回連続して完了しなかった（原因未特定・下記参照）。フロント側の異常系の証拠がない |
| Security | CSP・X-Content-Type-Options・X-Frame-Options・Referrer-Policy を全応答に付与（D 章）。ローカル専用設計 | HSTS・Permissions-Policy 不在。`script-src 'unsafe-inline'` により CSP の XSS 抑止力が実質無効 |
| Maintainability | 色が `static/css/ta2.css:3` の CSS 変数 1 行に集約されており、`--tx3` の変更だけで 164 ノードの違反に到達できる | `outline:none` が `ws.css` / `components.css` / `testcase-grid.css` / `account-view.css` に分散し、大域 `:focus-visible` を各所で打ち消す構造 |
| Portability | venv + Flask で追加ランタイム不要。axe-core を同梱し CDN 非依存（`src/ux/axe_runner.py` 冒頭に明記）でオフライン完結 | ローカル専用が設計上の制約（Docker 不採用）。他ホストへの移設手順の証拠は未確認 |
| Compatibility | 同梱 axe-core が顧客サイト検査と自社 UI 検査で同一に動作した（相互運用の実証） | 検証は Chromium 1440×900 のみ。他ブラウザ・他解像度は未測定 |
| Safety | 破壊操作（✕ 削除）は既定 `opacity:0` で誤操作面積が小さく、`:focus-visible` でキーボード時のみ可視化される | 22×22px は 2.5.8 不適合であり「安全のための小ささ」が到達性を犠牲にしている。削除前の確認ダイアログの有無は未検証 |

---

## D. セキュリティヘッダ

`curl -D -` による実測（2 エンドポイント）。**両者で完全に同一**。

| ヘッダ | `/` | `/sites/demomart/spec` | 値 |
|---|---|---|---|
| Content-Security-Policy | **あり** | **あり** | `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; frame-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'` |
| Strict-Transport-Security | **なし** | **なし** | — |
| X-Content-Type-Options | **あり** | **あり** | `nosniff` |
| X-Frame-Options | **あり** | **あり** | `SAMEORIGIN` |
| Referrer-Policy | **あり** | **あり** | `same-origin` |
| Permissions-Policy | **なし** | **なし** | — |

**ローカル専用設計を踏まえた判定**:

- **HSTS 不在は妥当**。`http://127.0.0.1:8765` は HTTPS で提供されず、localhost に HSTS を打つ意味がない。指摘としない。
- **Permissions-Policy 不在は軽微**。カメラ・マイク・位置情報を使わない UI であり、実害は小さい。ただし `frame-src 'self'` を
  設定している以上、`Permissions-Policy: camera=(), microphone=(), geolocation=()` を足す費用は 1 行で、防御の一貫性は上がる。
- **実質的な指摘は `script-src 'unsafe-inline'` の 1 点**。`templates/workspace.html` がインラインスクリプトと
  インラインスタイル（`style="font-size:11.5px;color:var(--tx3)"` 等）に依存しているため付与されていると見られる。
  これがある限り CSP は反射型 XSS をほぼ止められない。ローカル専用でもレポート HTML に外部サイトの文字列を
  取り込む製品である以上（`/report` は iframe でプレビューを描画）、nonce 方式への移行は検討に値する。
- 認証は今回 `WEBSPEC2DOC_AUTH_MODE=off` で無効化して測定しており、**認証・認可・レート制限は未検証**。

---

## 重大度順の指摘（症状 / 該当基準 / 証拠 / 推定原因 file:line）

### 1. [Critical] 画面一覧の listbox が許されない子要素を持つ

- **症状**: `#screen-items` が `role="listbox"` でありながら `role=button` の子を含む。スクリーンリーダーが一覧の項目数・現在位置を正しく提示できない。
- **該当基準**: WCAG 2.2 **1.3.1 Info and Relationships (A)** / axe `aria-required-children` (critical)
- **証拠**: `/sites/demomart/spec`・失敗セレクタ `#screen-items`・`Element has children which are not allowed: [role=button]`
- **推定原因**: `templates/workspace.html:65` が `role="listbox"` を静的に宣言し、`static/js/ta2/ws-spec.js:133`／`:336`／`:430` が同じ箱へ button を描画している

### 2. [Serious] 灰色テキスト `--tx3` が全ページでコントラスト不足（164 ノード）

- **症状**: レールのラベル「ホーム／分析・設計／自動化…」など 10px の灰色文字が背景に対し 2.58:1。計測 5 ページすべてで発生。
- **該当基準**: WCAG 2.2 **1.4.3 Contrast (Minimum) (AA)** / axe `color-contrast` (serious)
- **証拠**: axe 報告 `contrast 2.57 (#98a2b3 on #ffffff, 7.5pt)`、独立計算で #98A2B3/#FFFFFF = **2.58**、#98A2B3/#F6F7F9 = **2.40**。ノード数 `/`46・`/tests`40・`/schedule`36・`/spec`25・`/report`17
- **推定原因**: `static/css/ta2.css:3` の `--tx3:#98A2B3`。適用側は `static/css/ws.css:214`（レールラベル 10px）、`ws.css:22`、`ws.css:30`（10.5px）ほか
- **補足**: 変数 1 行のため修正コストは小さい。#667085 まで暗くすれば 4.97:1 で適合する（実測済み）

### 3. [Serious] サイト一覧の行（role=option）が内部にフォーカス可能な削除ボタンを含む

- **症状**: 24 ノードで option の中に button がネスト。支援技術での役割提示が壊れ、削除操作の到達性が不定になる。
- **該当基準**: WCAG 2.2 **4.1.2 Name, Role, Value (A)** / axe `nested-interactive` (serious)
- **証拠**: `/`・失敗セレクタ `div[data-domain="demomart"]`、`.it[role="option"]:nth-child(4)`・`Element has focusable descendants`
- **推定原因**: `static/js/ta2/ws-home.js:86`（`role="option" tabindex="0"` を付与）と `static/js/ta2/ws-home.js:91`（同じ行の内部に `<button class="del">` を生成）。同型の記述が `static/js/ta2/list.js:108` にもある

### 4. [Serious] 削除ボタンのターゲットが 22×22 px

- **症状**: サイト行とテスト手順行の ✕ が 24×24 px 未満。行自体もターゲットのため間隔の例外が成立しない。
- **該当基準**: WCAG 2.2 **2.5.8 Target Size (Minimum) (AA)**
- **証拠**: 実測 `button.del` = 22.0×22.0（`/` に 8 個以上）、`button.x` = 22.0×22.0（`/tests`）
- **推定原因**: `static/css/ws.css:31`（`.it .del{...width:22px;height:22px...}`）、`static/css/ta2.css:101`（`.st .x{...width:22px;height:22px...}`）

### 5. [Moderate] 見出し階層が全ページで不正（h1 が前に h2、h1 の重複、h2→h4 の飛ばし）

- **症状**: `/` は h2 の後に h1。`/spec` `/tests` `/schedule` `/report` は h1 が 2 個。`/schedule` `/report` は h2 の直後に h4。
- **該当基準**: WCAG 2.2 **1.3.1 (A)** / **2.4.6 Headings and Labels (AA)**
- **証拠**: B-6 の表（5 ページ分の実測見出し列）
- **推定原因**: `templates/workspace.html` の 3 ペイン構成で、リストペイン（h2/h4）と詳細ペイン（h1）が独立に見出しを打っている。`templates/workspace.html:300`（`<div class="ph"><h1>チーム</h1>`）が各パネルで同型に繰り返される

### 6. [Moderate] 検索欄 `#q` に placeholder しかラベルがない

- **症状**: 「検索 / 絞り込み」は入力開始と同時に消える。可視ラベルも `aria-label` もない。
- **該当基準**: WCAG 2.2 **3.3.2 Labels or Instructions (A)**（axe は placeholder をアクセシブル名として受理するため未検出）
- **証拠**: `/sites/demomart/tests` の DOM 走査で唯一のラベルなしコントロールとして検出
- **推定原因**: `templates/workspace.html:70` `<div class="search"><input id="q" placeholder="検索 / 絞り込み"><kbd>⌘K</kbd></div>`
- **対比**: `/schedule`・`/team` のフォームは全件 `<label for>` を持ち、時刻入力にも `aria-label` がある（`templates/workspace.html:238`）。この 1 箇所だけが規約から外れている

### 7. [Minor / 要確認] 時刻入力のフォーカス指標が計測上消えている

- **症状**: `#sched-window-start` / `#sched-window-end` にフォーカスした時点の計算値が `outline-style:none` かつ `box-shadow:none`。
- **該当基準**: WCAG 2.2 **2.4.7 Focus Visible (AA)**
- **証拠**: `/sites/demomart/schedule` のタブ巡回 33 停止中、この 2 件のみ指標なし
- **推定原因**: `static/css/ws.css:103` の `.fld input{...outline:none}` が大域 `:focus-visible`（`outline:2px solid var(--ac)`）を詳細度 0-1-1 対 0-1-0 で打ち消し、代替の `:focus` リングを `ws.css:104` の box-shadow に依存させている
- **注意**: `ws.css:104` が効いていれば box-shadow が観測されるはずで、**計測値とスタイルシートが矛盾している**。修正前に再現確認が必要。断定しない

### 8. [Minor] `script-src 'unsafe-inline'` により CSP の XSS 抑止が実質無効

- **症状**: CSP は設定されているが `'unsafe-inline'` を許可しているため、反射型 XSS をほぼ止められない。
- **該当基準**: OWASP ASVS L1 相当（V14 設定 / CSP）
- **証拠**: D 章の実測ヘッダ（`/` と `/spec` で同一）
- **推定原因**: `templates/workspace.html` がインライン `<script>` と多数のインライン `style` 属性（例: `:304` `style="font-size:11.5px;color:var(--tx3)"`）に依存
- **判定**: ローカル専用設計のため優先度は低い。ただし外部サイトの文字列を取り込んでレポート HTML を生成する製品特性を踏まえると nonce 方式が望ましい

### 9. [Info] Permissions-Policy 不在

- **症状**: `Permissions-Policy` ヘッダなし。**該当基準**: ASVS L1 相当。**証拠**: D 章。**推定原因**: 未設定。カメラ等を使わない UI のため実害は小さいが、追加コストは 1 行

---

## 測れなかったこと

1. **`/team` の axe 判定（未測定）**。ヘッドレス Chromium で 3 回試行し、いずれも完了しなかった。
   - 1 回目: フルプローブが 240 秒でタイムアウト（タブ巡回段階まで到達）
   - 2 回目・3 回目: 軽量版（axe のみ、`wait_until="commit"`、`**/*stream*` と `**/*events*` を abort）でも
     最初の `print("goto ok")` すら出力されず 170〜220 秒でタイムアウト
   - 一方 **サーバ側の `/team` は 200 / 12.0ms / 25,736 bytes と正常**。原因はクライアント側（ページ JS か、先行試行の
     残存 Chromium プロセス 7 個による資源競合）で、**どちらかを切り分けられていない**。`/team` の a11y 状態は不明であり、
     良好とも不良とも報告しない。静的に `templates/workspace.html:300-330` を読む限り、フォーム 5 コントロールは
     すべて `<label for>` を持ち、B-7 の観点では問題は見当たらない（DOM 実測ではない）。
2. **`/` のタブ巡回が未完走**。Tab 45 回の上限に達した（可視フォーカス可能要素 69）。到達不能な要素の不在は証明していない。
3. **`/tests` のタブ巡回はタブ順の後半のみ**。読み込み時のフォーカス位置が先頭になく、28 停止で巡回が終了した。
4. **矢印キーによる listbox 操作（WAI-ARIA APG 準拠）は未検証**。`role="listbox"` を宣言している以上、
   Home/End/矢印キーの実装有無は本来検証すべき項目。
5. **チェックボックスの実効ターゲット矩形は未計測**。`/report` の 14×14px は `<label>` 包含により拡大している可能性があり、2.5.8 の判定を保留した。
6. **認証・認可・レート制限・CSRF は未検証**。`WEBSPEC2DOC_AUTH_MODE=off` で測定したため、ASVS の V2/V3/V4 相当は範囲外。
7. **Chromium 1440×900 のみ**。他ブラウザ・他解像度・拡大 200%（1.4.4 Resize Text）・リフロー（1.4.10）は未測定。
8. **今回の 6 画面以外は未測定**。特に `static/css/testcase-grid.css:18,39,72` は編集セルで `outline:none` を
   指定しており、テストケースグリッド画面に同種のフォーカス可視問題がある可能性がある（未確認）。
9. **動的状態は未測定**。モーダル（`#ov-new` ほか）、エラー表示、実行中のローディング状態は開いていない。
   フォーカストラップ（2.1.2 No Keyboard Trap）と `role="alert"` の実挙動は未検証。

---

# 是正の結果（2026-08-31）

自社が顧客サイトの検査に使っている axe-core（`src/ux/assets/axe.min.js`）を、自分の画面に適用して測定。
タグ `wcag2a` / `wcag2aa` / `wcag22aa`。

| ページ | 是正前 | 是正後 |
|---|---|---|
| `/` | color-contrast ほか多数 | **0** |
| `/sites/demomart/spec` | listbox/button のロール不整合（critical）含む | **0** |
| `/sites/demomart/tests` | color-contrast | **0** |
| `/sites/demomart/changes` | color-contrast | **0** |
| `/sites/demomart/schedule` | color-contrast | **0** |
| `/sites/demomart/report` | color-contrast | **0** |
| 合計 | **164 ノード** | **0** |

## 直したもの（根拠となる達成基準つき）

| 症状 | 達成基準 | 修正 |
|---|---|---|
| 補助文字色 `#98A2B3` が白地 **2.58:1**（実測）で 4.5:1 を割る | 1.4.3 Contrast (Minimum) AA | `--tx3` を `#667085` に（白地 **4.97:1** / 画面地 **4.64:1**）。報告 HTML の `_TX3` も同値に |
| 重複サイト行を `opacity:.55` で薄くしていたため **2.17:1** まで低下 | 1.4.3 | 透明度をやめ、基準を満たす色を指定 |
| `role="listbox"` の子が `role="button"` | 1.3.1 Info and Relationships A | 子を `role="option"` + `aria-selected` に |
| `role="option"` の中に削除ボタン（入れ子の操作要素・24 箇所） | 4.1.2 Name, Role, Value A | 行を `role="listitem"` にし、選択用と削除用の 2 ボタンを並置 |
| 削除ボタンが **22×22px** | 2.5.8 Target Size (Minimum) AA | 26×26px に。行自体が操作対象のため間隔の例外は使えない |
| `h1` が重複し `h2 → h4` の飛びがある | 1.3.1（見出しの階層） | `h1` は現在地バーの 1 つだけにし、パネル見出しを `h2` に |

## 引用上の注意（調査で判明）

- **WCAG 2.2 で 4.1.1 Parsing は削除**された。HTML パースエラーを WCAG 根拠で報告してはいけない
- **JIS X 8341-3:2016 は WCAG 2.0 相当**。2.2 の新規 9 基準を JIS 準拠として示すのは誤り
- **axe-core の「57.38%」は検出された不具合件数の割合**であり達成基準の網羅率ではない。
  Focus Order 0% / Keyboard 2.49% と項目差が大きく、「WCAG の 57% を検査済み」と表示してはいけない
- 現在の `accessibility_audit.json` の但し書き（機械判定可能な項目のみ・適合を保証しない）は上記と整合しており、正しい

## 残課題

- `/team` は測定できていない（headless が 3 回ハング。サーバは 12ms で応答しており、ページ側の欠陥かブラウザ側の輻輳か切り分けできず）
- CSP に `script-src 'unsafe-inline'` が残る（ローカル専用設計だが、外部公開時は要見直し）
- 2.5.7 ドラッグ動作 / 3.3.9 は機械判定できないため未評価

---

# 未着手分の対応（2026-08-31 続き）

## 1. 実装済み技法の導線復活
`src/autorun/techniques.py` に 7 技法＋状態遷移モデルが実装済みだったが、統合時に導線を移植し損ねていた。
`GET /api/ta2/techniques` を追加し、分析・設計に「技法」モードを新設。

実データ（P004 決済）: 状態遷移モデル 2 本 / 分類ツリー 4 / デシジョンテーブル 6 /
原因結果グラフ 14 / ドメイン分析 12 / エラー推測 34。適用できない技法も理由つきで表示する。

根拠の表示は ISO/IEC/IEEE 29119-4:2021 の節番号（5.2.2 / 5.2.5 / 5.2.6 / 5.2.7 / 5.2.8 / 5.4）と
ISTQB の確認済み文言に限定した。カバレッジの計算式は規格の有償部のため引用していない。

## 2. `/team` のハング（自己検証で測れなかった項目）
**ブラウザ側の輻輳ではなく、当製品の無限ループだった。**
`ws-shell.renderCtx()` がサイト未選択（`S.domain === ''`）のとき履歴に該当サイトを探し、
見つからないと `loadHistory()` → 完了で再び `renderCtx()` を呼ぶ循環に入っていた。
`/team` はサイトに属さない画面なので必ずこの経路に入り、ブラウザが固まっていた。

修正: サイト未選択なら「この画面はサイトに属しません」と表示して打ち切る。
サイト指定ありで見つからない場合も、再取得は 1 回だけ。

測定結果: `/team` は **WCAG 2.2（A/AA）違反 0**。

## 3. 残り（対応せず・理由つき）
- ISO 29119-4 5.2.4 構文テスト・5.2.9 シナリオテスト: 画面の解析結果だけでは
  入力構文の完全な定義や業務シナリオが得られない。仕様書の取り込み（Doc Fusion）と
  接続してから実装すべきで、機械的に導くと根拠のないケースを量産する
- N-スイッチ（1 以上）: 生成側の `state_transitions` は 0-スイッチ固定。
  遷移グラフからの経路生成は実装可能だが、爆発を抑える基準（ISO 29119-4 6.2.8）が
  有償部で未確認のため、根拠を確定してから着手する
