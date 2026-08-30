# TA2 ビジュアル QA — 対話状態の実測と修正（2026-08-30）

対象: `/test-automation?domain=demomart`（`FLASK_TESTING=1 WEBSPEC2DOC_AUTH_MODE=off`・ポート 8765）
方法: Playwright headless（`venv/bin/python`）で 1440×900 と 1280×800 を全状態走査。
計測スクリプト `/.playwright-mcp/ta2_sweep.py`、証跡 PNG は `/.playwright-mcp/{pre,post,fix,fin}-*.png`。
静的スクショでは見えない「重なり・はみ出し・フォーカス・キーボード」を、**数値（矩形・scrollWidth・elementFromPoint・activeElement）で判定**した。

見た目（承認済み `docs/plan/design-ideas/prototype-visual-editor.html`）は変えていない。壊れる条件だけ直した。

---

## 検査した状態と結果

| 状態 | 1440×900 | 1280×800 | 結果 |
|---|---|---|---|
| ホバー: レール 6 ボタンのツールチップ | 全 6 件 opacity 1・一覧ペインの上に描画 | 同左 | OK（z-index 済み） |
| ホバー: 一覧行 / ステップカード / `.x` 削除ボタン | 表示・押下可 | 同左 | OK |
| ホバー: フィルム・drift/site カード・表の行・全 `.btn` | 表示 | 同左 | OK |
| 長い文字列: サイト名 `hotel-example-site.takeyaqa.dev` | h2 が 11px モノスペース灰で描画 | 同左 | **NG → 修正 V-3** |
| 長い文字列: 一覧行 60 字 | 省略記号で切れる | 同左 | OK |
| 長い文字列: グループ見出し | 件数が押し出される | 同左 | **NG → 修正 V-4** |
| 長い文字列: ステップ `.v` / `.loc` | 折返し可・分割不能文字列で破れる | 同左 | **NG → 修正 V-5** |
| 長い文字列: エディタヘッダ h1 | 420px で省略・code が伸びる | 同左 | **NG → 修正 V-6** |
| 長い文字列: KPI / drift タイトル / 地図カード | カード幅を超える | 同左 | **NG → 修正 V-10** |
| ピッカー: 吹き出しの位置 | 右端は clamp・**下端 clamp なし** | 同左 | **NG → 修正 E-1** |
| ピッカー: pick bar が seg を覆うか | bar top 108 / seg bottom 89.5 | bar top 108 / seg bottom 89.5 | OK（覆わない） |
| ピッカー: Escape で中止 | 中止 | 中止 | OK |
| ピッカー: 外側クリックで中止 | **中止しない** | **中止しない** | **NG → 修正 E-2** |
| モーダル: new / trace / help の表示 | 画面内に収まる | 同左 | OK |
| モーダル: 開いた直後のフォーカス | **背後のトリガに残る** | 同左 | **NG → 修正 M-1** |
| モーダル: Escape / 外側クリックで閉じる | 閉じる | 同左 | OK |
| モーダル表示中のトースト | `elementFromPoint` が `.toast` を返す＝最前面 | 同左 | OK |
| モーダル中の背景スクロール | `html,body{overflow:hidden}` で発生せず | 同左 | OK |
| パネル ▶ / ◈ / ⌂ | 横あふれなし | 同左 | OK |
| パネル ▶: 長いテスト名 | 行が 4 行に膨らむ（1 行 150px 超） | 同左 | **NG → 修正 V-9** |
| パネル ◈: 長い HTML の Before/After | `word-break:break-all` で折返し | 同左 | OK |
| キーボード: Tab 到達範囲 | 状態チップに**到達できない** | 同左 | **NG → 修正 A-1** |
| キーボード: フォーカスリング | UA 既定のみ（角丸で欠ける） | 同左 | **NG → 修正 V-2** |
| キーボード: `↑` `↓` 選択移動 + スクロール追従 | 移動・`selInView: true` | 同左 | OK |
| キーボード: `⌘K` | `#q` にフォーカス | 同左 | OK |
| キーボード: `R` / `Escape` | 実行 / 中止 | 同左 | OK |
| 空: `?domain=nope` | **黙って別サイトを表示（案内なし）** | 同左 | **NG → 修正 U-1** |
| 空: 絞り込み 0 件 | 「該当なし」だけで戻し方がない | 同左 | **NG → 修正 U-2** |
| 実行中: レールバッジ / ボタン / ピル | `■ 実行を中止`・ピル`実行中`・バッジ表示 | 同左 | OK |
| ビューア: ステップ多数のフィルム | **browser 枠の外へ 1000px 以上はみ出す** | 同左 | **NG → 修正 V-7** |
| ビューア: `失敗時` 画像 | `object-fit:contain` で枠内に収まる | 同左 | OK |
| ステップペインの内部スクロール | `.steps{overflow:auto}` で内部のみ | 同左 | OK |
| スクロールバー: ページ全体 | `docW==cliW`, `docH==cliH` | 同左 | OK（無し） |
| console エラー | **0 件**（初期・長文字列・パネル・モーダル・実行・空ドメイン） | **0 件** | OK |

