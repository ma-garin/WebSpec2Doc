# C. Hybrid（Evidence 中心）共通 UI 契約

採用: 2026-10-20（DESIGN_OPTIONS.md の推奨 C）。モック: mockups/c-hybrid.html。
正本: static/tokens.css（主色 #2563EB・意味色 success/warning/error/info）。新フレームワーク禁止（vanilla JS・CSS）。

## ファイル（Wave2 で作る。以後は各 System が使うだけ。編集は共通担当のみ）
- static/css/c-hybrid.css … 部品（クラス接頭辞 `c-`）。tokens.css の変数だけを使う
- static/css/c-shell.css … シェル（サイドバー・トップバー）の見た目を C に揃える上書き
- static/js/c-hybrid.js … `window.WS2D`（下の API）。依存なし・ES5 互換・XSS 防止（文字は textContent かエスケープ）

## 語彙（UI に出す語。内部の状態名は各 System のままでよく、表示時に対応付ける）
### 工程の状態 `WS2D.status`
| code | 表示 | 形 |
|---|---|---|
| not_started | 未開始 | ○ |
| preparing | 準備中 | ◔ |
| running | 実行中 | ▶ |
| waiting_review | 確認待ち | ? |
| waiting_approval | 承認待ち | ! |
| partial | 一部完了 | ◐ |
| done | 完了 | ✓ |
| failed | 失敗 | × |
| cancelled | 中止 | ■ |
| unverified | 未確認 | ◌ |
| unavailable | 利用不可 | ⊘ |
工程バッジは角丸四角（`c-status`）。Evidence バッジと形を変えて混同させない。

### Evidence の状態 `WS2D.evidence`
| code | 表示 | 形 | 区分 |
|---|---|---|---|
| observed | 実測 | ● | 事実 |
| observed_auth | 認証済み実測 | ●＋鍵 | 事実 |
| record | 記録 | ▣ | 事実 |
| document | 文書 | ▭ | 事実 |
| static | 静的 | ○ | 推論 |
| inferred | 推論 | ◐ | 推論 |
| ambiguous | 曖昧 | ◇ | 推論 |
| unverified | 未確認 | ◌ | 未確認 |
| unavailable | 利用不可 | ⊘ | 未確認 |
Evidence バッジはピル型（`c-ev`）。形＋文字＋色の 3 つで示す（色だけにしない）。
3 区分（事実／推論／未確認）は KPI・一覧・ドロワーで同じ並び・同じ語。

## JS API（window.WS2D）
- `WS2D.status.html(code, label?)` / `WS2D.evidence.html(code, label?)` → バッジ HTML 文字列。`WS2D.evidence.category(code)` → 'fact' | 'inference' | 'unverified'
- `WS2D.kpis(host, items)` items: [{label, value, sub?, href?, onClick?, category?}]。value が null なら「未計測」。数字はリンク（根拠の一覧へ）
- `WS2D.state(host, {kind, title?, message, next?, retained?, actionLabel?, onAction?})` kind: loading | empty | error | partial | permission | unavailable | unverified | stale。retained=true なら「既存の結果は保持しています」を出す。エラーは「何が起きた／既存結果は保持されたか／次に何をするか」
- `WS2D.reason(host, text, kind?)` 画面上部の「状態の理由」1 行（`c-reason`）
- `WS2D.drawer.open({title, state, stateReason, claim, facts:[{label, value}], inferences:[...], limitations:[string], sources:[{label, value}], extra?, returnFocus})` 固定順: 1 主張 → 2 実測事実 → 3 推論 → 4 制限 → 5 出典・位置・provider・version。role=dialog・aria-modal・Esc・フォーカス閉じ込め・閉じたら returnFocus へ。1440px 以上は本文を押して並べ、未満はオーバーレイ。`WS2D.drawer.close()`
- `WS2D.confirm({title, message, detail?, confirmLabel, danger?})` → Promise<boolean>。破壊操作は danger=true（消えるもの・元に戻せるかを文字で）
- `WS2D.toast(message, kind?)` aria-live=polite。kind: info | success | warning | error
- `WS2D.modal.open({title, body(HTMLElement|string), actions:[{label, primary?, onClick}]})` / `close()`
- `WS2D.esc(s)` エスケープ

## CSS 部品（c-hybrid.css）
`c-page-head`（何の画面か 1 文・状態・主操作 1 つ・副操作）、`c-context`（現在の対象・最終実行・状態）、`c-reason`、`c-stepper`（工程上の位置）、`c-kpis`/`c-kpi`、`c-table`（中密度 1 行 36px・内側スクロール・816px 以下はカード化）、`c-filter`、`c-tabs`（role=tablist）、`c-status`、`c-ev`、`c-split`（事実／推論／未確認の 3 区分の帯）、`c-state`、`c-btn`（primary/secondary/danger/ghost）、`c-drawer`、`c-modal`、`c-confirm`、`c-toast`、`c-empty`。focus-visible を必ず見せる。prefers-reduced-motion で動きを止める。

## Product Truth（UI で破らない）
inferred→observed・static→到達済み・URL 到達→機能正常・method 不明→GET・generated→executed・exported→verified・Partial→Success・mock→implemented・sample→production・認証あり→正常動作・provider unavailable→success をしない。
