# Agent E: Design System / CSS 監査

対象: origin/main 0efbd20（worktree wt-gui）。静的 grep/wc のみ。実画面は未確認。

## 事実（数値つき）

### 1. トークンが 2 系統ある（最大の構造欠陥）
- 正本 `static/tokens.css`（87 行・変数 68）: `--color-*`（primary/critical/high/medium/low/info とその -bg/-border）・`--text-xs..2xl`・`--space-1..12`・`--radius-*`・`--shadow-*`・`--motion-*`・`--font-main/mono`
- 別系統 `static/css/ta2.css:2-12` の `:root`: `--bg --sf --line --tx --ac --ok --ng --wa --sans --mono`。primary は tokens `#1976D2` に対し ta2 `#2563EB`。フォントは tokens `Noto Sans JP` 先頭に対し ta2 `Inter` 先頭
- さらに `static/app.css` に別名 31 本（`--text-muted --border --primary --surface --critical --info-bg --radius` 等）。参照数は `--text-muted` 327・`--border` 276・`--primary` 143
- 参照量: `var(--color-*)` 1177 回 / ta2 短縮名 `var(--bg|--tx|--ac|--ok|--ng|--wa…)` 1313 回。ワークスペース・システム選択・healing・impact・orchestration・docverify は ta2 系、index.html（旧ビュー）・components.css は `--color-*` 系
- tokens.css に意味色 success / warning / error が無い。critical/high/medium/low/info を「重大度」と「状態」で兼用している
- ダークテーマ定義 0 件（`prefers-color-scheme` / `data-theme` が CSS 全体で 0。tokens.css のコメントは「light/dark 両テーマ」と書くが :root 1 つのみ）
- 未定義変数の参照 28 種: `--success --warn --danger --er-bg --wn-bg --high-bg --color-success --color-text-tertiary --primary-border --surface-2 --surface-alt --hl-*` 等（viewpoints.css・components.css・healing*.css・app-report.css・view-settings.html）。フォールバック有無は未確認

### 2. 生の色（#hex）。CSS 全体で hex 1135 個、var(--) 参照 5275 回
| 順 | ファイル | hex+rgb | var 参照 |
|---|---|---|---|
| 1 | css/healing.css | 170 | 236 |
| 2 | css/healing-reports.css | 112 | 106 |
| 3 | css/ta2.css | 97 | 289 |
| 4 | css/orchestration.css | 74 | 70 |
| 5 | css/docverify-tier-1.css | 72 | 52 |
| 6 | css/docverify-tier-2.css | 72 | 53 |
| 7 | css/system-select.css | 71 | 32 |
| 8 | app-report.css | 55 | 421 |
| 9 | css/impact.css | 54 | 102 |
| 10 | css/components.css | 51 | 824 |
- ta2.css の 97 は `:root` 定義分を含む。他は意味色の直書き（`#FEE4E2 #B42318 #FDA29B` 等 ta2 系の値を hl-badge が再記述）
- templates 内 `<style>` ブロックは 6 ファイル（traceability / healing_report_print / system-select / orchestration_b / view-settings / view-usage）。生色 hex は healing_report_print 13・system-select 9

### 3. inline style・typography・responsive
- templates の `style="` 278 件: view-settings 81 / view-generate 64 / workspace 40 / view-auto-run 19 / modal-autorun-login 14 / view-user-guide 8 / view-qa-quality 7 / view-viewpoints 5 / index 5 / modal-user-admin 4。JS 内 `style="`/cssText 行 169（ws-spec 14・panels 14・view-report 13・results 12・view-overview 10・docverify-review 10）
- font-size: px 直書き 1199 / `var(--text-*)` 357 / rem・em 11。px の種類 29。分布は 12px:286 11px:234 13px:189 12.5px:134 11.5px:78 14px:46 10.5px:46 10px:38 15px:35。トークン段（11/13/14/16/18/22/28）に乗らない px が 675 件。10px 以下 47 件（10px:38・9px:8・8px:1）
- viewport meta: 通常ページは設定済み。欠落は auth/tenant.html（ほか docverify/_*.html 9 本は partial の可能性・未検証）
- `html,body{overflow:hidden}`: ta2.css:14・orchestration-b.css:9・orchestration-d.css:5 と app.css:42 `body.app-page`。system-select.css:181 が「8 枚が 1440x900 に収まらず切れる」ため個別に解除（同種の見切れ再発点）
- `@media` 58 件のうち reduced-motion 10・幅指定 48。幅の閾値は 640/760/820/860/900/1020/1100/1200/1280 と散在（統一ブレークポイント無し）。`min-width:Npx` 直書きは app-report 10・components 8・app 7・viewpoints 5・docverify 5。`width:300px 以上` 固定は ta2 3・docverify-tier-2 3 ほか
- overflow:hidden は components 23・ta2 18・healing 17・app-report 17・app 16（見切れ温床。check_clipping.py の対象）