---

## 修正一覧（ファイル:行）

### 表示の破綻

| # | 内容 | 場所 |
|---|---|---|
| V-1 | `[hidden]` が `.btn{display:inline-flex}` に負け、**API の無い「証跡をまとめて書き出す」ボタンが出ていた**（契約 §0 違反）。`[hidden]{display:none!important}` で意図どおり非表示に戻した | `static/css/ta2.css:253` |
| V-2 | `:focus-visible` を `--ac` の 2px アウトラインで統一。`.it` `.st` `.strip .th` `.scard` `.fchip` にも付与。`.st:focus-within .x` で削除ボタンをキーボードでも出す | `static/css/ta2.css:256` |
| V-3 | `#site-name` が件数用の `h2 span`（11px・モノスペース・灰）を拾っていた。原型は h2 の地の文。15px/700/`--tx`/sans に戻し、省略記号を付けた | `static/css/ta2.css:263` |
| V-4 | 長い画面名でグループ見出しの件数が押し出される。`.grp{overflow-wrap:anywhere}` + `span{flex:none}`。`.it code` も `flex:none` | `static/css/ta2.css:270` |
| V-5 | `.st` グリッド中央セルの `min-width:auto` で長いセレクタが枠を破る。`min-width:0` + `overflow-wrap:anywhere` | `static/css/ta2.css:278` |
| V-6 | ヘッダの `code` / `hist` / `btn` が伸びて実行ボタンを画面外へ押し出す。`flex:none` と `code` の 230px 省略 | `static/css/ta2.css:283` |
| V-7 | フィルムがステップ数だけ横に伸び、browser 枠外（最大 +1180px）まで溢れていた。`overflow-x:auto` にして内部スクロール化、`.lab` を sticky 化 | `static/css/ta2.css:290`, `:350` |
| V-8 | 吹き出しの `max-width`/`max-height` を stage 基準で上限化。pick bar も折返し可に | `static/css/ta2.css:294` |
| V-9 | 実行結果テーブルを `table-layout:fixed` にし、テスト名・画面列を 1 行省略（`td.nm` / `td.scr`）。**行高 150px 超 → 38px** | `static/css/ta2.css:298` / `static/js/ta2/panels.js:186,187,200,201` |
| V-10 | drift 見出し・Before/After・地図カード・KPI に `min-width:0` と `overflow-wrap:anywhere` | `static/css/ta2.css:304` |
| V-11 | `.md .mb{min-height:0}`（縦に詰まったとき本文が縮まない） | `static/css/ta2.css:316` |
| E-1 | ピッカーの吹き出しに**下端 clamp が無く**、browser 下部の要素を選ぶと画面外へ落ちて操作不能になる。追加後に実寸を測り、下に置けなければ要素の上へ回す。左右の clamp もハードコード 320 → 実寸に | `static/js/ta2/editor.js:282` |

### 対話・アクセシビリティ

| # | 内容 | 場所 |
|---|---|---|
| E-2 | 選択モード中に無関係な場所を押しても中止されず、以後どこを押しても反応しない状態に見えた。外側クリックで `stopPick()` | `static/js/ta2/editor.js:331` |
| M-1 | モーダルを開いてもフォーカスがトリガに残り、Tab が背後を巡回・Enter が背後のボタンを押していた。`open()` で中へ移し、閉じたら元へ戻す（Escape・外側・`[data-close]` すべて） | `static/js/ta2/modals.js:26,46,54,265,269` |
| A-1 | 状態チップが `<span>` で Tab 到達不能だった。`role="button" tabindex="0" aria-pressed` + Enter/Space で押下 | `templates/test-automation.html:60-64` / `static/js/ta2/list.js:69,149` |

---

## 使い勝手の修正

| # | before | after | 場所 |
|---|---|---|---|
| U-1 | `?domain=nope` のように存在しないドメインを指定すると、**黙って別サイトのテストを表示**していた（今どのサイトを見ているか分からないまま操作させる） | 一覧ヘッダに消えない案内を出す:「『nope』のクロール結果がありません。代わりに『127.0.0.1:8765』を表示しています。上の選択欄でサイトを変えられます。」+ サイト選択欄を強制表示（1 件しか無くても切替口を残す） | `static/js/ta2/app.js:36,150` |
| U-2 | 絞り込みが 0 件のとき「該当なし」だけ。**なぜ 0 件かも、戻し方も分からない** | 「条件に合うテストがありません／検索『x』 で 1641 件中 0 件」＋「絞り込みを解除」ボタン。テストが 1 件も無い場合は作り方（＋ 新しいテスト / ⌂ サイトの地図）を案内 | `static/js/ta2/list.js:103,134` |
| U-3 | 選択モードで無関係な場所を押しても何も起きない（Escape を知らないと抜けられない） | 外側クリックで中止（E-2 と同じ修正） | `static/js/ta2/editor.js:331` |
| U-4 | 要素を選んだ直後、値の入力欄までもう 1 クリック必要だった | 吹き出しを開いたら `#pk-arg` に自動フォーカス | `static/js/ta2/editor.js:293` |
| U-5 | 実行結果表の失敗理由が 60 字で無言のまま切れていた | 60 字超は `…` を付け、`title` に全文を持たせた | `static/js/ta2/panels.js:117` |
| U-6 | 実行完了後、失敗が下の方にあると自分で探す必要があった | 失敗があれば最初の失敗行を `scrollIntoView` で見える位置へ送る | `static/js/ta2/panels.js:419` |
| U-7 | 実行結果表のテスト名・画面名が省略されると全文を確認する手段が無かった | `title` 属性で全文をホバー表示 | `static/js/ta2/panels.js:186,200,201` |
| U-8 | 一覧フッタの `▶` がアイコンのみ・`title` が「全件実行」だけで対象が曖昧 | `title="このサイトのテストを全件実行"` + `aria-label="全件実行"` | `templates/test-automation.html:67` |
| U-9 | 「未作成 · 地図から生成」行は押せるのに `cursor:default`（押せないように見える）。状態チップも同様 | `.it.empty[data-gen]` と `.fchip` に `cursor:pointer` | `static/css/ta2.css:270` |

---

## 共通導線の追加

ユーザー報告:「他システムへ行く導線・ログアウト・ユーザーメニューが無く、ヘッダが他画面と違う」。
`templates/index.html`（`.sys-switcher`）と `templates/partials/topbar.html`（`.usermenu`）の**項目と並びをそのまま踏襲**し、56px レールに収まる形へ落とし込んだ。