## 部品の重複実装（同じ役割の別実装数）
| 役割 | 実装数 | 代表（file:クラス） |
|---|---|---|
| button | 29 接頭辞 / 58 クラス | ta2 `.btn`（唯一の素の .btn）。ほか arep-btn・dv-btn・hl-btn・rv-btn・cd-btn・pager-btn・btn-primary(app.css, app-components.css 重複) |
| badge/chip/pill | 34 接頭辞 / 78 クラス / 24 ファイル | `.badge`(components) `.pill`(ta2) `.hl-badge`(healing と healing-reports で二重定義) `.rv-badge` `.dv-chip` `.vp-chip` `.arv-badge` `.asr-badge` `.im-rea-b` |
| modal/dialog | 10 実装 | `.cmp-modal` `.autorun-modal` `.dv-modal` `.bs-modal` `.im-modal` `.cd-dialog` `.input-dialog-card` ほか。ta2 系に共通 modal 無し。role="dialog"/aria-modal は templates+js で 21 |
| drawer | 共通 0 | rv 側 2 クラスのみ。drawer の正本無し |
| toast/banner | toast 5 実装 + banner 5 | `.toast`(app-components) `.toast`(ta2.css:242, 406 の二重) `.bt-toast` `.bs-toast` `.dv-toast` `.hl-toast`。banner: `dv- bt- bs- hl- cd-` |
| table | 44 接頭辞 | `.dv-table` `.arep-table` `.hl-*` `.tds-table` `.account-table` `.uadm-table` `.cli-table` `.mbt-table` `.rh-table` `.traceability-table` ほか |
| tabs/seg | 9 実装 | `.result-tab`(app.css と report-v2.css 二重) `.set-tab` `.vp-tab` `.bs-tabs` `.dv-tabs` `.rv-tab` ta2 `.seg` |
| empty | 19 実装 | `.empty` `.dashboard-empty` `.qa-empty-state` `.arep-empty` `.bt-empty` `.hl-empty`(healing と healing-reports) `.dv-empty` `.rv-empty` `.ui-empty`(report-v2) ws `.list-empty` ほか |
| loading | 7 実装 | `.spinner`(app.css) `.arep-loading` `.dv-loading` `.rr-loading` `.rv-loading` `.ui-skeleton` `.discover-loading` |
| KPI/tile | 11 実装 | `.kpi`(ta2) `.stat-card`(app.css と components.css 二重) `.arep-tile` `.rv-tile` `.dvr-kpi` `.dv3-stat` `.kpi-tile` `.runs-stat-card` `.rep-kpi` |
- `ui-empty / ui-skeleton`（report-v2.css:87,114）が唯一「共通部品」を意図した命名だが、ワークスペースの ta2 系ページには読み込まれていない（workspace.html は tokens/app/user-menu/ta2/ws/testcase-grid/reverse-analysis のみ）

## 状態語彙（UI 文言の出現数: templates + static/js）
- 完了 99 / 成功 50 / 合格 22 / 済み 208（全て「うまくいった」の同義）
- 失敗 297 / エラー 79 / 不合格 11 / NG 27 / FAIL 11。失敗文は `失敗しました` 121・`できませんでした` 127・`取得できません` 47・`に失敗` 124 が混在
- 実行中 76 / 読み込み中 44 / 取得中 3 / 生成中 5 / 解析中 9 / 処理中 2 / 準備中 2 / 英語 Loading 28
- 未確認 41 / 未検証 23 / 未実行 29 / 要確認 48 / 確認待ち 11 / 承認待ち 25 / 要対応 8（要確認=人が見る、確認待ち/承認待ち=人の入力待ちが混在）
- キャンセル 24 / 中止 37 / 中断 23（同義の 3 語）。空状態: 「ありません」255・「まだありません」30・「0 件」30 と「0件」17（半角スペース揺れ）・「なし」121・未設定 39・未登録 4
- 英語: NG 27・OK 13・PASS 14・FAIL 11 が日本語 UI に混在