| 位置 | 追加したもの | 場所 |
|---|---|---|
| レール最上部 | `W` ロゴを `/systems` へのリンク化。ツールチップ「システム選択へ戻る」 | `templates/test-automation.html:18` |
| その直下 | システム切替（`TA` バッジ・`/systems`）。ツールチップ「テスト自動化 · システムを切り替える」。下に区切り線 | `templates/test-automation.html:19,20` |
| レール下部（`?` の上） | ユーザーアバター（`auth_user.name` の頭文字／認証オフは「ゲ」）。押すとレール右側にポップオーバー | `templates/test-automation.html:26-31` |
| ポップオーバー中身 | 氏名 + メール（未ログイン時は「未ログイン（認証オフ）」）／個人設定 `/account`（`auth_user` 時のみ）／ユーザーガイド `/user-guide`／フィードバック `/feedback`／システムを切り替える `/systems`／ログアウト `<form method="post" action="/auth/logout">`（`auth_user` 時のみ） | 同上 |
| 挙動 | Escape・外側クリックで閉じる。`aria-haspopup` / `aria-expanded` / `role="menu"` を更新し、開いたら先頭項目へフォーカス | `static/js/ta2/app.js:54,136` |
| スタイル | `.rail .lg` `.sysbtn` `.rail-sep` `.ta-user` `.upop` `.uitem`。`.upop` は `z-index:40`（レールの stacking context 内 = 一覧の上／モーダル `z-index:50` の下） | `static/css/ta2.css:319` |

検証（実測）:

- リンク応答: `/systems=200` `/account=200` `/user-guide=200` `/feedback=200`
- ポップオーバー: 1440・1280 とも `inView: true` / `covered: false`（`elementFromPoint` が自分自身を返す）/ `aria-expanded="true"` / 先頭項目にフォーカス
- Escape・外側クリックで `hidden: true` に戻る（両幅）
- console エラー 0 件。ゲスト状態（`auth_user` なし）でもテンプレートエラーなし
- 証跡: `.playwright-mcp/post-1440-usermenu.png` / `post-1280-usermenu.png` / `fin-1280-site.png`

---

## 直さなかった観測（理由つき）

1. **ステップハイライト（`.st.run` / `.st.done`）が実行中に点かない。**
   `run/status` が `current_step` を返さない実装のため、`state.js:applyStepProgress` が意図的に何も塗らない（契約 §0 捏造禁止）。
   フロントだけで直すと進捗を捏造することになるので触っていない。**API 側の課題**として残す。
2. **`.strip` の横スクロールバーが OS 設定によっては常時表示になりうる。**
   `scrollbar-width:thin` は指定したが、`::-webkit-scrollbar` の自作は承認済みデザインに無い装飾なので入れていない。
3. **ステップカード・フィルムのサムネイル・一覧行はキーボードで直接操作できない。**
   一覧は `↑` `↓`、ステップは選択中テストの文脈に依存する。`tabindex` を全付与すると Tab 回数が数十回になり、承認済みの操作体系（`⌘K` / `↑↓` / `R`）と競合する。ロービング tabindex の導入は設計判断が要るため見送り、フォーカスリングのみ整えた。
4. **`.alert` のプレースホルダは `visibility:hidden` のため選択モードで拾えない。**
   「エラー表示領域」は失敗時にしか出ない要素で、ワイヤーフレーム上でも隠れているのが正しい状態。選ばせるには表示ロジックの変更が必要でデザイン変更にあたる。
5. **`証跡をまとめて書き出す` は V-1 で非表示に戻した。**
   テンプレートの `hidden` とコメント（「証跡 ZIP / JUnit XML を作る API はまだ無い」）が正。CSS のバグで表示されていただけで、押すと選択中 1 件の report が開くだけでラベルの約束（一括書き出し）を果たしていなかった。API ができたら `panels.js` が `hidden` を外す。
6. **`#items` がスクロール領域として Tab フォーカスを受ける（Chrome の仕様）。**
   スクロール可能領域をキーボードで送れるのは正しい挙動なので `tabindex="-1"` を付けて順序からは外し、プログラム的なフォーカスだけ残した。

---

## 未検証

- 実データでの実行完走（`demo/site` の 8766 が停止中のため、実行は「開始・実行中表示・中止ボタン」までの確認）
- `auth_user` が実在する（ログイン済み）状態でのポップオーバー表示。ゲスト分岐のみ実測、ログイン分岐はテンプレートの条件式のみ確認
- `make test` / `make verify-ui` / `quality_harness` は未実行（H-7: 要求時のみ）