## Evidence 状態の表示実装（ファイルとラベル・色の差）
| 実装 file | ラベル | 色 |
|---|---|---|
| js/ta2/ws-reverse.js:16 + css/reverse-analysis.css:65-70 | 実測/静的/推論/曖昧/未確認/利用不可 | 緑/青/黄(文字が #FBC02D)/橙/破線グレー/赤 |
| js/impact/rea.js:7 + css/impact.css:176-184 | 推論/曖昧/未確認 + 到達(実測) | 推論=青 #EFF8FF 直書き、曖昧=黄 ta2、到達 unreached/auth/failed=同一の黄 |
| js/autorun-static-routes.js:70-74 + css/autorun-static-routes.css:34-36 | 実測(認証済み/未認証)・未到達・要認証・曖昧・失敗 | 実測=緑、未到達と失敗=赤、要認証と曖昧=黄 |
| js/view-design.js:400 + components.css:1980 | 実測 1.0 / カタログ | #d7f0dd #fdeecd 直書き |
| js/healing-reports.js:417, js/orchestration.js:31 | 実測/入力/AIの提案/前提/未確認（出所 5 値） | 別体系（出所であって状態ではない。同名 SOURCE_LABELS が 2 ファイルに重複） |
- 差: 「曖昧」は reverse=橙 / impact=黄 / static-routes=黄で 3 色。「推論」は reverse=黄 / impact=青。「未確認」は reverse=破線グレー / impact=グレー実線 / healing=出所ラベル。「認証済み」は autorun-static-routes のみ（reverse・impact に無い）
- `rv-oc-success` は info(青)、`rv-st-observed` は low(緑)。同じ画面内で「成功」の色が 2 つ
- `rv-st-inferred` は色 `--color-medium`(#FBC02D) を文字色に使用。淡黄地で WCAG 1.4.3（4.5:1）を満たさない見込み（未計測）

## 共通 contract に昇格すべき部品（優先順・正本・file）
1. 意味色トークン: `static/tokens.css` に `--color-success/-warning/-error/-info/-neutral`(+ -bg/-border/-text) を追加し、ta2.css の `--ok/--ng/--wa/--ac` と app.css の別名 31 本を tokens への alias 化（正本=tokens.css。値は ta2 の AA 検証済み `-tx` 系を採用）。ダーク定義も同時に
2. StatusBadge(1 部品・語彙固定 enum): 正本=ta2.css `.pill`+`.fchip` を拡張。置換対象は `.hl-badge .rv-badge .asr-badge .im-rea-b .badge .arv-badge .mbt-badge`
3. EvidenceBadge: 正本=reverse-analysis `rv-st-*` の 6 状態 + 認証済みを足す。js/ta2/ws-reverse.js `STATE_LABEL` を共通 JS に移し impact/rea.js・autorun-static-routes.js が参照
4. Button: 正本=ta2.css `.btn`（唯一の素の .btn）。`.arep-btn .dv-btn .hl-btn .rv-btn .cd-btn` を variant（primary/ghost/danger）に寄せる
5. Modal/Dialog + Drawer: 正本は新設（focus trap・Esc・role="dialog" を持つもの）。10 実装を置換。現状は ta2 系に正本無し
6. Toast/Banner: 正本=ta2.css:242 `.toast`（二重定義を 1 本に）。`.bt- .bs- .dv- .hl-` を置換
7. EmptyState/Loading/ErrorState: 正本=report-v2.css `.ui-empty/.ui-skeleton` を ta2 系に読み込む形へ昇格（文言テンプレ: 何が無い・次の行動 1 行）
8. KPI tile: 正本=ta2.css `.kpi`。9 実装を寄せる
9. Tabs/Seg: 正本=ta2.css `.seg`
10. Table: 共通 `.tbl`（sticky head・狭幅時の data-l カード化は reverse-analysis と autorun-static-routes にあり、これを正本の下敷きに）

## 意味色・状態語彙の統一案（表 1 個）
| 意味 | 語彙(固定) | 色トークン | 同義で廃止 |
|---|---|---|---|
| 成功 | 完了 | success | 成功・済み・合格・OK |
| 失敗 | 失敗 | error | エラー・NG・不合格 |
| 実行中 | 実行中 | primary | 処理中・取得中・生成中 |
| 待機 | 確認待ち | warning | 承認待ち・要確認の一部 |
| 要判断 | 要確認 | warning | 要対応 |
| 未実施 | 未実行 | neutral | 未着手 |
| 根拠なし | 未確認 | neutral 破線 | 未検証(結果に限る) |
| 中断 | 中止 | neutral | キャンセル・中断 |
- Evidence 7 状態: 実測=success / 静的=info / 推論=primary 薄 / 曖昧=warning / 未確認=neutral 破線 / 利用不可=error / 認証済み=success 内の「認証済み」修飾（別バッジでなく併記）
- 失敗文は「〇〇に失敗しました。次の行動」1 型、空状態は「〇〇はまだありません」1 型、件数は「0 件」（半角スペース）に統一

## P0 候補
- E-P0-1 トークン 2 系統の統合: `--color-*` と ta2 短縮名が併存（primary #1976D2 と #2563EB、フォント Noto/Inter）。同一アプリ内で画面ごとに青とフォントが違う。tokens.css に集約し alias 化。
- E-P0-2 意味色（success/warning/error）が正本に無く、未定義変数 28 種を参照。参照先が無い箇所は色が付かず成功/失敗が見えない恐れ（フォールバック有無は未確認）。
- E-P0-3 Evidence/Status バッジが 5 実装で色・ラベルが不一致（曖昧が橙/黄、成功が青/緑）。誤読リスクのため共通 EvidenceBadge/StatusBadge を先に作る。
- E-P0-4 `rv-st-inferred` の黄文字（#FBC02D）が淡黄地でコントラスト不足の見込み。実測して `-tx` 系へ。
- E-P0-5 Modal/Dialog が 10 実装で共通 contract 無し（focus trap・Esc の統一が保証できない）。共通 Modal を新設。
- E-P0-6 `html,body{overflow:hidden}` 方式で system-select が切れた実績（system-select.css:181）。ページ別解除でなく共通レイアウト contract に「縦スクロール領域」を定義。
- E-P1 参考: 10px 以下 47 件・tokens 外 px 675 件・inline style 278+169 件・dark 定義 0・viewport 欠落 1 本（auth/tenant.html）。
