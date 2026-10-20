# System 06 ドキュメント検証（docverify）コード地図

2026-10-18 時点の main（9039483）の docverify 関連 73 ファイルを全行読んで作成。ファイルごとの役割・主な要素・依存・注意。
要点は `.claude/rules/docverify-map.md`（docverify のファイルを扱うと自動で読み込まれる）。

> 2026-10-20 改名（G5）: 世代名ファイルを役割名に改名した（本文のファイル名は追従済み）。旧 r3 画面
> （`templates/docverify/_r3.html`・`static/js/docverify-r3.js`・`static/css/docverify-r3.css`）はどのテンプレートからも
> 読み込まれていなかったため削除した。本文に残る r3 画面の節は履歴として読む。

### `templates/doc_verify.html`（78 行）
- 役割: System 06 の単一ページ殻。サイドバー（data-nav）と本文領域に各 partial を include し、CSS/JS を読み込んで `DV.start()` を呼ぶ。
- 主な要素:
  - `<body class="app-page dv-page">`（18）、`.app-shell`>`aside.app-sidebar`（22-51）>`.app-main`（53）>`main#app-content.dv-content`（56）
  - サイドバー: `#dv-new-review`（25、「＋ 新しいレビュー」）、`nav.app-nav`（26）
  - data-nav 一覧: 全体 `home`(28) `mine`(29) `reviews`(30) `findings`(31)／レビュー内（`#dv-review-nav` 35 の中、`#dv-review-name` 33 がレビュー名）`plan` `read` `triage` `questions` `followup` `screen` `gate` `setcheck`(36-42)／管理 `checklists` `metrics` `accuracy` `settings`(46-49)
  - 件数バッジ `[data-count]`: `mine`(29)、`open`(31、class red)、`candidates`(read)、`adopted`(triage)
  - `#dv-banner`（57、role=alert）、`#dv-toast`（58）、`dialog#dv-modal`（64。`#dv-modal-title` `#dv-modal-body`、`[data-modal=cancel|ok]`）
  - include: `partials/topbar.html`（55、`topbar_crumb`/`topbar_title` を set）、`docverify/_global.html` `_review.html` `_r3.html` `_process.html` `_accuracy.html`（59-63）
- 依存: CSS は tokens / app / app-components / css/components / user-menu / ta2 は `?v={{ _ver }}`、docverify / -r3 / -r4 は `?v={{ dv_ver }}`（8-16）。JS は user-menu → docverify-core → -global → -review → -r2 → -r3 → -r4 → -r5 の順（68-75）、最後に `DV.start()`（76）。ルートは `web/routes/doc_verify.py:66-67` が `dv_ver`（静的ファイル mtime の最大）を渡す。
- 注意:
  - 読み込み順が重要: core が `window.DV` を作り、以降が `DV.on(view, fn)` で登録する。順序を変えると global 等は `if (!DV) return` で黙って何もしない。
  - `docverify-ai.js` はこの担当範囲外で、対応する CSS/partial は無い（R2 は review 系の拡張と思われる。未確認）。
  - `accuracy` に対応する DOM は `_accuracy.html`。`followup`/`screen` 等は `_review.html` の共通殻のみ。
  - トップバーの `topbar_title` は静的に「ホーム」、実際は core の `show()` が `#topbar-title` を書き換える。
  - favicon は `/static/favicon.svg` 直書き（7）。

### `templates/docverify/_global.html`（70 行）
- 役割: 全体・管理画面 6 つ（home / mine / reviews / findings / checklists / metrics / settings の 7 セクション）の静的 DOM。描画は docverify-global.js。
- 主な要素（data-view 単位）:
  - `data-view="home"`（1）: ヒーロー `.dash-hero`、`#dvgHeroStart`（5「検証を始める」）、ステップ表示 1-5（6、静的）、`#dvgHomeReload`（10）、`#dvgHomeNew`（10）、`#dvgHomeStats`（12、`.stat-cards`、aria-live）、`#dvgHomeQuality`（14）、`#dvgHomeTodo`（15）、`#dvgHomeTable`（17、`.dv-tscroll`）
  - `data-view="mine"`（20）: `#dvgMine`（23）
  - `data-view="reviews"`（26）: フォーム `#dvgNewForm`（28、name / file / checklist_id（`#dvgNewChecklist`）/ due）、一覧 `#dvgReviews`（36）
  - `data-view="findings"`（39）: フィルタ `#dvgFStatus`（状態: open/accepted/rejected/fixed）、`#dvgFSeverity`（critical/major/minor）、`#dvgFReview`、結果 `#dvgFindings`（47）
  - `data-view="checklists"`（50）: `#dvgClSel`、`#dvgClNew`、`#dvgClEdit`
  - `data-view="metrics"`（60）: `#dvgMetrics`
  - `data-view="settings"`（66）: `#dvgSettings`
- 依存: docverify-global.js、docverify.css（.dvg-* / .dv-grid2 / .dv-tscroll）、app 共通の `.dash-hero` `.stat-cards` `.btn-primary` `.btn-outline-sm`。
- 注意:
  - findings の状態 option（open/accepted/rejected/fixed）は JS 側 STATUS（candidate/adopted/rejected/fixed/verified）と値体系が違う。API 側でどう解釈されるか未確認（要確認）。
  - 全 section が `hidden` 初期で表示は core の `show()` 任せ。
  - 「（任意）」類の文言は無し。ヒーロー文言・ステップは静的ハードコード。

### `templates/docverify/_r3.html`（47 行）
- 役割: `data-view="setcheck"`（集合の検査・追跡、SCR-06-07）の静的 DOM。描画は docverify-r3.js（担当外）。
- 主な要素: section `.dv-view.dvr-view.dv3`（2）、「網羅性: 未検証」固定表示 `.dv3-coverage` ×3（4, 22, 32）、`#dv3Msg`（5）、文書登録 `#dv3Upload` `#dv3Kind` `#dv3File`（accept .txt .md .docx .xlsx .pdf）`#dv3Hidden`（checked）`#dv3UploadBtn` `#dv3Docs`（9-15）、集合検査 `#dv3Run` `#dv3Pairs`（19-23）、追跡表 `#dv3Format` `#dv3Xlsx` `#dv3TraceSummary` `#dv3Trace`（27-34）、規則・語彙 `#dv3Rules` `#dv3RuleList` `#dv3Forbidden` `#dv3Allowed` `#dv3Synonyms`（37-45）
- 依存: docverify-r3.js、docverify-r3.css。
- 注意: setcheck は core の REVIEW_VIEWS に含まれ、レビュー未選択だと `reviews` に飛ぶ。「規則と組織の語彙」はテナント共通（レビュー単位ではない）。`_review.html` の共通殻（steps / dvr-msg / dvr-body）を使わず独自構造。

### `templates/docverify/_process.html`（84 行）
- 役割: R4 の部品（種別・工程・工数・指標・回答取り込み・判定）を `#dvR4Parts`（hidden）に置く。docverify-process.js が各画面（plan / triage / questions / gate）の本体へ差し込む（r4.js:221 で存在確認）。
- 主な要素（`data-r4-view` ごと）:
  - `plan`（`#dvR4-plan`）: `#dvR4Legacy`、`#dvR4Type` `#dvR4Required`、参加者表 `#dvR4People` `#dvR4AddPerson`、チェック `#dvR4Independent` `#dvR4ExitVerified` `#dvR4ExitDone`、プリセット `#dvR4Preset` `#dvR4PresetUse/Copy/Delete`、`#dvR4PlanSave`、工程 `#dvR4Entry`（errors）`#dvR4Advance` `#dvR4Log`、工数 `#dvR4Prep` `#dvR4Meeting` `#dvR4Pages` `#dvR4Kind`（比較しない/basic/detail）`#dvR4EffortSave`、指標 `#dvR4Metrics`
  - `triage`（`#dvR4-triage`）: `#dvR4Hidden`（個別レビュー中の非表示注記）`#dvR4Kinds`
  - `questions`（`#dvR4-questions`）: `#dvR4AnsFile`（.csv .xlsx）`#dvR4AnsImport` `#dvR4AnsResult`
  - `gate`（`#dvR4-gate`）: `#dvR4Stale` `#dvR4Verdict` `#dvR4Approver` `#dvR4Decided` `#dvR4VerdictSave` `#dvR4Unchecked` `#dvR4Record` `#dvR4RecordXlsx` `#dvR4AuditVerify` `#dvR4AuditResult` `#dvR4Standards` `#dvR4StandardsNote`
- 依存: docverify-process.js、docverify-process.css（.dv-r4-*）。
- 注意: `#dvR4Parts` 自体は hidden のため、JS が移動しないと表示されない。承認者・日時は自由入力 text（日時の書式は placeholder のみ）。`dvR4Kind` の option 値は HTML ハードコード。

### `templates/docverify/_accuracy.html`（10 行）
- 役割: `data-view="accuracy"`（精度）の静的 DOM。描画は docverify-accuracy.js。
- 主な要素: `#dvAccReload`（4）、`#dvAccMeta`（6、初期「読み込み中…」）、`#dvAccTable`（7）、`#dvAccMethods`（8）、`#dvAccLimits`（9）
- 依存: docverify-accuracy.js。
- 注意: ID 接頭辞が `dvAcc*`（他は dvg / dv3 / dvR4）で不統一。section は `dvr-view` ではなく `dv-view` のみ。レビュー未選択でも開ける管理画面（REVIEW_VIEWS 外）。

### `templates/docverify/_review.html`（9 行）
- 役割: レビュー内 7 画面（plan / read / triage / questions / followup / screen / gate）の共通殻を Jinja の for で生成する。
- 主な要素: `section.dv-view.dvr-view[data-view=key]`（3）、`[data-dvr-steps]`（4）、`.dvr-title` と `[data-dvr-headright]`（5）、`[data-dvr-msg]`（6、aria-live）、`[data-dvr-body]`（7）。title は for のタプルで固定（計画 / 文書を読む / 指摘の検討 / 質問票 / 修正版の確認 / 実画面との照合 / 判定と記録）。
- 依存: docverify-review.js が data-dvr-* を埋める。
- 注意: ID を持たず data 属性で選ぶ。画面を足すときはタプルと core の REVIEW_VIEWS・TITLES・doc_verify.html のサイドバーの 3 箇所を揃える必要あり。

### `static/css/docverify.css`（249 行）
- 役割: System 06 全体の基本スタイル（レイアウト・部品・全体/管理画面・レビュー内画面・R1 追加分）。
- 主な要素:
  - レイアウト: `.dv-content`(3)、`.dv-grp` `.dv-grp-review` `.dv-n(.red)`(4-8)、`.dv-banner` `.dv-toast`(10-11)、`.dv-steps`(13-18)
  - 旧系統部品: `.dv-card` `.dv-table` `.dv-chip` `.dv-sev-*` `.dv-btn*` `.dv-field` `.dv-tabs`(20-50)
  - 全体・管理: `.dvg-*`(53-64)、`[data-view]:not(.dvr-view)` に `.card/.f/.chip/.c-crit/.b/.tabs/.dv-t/.dv-panel` を再定義(140-176)
  - レビュー内: `.dvr-*`(67-94)、`.dvr-view` 配下の `.steps/.wrap/.card/.doc/.f/.b/.tabs/.dv-t/.dv-panel`(97-138)
  - R1: `.dv-grid2` `.dv-qrow` `.dv-score*` `.dv-stage` `.dv-sev` `.stat-card.is-warn` `.dv-todo` `.dv-link` `.dv-tscroll` `.dv-ellipsis` `.dvr-docband` `.dv-unread` `.dv-scoreband` `.dv-mini` `.dv-unverified`(185-225)、`.dv-modal*`(226-236)、`[aria-busy]` `[data-key-open]`(237-239)、パンくず省略(241-247)
- 依存: tokens.css の変数、ta2.css（`html,body{overflow:hidden}`、汎用 `.steps` を 98 行で打ち消し）、app.css の `.stat-card`。
- 注意:
  - 重複・衝突: `.dvg-card` `.dvg-num` `.dvg-bar` `.dvg-bl` `.dvg-bn` が 56-63 と 167-171 で二重定義（後勝ち）。`.dv-steps`(13) と `.dvr-view .steps`(97) も同内容。
  - `.dv-card > h3`(21) と `.dv-grid2 > .dv-card > h3`(188) と `[data-view]:not(.dvr-view) h3`(174) が競合しやすい。
  - ハードコード色: #111827(11) `#047857`(17,101) #FFF7ED #FDE68A #D97706(113-114) `#fff`(126,42)。トークン化されていない。
  - 旧系統（`.dv-table` `.dv-btn*` `.dv-chip` `.dv-card-body` `.dv-split` `.dv-empty` `.dv-loading`）は担当 JS・HTML からは未使用。他の JS で使うか未確認（未結線の可能性）。
  - `.dv-tscroll` は `overflow-x:hidden`＋`table-layout:fixed`＋`white-space:nowrap` で長文は省略される（全文は title）。

### `static/css/docverify-r3.css`（35 行）
- 役割: 集合の検査・追跡（setcheck）専用スタイル。
- 主な要素: `.dv3`(2、縦並び＋ overflow:auto)、`.dv3-card/h/row/actions/coverage/msg/upload/rules/field/check/fieldset`、表 `.dv3-table`(14-17)、`.dv3-gap` `.dv3-loc` `.dv3-kind(-contradiction)` `.dv3-decs/.dv3-dec(.is-on)`(20-25)、`.dv3-empty/sub/warn/notes/stats/stat/cands`(26-35)
- 依存: tokens.css のみ。
- 注意: `.dv3-coverage` は固定の黄系バッジ。`.dv3-table` は docverify.css の `.dv-t` とは別系統（表の見た目が二系統）。JS 側（docverify-r3.js）が使う class と一致するか未確認。

### `static/css/docverify-process.css`（24 行）
- 役割: R4 部品（`.dv-r4*`）のスタイル。
- 主な要素: `.dv-r4`(2)、`-title` `-row` `-hint` `-warn` `-muted` `-result` `-table` `-fieldset` `-errors`(:empty は非表示) `-list` `-grid` `-metrics` `-dl`(dt/dd) と `:focus-visible`(24)
- 依存: tokens.css のみ。
- 注意: `.dv-r4-dl` と `-grid label` は HTML 側に出現せず、JS が動的生成する前提。font-size を px 直書き（13px / 12px / 14px）でトークン不使用。

### `static/js/docverify-core.js`（240 行）
- 役割: `window.DV` の土台。画面切替・API ラッパー・通知・モーダル・共通ユーティリティ。
- 主な要素:
  - 定数: `REVIEW_VIEWS`(5、レビュー必須の 8 画面)、`TITLES`(6-10、全 16 view の表示名)、`NET_ERR`(11)
  - 関数: `esc`(15)、`banner`(17、`#dv-banner`)、`toast`(24、2.6 秒)、`api`(32、opts: method / form / json / body+headers / raw。失敗時 banner に data.error を出して `err.status`/`err.data` 付きで throw)、`setCounts`(60、`[data-count=candidates|adopted]`)、`renderReviewNav`(68)、`show`(77)、`openReview`(96)、`setReview`(105)、`start`(111)、`busy`(122)、`trapTab`/`modal`(143/155)、`download`(189)、`emptyFindings`(203)、`scoreText/scoreClass/scoreBar`(204-216)、`keyOpen`(219)
  - 公開 API（232-240）: `DV.api esc show toast openReview setReview start banner busy modal download emptyFindings scoreText scoreClass scoreBar keyOpen NO_SCORE state{review,summary} on(view,fn) refreshNav PHASES`
  - 保存先: `sessionStorage['dv-review']`（100、開いたレビュー ID）、URL hash（画面名）
  - 呼ぶ API: `GET /api/docverify/inspections/<iid>`（openReview）
- 動作:
  - `show(view)`: 未定義 view は home、REVIEW_VIEWS でレビュー未選択なら reviews に切替。`.dv-view` の hidden 切替、`[data-nav]` の active、`#topbar-title`、`#topbar-breadcrumb`（レビュー名付き）更新、hash を replaceState、banner を消し、登録済み handlers[view] を全て実行（例外は console.error＋banner「画面を表示できませんでした」）。
  - `start()`: nav クリックで show。sessionStorage にレビュー ID があれば `openReview(saved, hash || 'read')`（失敗時は banner を消して home 等へ）。
- 依存: `#dv-banner` `#dv-toast` `#dv-modal` `#dv-review-nav` `#dv-review-name` `#topbar-title` `#topbar-breadcrumb`（topbar partial）。
- 注意:
  - 保存済みレビューがあると起動時に必ずそのレビューを開く。hash が `home` でも `openReview(saved, 'home')` で home 表示になるが、レビューは選択状態で残る。
  - `api()` は成功時に banner を消す（他の失敗表示が消えうる）。`opts.raw` は成功時 banner を消さない。
  - `modal` は `o.html` を innerHTML に入れる。呼び出し側が esc 済みであることが前提。
  - `PHASES`（238）は global.js の `PHASE` と別定義で、`closed` の表記が違う（core は「判定と記録」、global は「完了」）。
  - 新 view の追加は TITLES と REVIEW_VIEWS の両方が必要。`accuracy` `setcheck` は TITLES にあるが `show` の handlers 登録は r3 / r5 側。

### `static/js/docverify-global.js`（320 行）
- 役割: 全体・管理 7 画面（home / mine / reviews / findings / checklists / metrics / settings）の描画と操作。IIFE（var / function 記法）。`window.DV` が無ければ即 return。
- 主な要素:
  - 定数: `SEV`(9)、`STATUS`(10)、`PHASE`(11)、`ROLE`(12)、`CK_LABEL`(45、ISO/IEC/IEEE 29148 の 8 特性)、`TODO_SCOPE`(49)、`DEFAULT_REVIEW_TYPE='informal'`(164)
  - 共通: `sevChip` `loading` `failed`（「読み込めませんでした。画面を開き直してください。」）`empty` `lbl` `load(el,path,render)` `table` `bindRows` `reviewRow` `reviewTable` `relabel`(14-46)
  - 画面ごとの描画:
    - home（`data-view="home"`）: 入口 `DV.on('home', loadHome)`(125)。`loadHome`(119)は `#dvgHomeStats` を空に、`#dvgHomeQuality` `#dvgHomeTodo` `#dvgHomeTable` を「読み込み中…」にして `GET /api/docverify/home`。成功で `renderHome`(105)。失敗時は 3 枠とも「読み込めませんでした。画面を開き直してください。」（Stats は空のまま）。`.catch` は握りつぶす。
    - home の各枠: `#dvgHomeStats`←`homeStats`(55)。カード 4 枚 `data-stat=active|critical|answers|quality`（進行中のレビュー / 未対応の重大な指摘（>0 で is-warn）/ 回答待ちの質問 / 品質スコア）。品質は未算出なら `DV.NO_SCORE`「— 文書を取り込むと表示されます。」。`#dvgHomeQuality`←`homeQuality`(64)。`n_scored`=0 なら NO_SCORE 文言、あれば特性別スコアを昇順（null は末尾）で `DV.scoreBar`。`#dvgHomeTodo`←`homeTodo`(80)。0 件は「いまやることはありません。」、あれば `next_actions` の各 `review_name` と `button.dv-link[data-review][data-view]`（クリックで `DV.openReview(id, view||'read')`）。見出し副題は `next_scope`（mine=自分の担当から / active=進行中のレビューから）。`#dvgHomeTable`←`homeTable`(100)。0 件は「進行中のレビューはありません。『＋ 新しいレビュー』から始められます。」、あれば 6 列表（文書 / 工程 / 品質スコア / 未対応（重大バッジ）/ 更新 / 操作）、行クリックで `openReview(id,'read')`、`versions>1` で「改版あり」バッジ。
    - home の応答キー: `counts{active,open_critical,awaiting_answers}`、`quality{overall,n_scored,items{label,score}}`、`next_actions[{review_id,review_name,view,label}]`、`next_scope`、`active[{review_id,document_name,review_name,phase,quality_overall,open,open_critical,versions,updated_at}]`、`mine`。
    - ボタン: `#dvgHomeReload`←`DV.busy(loadHome,'読み込み中…')`(126)。`#dv-new-review` `#dvgHeroStart` `#dvgHomeNew`←`startNew`(128、reviews へ移動し名前欄にフォーカス)(133)。
    - mine: `DV.on('mine')`(136) `#dvgMine` に `GET /api/docverify/home` の `mine` を `reviewTable`（レビュー / 役割 / 工程 / 期限）。空は「いま担当しているレビューはありません。」
    - reviews: `DV.on('reviews')`(149)。`fillChecklistSelect`(142)で `GET /api/docverify/checklists`→`#dvgNewChecklist`、`GET /api/docverify/inspections`→`#dvgReviews`（レビュー / 工程 / 期限 / 指摘 の表。空は「レビューはまだありません。上の欄から作成してください。」）。`#dvgNewForm` submit(181)→`createReview`(165): `POST /api/docverify/r4/inspections`（json name / goal / review_type 既定 informal）→checklist_id・due があれば `PATCH /api/docverify/inspections/<id>`→file があれば `POST /api/docverify/inspections/<id>/document`（FormData）→`DV.openReview(iid, ファイル有 ? 'read' : 'plan')`。busy ラベル「文書を読み取り中…」。失敗時は入力保持。
    - findings: `loadFindings`(191)。`GET /api/docverify/findings?status=&severity=&review=`→`#dvgFindings`（重大度 / 内容 / レビュー / 状態 / 指摘者）。初回のみ `#dvgFReview` に option を結果から生成(`fReviewsLoaded`)。行クリックで `openReview(review_id,'triage')`。空は「条件に合う指摘はありません。」。フィルタ 3 つの change で再読込。
    - checklists: `DV.on('checklists')`(259)。`GET /api/docverify/checklists`→`fillSel`(253)→`renderChecklist`(222)で `#dvgClEdit` にリスト名・項目 ol（`#dvgClName` `#dvgClItems` `#dvgClAdd` `#dvgClSave`）。保存は `PUT /api/docverify/checklists`（全リスト配列を JSON で置換）。`#dvgClNew` はクライアント側で `cl-<Date.now()>` を採番。
    - metrics: `DV.on('metrics')`(281)。`GET /api/docverify/metrics`→修正完了率・断片あたりの指摘・`bars()` で重大度別 / 観点別 / レビュー別。
    - settings: `DV.on('settings')`(297)。`GET /api/docverify/settings`→重大度・指摘の種別・出口基準・役割。読み取り専用。
- 依存: core の `DV.api/busy/openReview/show/toast/keyOpen/scoreBar/scoreText/NO_SCORE/on`、DOM は `_global.html`。
- 注意:
  - 保存先は API 経由のみ。localStorage は不使用。
  - home 失敗時は `#dvgHomeStats` が空のままで、エラー表示が無い（banner は core の api が出す）。
  - `mine` と `home` が同じ `/api/docverify/home` を別々に呼ぶ（キャッシュ無し）。
  - `STATUS` に `accepted` が無い。`_global.html` のフィルタは `accepted` を使うが `lbl(STATUS)` では「採用」と出ず生値表示になりうる（未検証）。
  - findings 一覧の行 `data-id` は配列 index（i）で、`list` をクロージャで参照。再描画後は古い index にならない前提。
  - metrics は API の複数形を `||` で拾う防御的実装で、実際の応答キーは未確認（`fix_rate`/`completion_rate`、`density`/`findings_per_fragment`、`by_viewpoint`/`by_checklist_item`/`by_checklist`）。
  - `createReview` は `r4/inspections` を直接使い、`goal` フォーム欄が無いため常に空。`review_type` 欄も無く常に `informal`（FR-06-140、計画画面で変更）。
  - `reviewRow` の ID は `r.id || r.review_id`（一覧とホームで応答形が違う）。
  - checklist 保存が全置換のため、同時編集で後勝ちになる。
  - `PHASE` は core の `PHASES` と重複定義。

### `static/js/docverify-review.js`（552 行）
- 役割: レビュー内の 7 画面（plan/read/triage/questions/followup/screen/gate）を描く IIFE。土台は window.DV（core）。
- 主な要素:
  - 登録: init(546) が `DV.on(view, open(view, map[view]))` を 7 画面分。DOM に `.dvr-view[data-view]` がある画面だけ（550）。DV 未定義なら 30ms 再試行。
  - 共通: open(174: reload()+settings()→renderSteps→render)、rerender(185)、renderSteps(158 工程バー)、setReview(120 DV.state.review/summary を更新)、setFinding(153)、busy(46→DV.busy)、msg/loading/failed(33-42)、part()/sect()(26-27 `[data-dvr-body|msg|steps|headright]`)。
  - 帯・表: docBand/scoreBand/qualityTable/historyTable/scopeTables(60-106)、showScoreHelp(107)、confirmClose(111)、`data-act="score-help"`。
  - renderPlan(188): #dvr-name/#dvr-goal/#dvr-due/#dvr-cl/#dvr-ec-c/#dvr-ec-w、`[data-plist]`、`[data-file]`、act=addp/delp/save/start/upload。addPRow(227)、savePlan(238)。
  - renderRead(284): `.ln[data-pid]` 文クリック→openAdd(363 `.dvr-add`)、タブ mine/all/check、`data-fa`=adopt/reject/ask、`data-ck` チェックリスト、`data-act="done"`、findingCard(267)、hl(262)。
  - renderTriage(399): `[data-t=sev|st|disp|save]`。renderQuestions(428): `data-act="ans"`。renderFollowup(448): `data-act=up`、`data-ok`/`data-ng`。renderScreen(479): `[data-dom]`、`data-act="m"`。renderGate(497): #dvr-apn/#dvr-apd、act=ap/close/report、closeReview(536)。
  - API: GET /api/docverify/inspections/{id}（base, 125）、PATCH {base}（計画・checks・approval, 255/358/524）、POST {base}/document（取込, 220/468）、POST {base}/findings（390）、POST {base}/findings/{fid}（153）、POST {base}/participants/me/done（293）、GET {base}/questions.csv|.xlsx（430 リンク）、POST {base}/answers（439）、GET /api/docverify/domains（480）、POST {base}/match（489）、GET {base}/report.xlsx（DV.download, 503）、POST {base}/close（537）、GET /api/docverify/settings（128）、GET /api/docverify/checklists（132）。
  - 状態: モジュール内 cache{settings,checklists}（初回のみ取得、以後固定）、ui{tab,selLine}。ブラウザ保存なし。
- 依存: DV.state.review/summary、DV.api/esc/busy/modal/toast/show/download/keyOpen/scoreText/scoreBar/emptyFindings/NO_SCORE。テンプレート templates/docverify/_review.html の `.dvr-view` と `data-dvr-*`。`#accuracy`（r5）へのリンク(105)。
- 注意:
  - 'use strict'(6) が CK_LABEL 宣言(5)の後ろにあり、ディレクティブとして無効（strict 化されていない）。
  - DV.api を `{method,headers,body}` 形式で呼ぶ（json()/upload()）。core は互換で受けるが r2/r3/r4 は `{json}`/`{form}` 形式で不統一。
  - 自前の PHASES(8)・setReview(120) が core の DV.PHASES/DV.setReview と重複。自前 setReview は renderReviewNav を呼ばない（名前表示等が更新されない可能性）。
  - plan/triage/questions/gate は r4.js も DV.on で同じ画面に重ねて登録（handlers は配列で全部走る。非同期は待たない）。承認欄が review.js(#dvr-apn, PATCH approval) と r4(#dvR4Approver, POST /r4/.../verdict) で二重。
  - 計画の PATCH は rev を送らない（r4 は rev 必須で 409）。同時編集で上書きされうる。
  - 文言ハードコード: 重大度 SEV、役割 ROLES、観点 DEFAULT_TYPES、出口基準の既定 max_open_warning=5(201)、viewpoint '実画面との食い違い'(482)、certainty '要確認'(282/339/429)。
  - renderRead の checkbox 変更は PATCH 後に全体再描画。findings 追加は 2 段階（POST→checklist_item を別 POST、391）で途中失敗すると項目なしで残る。
  - 'warning'/'info' を major/minor に読み替える旧値互換(23)。questions の CSV/Excel は a href 直リンク（失敗時の表示なし）。

### `static/js/docverify-ai.js`（207 行）
- 役割: R2「AI の説明」: 送信前確認→送信→採否・質問票へ送る、と設定画面の AI 送信先・監査ログ。
- 主な要素:
  - decorate(15): `[data-fa="ask"]` の親と `tr[data-fid]` の最終 td に `data-r2="explain"` ボタンを注入。MutationObserver(132) で body 全体を監視し再注入。
  - explain(115)→confirmSend(47)→send(63)→showResult(91)。previewHtml(34)、resultHtml(80)、highlight(28)。DOM id: dv-r2-words/dv-r2-wobble/dv-r2-remask/dv-r2-q/dv-r2-reject、`data-r2q`。
  - API（R2=/api/docverify/r2）: POST …/inspections/{id}/findings/{fid}/ai/preview（48）、/ai/explain（68）、/ai/decision（104）、/ai/questions（108）、POST /r2/ai/cancel（58/66）、GET|POST /r2/llm-settings（192/197）、GET /r2/audit?since&until&user&action（171/175）、GET /r2/audit.csv（178）。
  - 設定画面: DV.on('settings', renderSettings)(205)。#dvgSettings の直後に section#dv-r2-settings（#dv-r2-llm/#dv-r2-audit）を挿入。settingsHtml(135)、auditHtml(147)、rowsHtml(156)、query(163)、loadAudit(169)。ラジオ name=dv-r2-dest、#dv-r2-url/#dv-r2-model/#dv-r2-save、#dv-r2-since/until/user/act/filter/csv/rows。
  - 公開: `DV.r2 = {decorate, explain, renderSettings}`(206)。
- 依存: DV.api（`{json}`）/modal/busy/setReview/toast/show/current/state.review/banner/download/esc。review.js が描く `[data-fa="ask"][data-fid]` と triage の `tr[data-fid]` に依存。#dvgSettings（docverify-global.js 側）、#dv-modal の `[data-modal="cancel"]`(12)。
- 注意:
  - `DV` 未定義なら黙って return(6)。review.js より後に読み込む前提。
  - closeModal はキャンセルボタンを click する擬似操作。モーダル内部の DOM 構造に依存。「再反映」「質問票へ」「不採用」のたびに ok=false で resolve される経路を act 変数で区別している（読みにくい）。
  - 例外はほぼ握りつぶし（catch 空）。利用者向け文は DV.api が帯に出す前提。
  - 送信キャンセルは token を /ai/cancel へ best-effort で投げる（失敗無視）。
  - MutationObserver が body 全体の子孫変更ごとに querySelectorAll を走らせる（重い画面で負荷になりうる）。
  - タイムアウト 60 秒(65)、AI の選択肢 openai/ollama/none(136) がハードコード。renderSettings 内で保存後に自分自身を再呼び出し（監査ログも再取得）。
  - 監査ログ失敗時 DV.banner('') で帯を消してから自前メッセージ(180)。

### `static/js/docverify-r3.js`（168 行）
- 役割: R3 集合の検査画面（SCR-06-07, view=setcheck）: 文書登録・矛盾/重複候補の判断・追跡表・規則と語彙の設定。
- 主な要素:
  - 登録: `DV.on('setcheck', …)`(163)。初回のみ kinds()(158)+bind()(114)、毎回 load()(90)+loadRules()(134)。
  - 描画: render(83)→renderDocs(22)/candidateList(35, 先頭 50 件)/renderPairs(50)/pairRow(43)/renderTrace(61)。state はモジュール変数。
  - DOM id: #dv3Msg #dv3Docs #dv3Pairs #dv3Format #dv3TraceSummary #dv3Trace #dv3TraceTable #dv3Upload #dv3File #dv3Kind #dv3Hidden #dv3UploadBtn #dv3Run #dv3Xlsx #dv3Rules #dv3RuleList #dv3Forbidden #dv3Allowed #dv3Synonyms。`data-dv3-del` `data-dv3-pair` `data-dv3-dec`。
  - API（base=/api/docverify/inspections/{id}/r3）: GET {base}（92）、POST {base}/documents（form: file,kind,include_hidden, 106）、DELETE {base}/documents/{id}（122）、POST {base}/setcheck（116）、POST {base}/setcheck/{pairId}（decision, 126）、POST {base}/trace（format, 117）、GET {base}/trace.xlsx（118）、GET|PUT /api/docverify/r3/settings（136/153）。
  - 判断 DECISIONS: contradiction/duplicate/ok。固定文言 COVERAGE '網羅性: 未検証'(9)。
- 依存: DV.api（`{json}` `{form}` `{method}`）/busy/toast/download/esc/state.review。templates/docverify/_r3.html の DOM。
- 注意:
  - 各 API は成功時に全体 state を返す前提で render() に直接渡す（形が崩れると画面全体が落ちる）。
  - iid が無いと load は何もしない（メッセージも出ない）。
  - 種別 option(158)・結果ラベルがハードコード。語彙の同義語は「正規＝別名、別名」形式を行ごとに手でパース(148)、`=` 複数や空は無検証。
  - 設定保存後の文言「次に取り込む文書から使います」: 既存文書へ再適用されない。
  - 失敗時 catch は空（DV.api が帯に出す前提）。upload の catch は msg('') で消すだけ。
  - bind 済み判定 `bound` はページ生存中のみ。ボタン busy は DV.busy で二重送信防止。

### `static/js/docverify-process.js`（229 行）
- 役割: R4 レビュー種別・役割・工程の進行・工数と指標・観点プリセット・指摘の種別・回答取込・判定と記録を、_process.html の部品として既存の plan/triage/questions/gate 画面へ差し込む。
- 主な要素:
  - 登録（DOMContentLoaded 内, 220）: `#dvR4Parts` が無ければ何もしない。DV.on('plan', showPlan)、('triage', showTriage)、('questions', showQuestions=mount のみ)、('gate', showGate)。bindPlan(144)/bindOthers(191)。
  - mount(17): `#dvR4-{view}` を `.dv-view[data-view]` へ appendChild。
  - 状態: meta（初回のみ GET）、st（検査の R4 状態）、presetList、people。load(28)、send(35: 常に rev を付与、409 code=conflict で再読込して再 throw)。
  - 描画: renderPeople(48)、renderPlanFields(56)、renderFlow(69)、renderEffort(78)、showTriage(112)、showGate(126)。
  - API（P=/api/docverify/r4）: GET {P}/meta、GET {P}/inspections/{id}、GET {P}/presets、PUT …/plan、POST …/advance、PUT …/effort、POST …/preset、POST {P}/presets/{id}/copy、DELETE {P}/presets/{id}、POST …/findings/{fid}/kind、POST …/answers（form: file, rev）、POST …/verdict、GET …/record.xlsx、GET {P}/audit/verify。
  - DOM id: #dvR4Parts #dvR4People #dvR4AddPerson #dvR4Type #dvR4Legacy #dvR4Required #dvR4Independent #dvR4ExitVerified #dvR4ExitDone #dvR4Preset(+Use/Copy/Delete) #dvR4PlanSave #dvR4Entry #dvR4Advance #dvR4Log #dvR4Prep #dvR4Meeting #dvR4Pages #dvR4Kind #dvR4EffortSave #dvR4Metrics #dvR4Hidden #dvR4Kinds #dvR4AnsFile/#dvR4AnsImport/#dvR4AnsResult #dvR4Stale #dvR4Verdict #dvR4Approver #dvR4Decided #dvR4VerdictSave #dvR4Unchecked #dvR4Record #dvR4RecordXlsx #dvR4Standards #dvR4StandardsNote #dvR4AuditVerify #dvR4AuditResult。
- 依存: DV.api/esc/toast/banner/download/PHASES/state.review。templates/docverify/_process.html と `.dv-view` 4 画面。review.js が先に描く plan/triage/gate/questions の枠。
- 注意:
  - review.js と同じ 4 画面に重ねて登録。review.js 側 renderPlan が body を innerHTML で作り直しても r4 部品は host 直下に別途 mount されるので残るが、描画順・二重の保存ボタン（計画保存 PATCH と /r4/plan PUT）と承認欄の二重に注意。
  - 承認: showGate は #dvR4Approver / #dvR4Decided に値を入れない（入力欄は空のまま。保存済み承認を表示しない）。review.js 側 #dvr-apn は ap.approver を表示。
  - rev 排他: send は st.rev 必須。review.js の PATCH は rev を送らず、更新後に r4 の st は古くなる→次の保存で 409。
  - `if (!iid()) return` で未選択時は何も出さない。meta は一度取れば再取得しない。
  - showQuestions は mount のみ（回答取込のイベントは bindOthers 側）。DOMContentLoaded 前提のため、動的読込にすると動かない。
  - guard は例外握りつぶし（文言は DV.api の帯）。renderEffort の保存後は load し直さず st を使用。

### `static/js/docverify-accuracy.js`（89 行）
- 役割: R5 精度ページ（SCR-06-10, `#accuracy`）。GET /api/docverify/accuracy を 4 つの表（メタ・規則・測定方法別・限界）に描く。
- 主な要素:
  - load(70): fetch('/api/docverify/accuracy')。renderMeta(18)、renderRules(36)、renderMethods(47)、renderLimits(59)、fail(65)、table(11)、esc/v（未測定表示, 5/10）。
  - DOM id: #dvAccMeta #dvAccTable #dvAccMethods #dvAccLimits #dvAccReload。
  - イベント: DOMContentLoaded で再読込ボタン、onRoute(81) が `location.hash==='#accuracy'` で load。hashchange(87)。公開 `window.DVAccuracy={load}`。
- 依存: window.DV を使わない（独立）。精度ページのテンプレート DOM（docverify-global 側か _r5 系）。review.js(105) の `#accuracy` リンク。
- 注意:
  - DV.on を使わず hash で自前ルーティング。core の show() は `#accuracy` を TITLES に無ければ home に倒す可能性があり、画面の表示切替は別実装（global/core 側）に依存（担当外・未確認）。
  - esc を自前実装（DV.esc と重複）。fetch を直接使い、DV.api の帯表示・エラー共通処理を通らない。
  - 列名・「未測定」・閾値表示 min_precision がハードコード。table() の行セルは呼び出し側で esc 済み前提（未 esc を渡すと XSS）。
  - hash が最初から #accuracy でも DOMContentLoaded 後に 1 回 load。画面遷移のたびに再取得はしない（hashchange のみ）。

### `web/routes/doc_verify.py`（517 行）
- 役割: System 06 の R1 本体。画面 HTML、検査（インスペクション）の作成・取得・更新、文書取り込み、指摘の更新・追加、質問票の出力と回答取り込み、実画面照合、終了、報告、ホーム、全指摘、チェックリスト、設定、メトリクス。
- 共通の型: 応答は `_respond(insp, status, **extra)` が `{inspection, summary(metrics.summary), ...extra}` を返す（27〜47 行付近の `_err`・`_load`・`_respond`）。エラーは `{error: 文}`。`_load` は iid が `^[0-9a-f]{12}$` でない・store に無いとき 404。
- 権限: `@_perm.require(op)`（`web.services.docverify.perm`）。URL に iid があればその検査の参加者の役割で判定し、無ければ 403 `{error, code:"forbidden"}`。認証オフは全操作許可。付いているのは下表の「権限」列の 4 件だけ。
- 主な要素（メソッド URL → 関数（行）→ 呼ぶ service → 応答の主なキー → エラー）:
  - GET /docverify → `page`（61）→ `render_template("doc_verify.html", dv_ver=…)`。JS/CSS 10 本の更新時刻の最大値を版として渡す → HTML。
  - GET /api/docverify/inspections → `list_inspections`（70）→ `store.list_all` → `{inspections}` → 500。
  - POST /api/docverify/inspections → `create_inspection`（80）→ `store.new`・`store.save`・`settings.current_user` → `{inspection, summary}` 201。作成者を進行役（moderator）で参加者に入れる。名前空 400、保存失敗 500。権限なし。
  - GET /api/docverify/inspections/<iid> → `get_inspection`（99）→ `store.load` → `{inspection, summary}` → 404。
  - POST …/<iid>/document → `upload_document`（105）権限 import_doc → `ingest.ingest`・`checks.candidates`・`setcheck.apply_rules`/`load_settings`・`diff.compare`/`carry_findings`・`metrics.freeze_current`/`quality_brief`・`process.entry_errors`/`type_info`・`store.save` → `{inspection, summary, entry_errors?}` → ファイル未選択・IngestError 400、取り込み失敗・候補生成失敗 500、検査なし 404。2 版目以降は前版との差分で新規断片だけ再検出し、旧指摘を引き継ぐ。phase が plan のときだけ individual へ進め、R4 種別設定済みなら入口基準（FR-06-142）未達で進めない。
  - POST …/<iid>/findings/<fid> → `update_finding`（163）権限なし → `store.save`・`_perm.record("finding_update")` → `{inspection, summary}` → 状態・重大度・確度・checklist_item/disposition の不正 400、変更なし 400、指摘なし 404。status は candidate/adopted/rejected/fixed/verified、severity は critical/major/minor（`normalize_severity` 経由）、certainty は 事実/推定/要確認。
  - POST …/<iid>/findings → `add_finding`（202）権限 finding_edit → `settings.normalize_severity`/`current_user`・`_renumber` → `{inspection, summary}` 201（HUMAN 規則・status=adopted・origin=human）→ 箇所未選択・重大度・観点/文の空 400。
  - GET …/<iid>/questions.csv（234）`questions_csv` → `questions.build`/`to_csv` → text/csv 添付 → 404。
  - GET …/<iid>/questions.xlsx（245）`questions_xlsx` → `questions.to_xlsx` → xlsx 添付 → 404。
  - POST …/<iid>/answers → `import_answers`（256）権限 finding_edit → `questions.import_answers` → `{inspection, summary, applied}` → ファイルなし・UTF-8 不可・形式違い・その他の失敗もすべて 400。
  - GET /api/docverify/domains → `domains`（282）→ `match.domains` → `{domains}` → 500。
  - POST …/<iid>/match → `match_screens`（292）権限なし → `match.match(passages, domain)` → `{inspection, summary}` → domain 空・未巡回（ValueError）400、他 500。同じ観点の candidate を置換する。
  - POST …/<iid>/close → `close`（316）権限 plan_edit → `metrics.summary`・`metrics.freeze_current` → `{inspection, summary}`、終了条件未達は 409 `{error, reasons}`。status=closed にするが phase は変えない。
  - GET …/<iid>/report.xlsx → `report_xlsx`（332）→ `metrics.to_xlsx` → xlsx 添付 → 404/500。
  - GET /api/docverify/home → `home`（361）→ `home_svc.build(_all_full(), current_user())` → 下記 → 500。
  - GET /api/docverify/findings → `all_findings`（372）クエリ status/severity/review → `_all_full` → `{findings:[指摘 + review_id, review_name]}` → 500。
  - PATCH …/<iid> → `patch_inspection`（400）権限なし → `store.save`・`settings.load_checklists`・`_perm.record("approval")` → `{inspection, summary}` → 各項目不正 400、変更なし 400。受け付けるキー: name, goal, due(YYYY-MM-DD), participants(役割 5 種), checklist_id, checks(dict→bool), exit_criteria(非負整数をマージ), phase(6 種), approval({approver, decided_at}、doc_version は文書から付与)。
  - POST …/<iid>/participants/me/done → `participant_done`（466）→ `current_user` → `{inspection, summary}` → 参加者外 403。
  - GET/PUT /api/docverify/checklists → `checklists`（482）→ `settings.load_checklists`/`save_checklists` → `{checklists}` → ValueError 400、他 500。
  - GET/PUT /api/docverify/settings → `settings_api`（496）→ `settings.load_settings`/`save_settings` → `{settings}` → 400/500。
  - GET /api/docverify/metrics → `metrics_api`（510）→ `metrics.overall(_all_full())` → `{metrics}` → 500。
- GET /api/docverify/home の応答キー（`home.build(reviews, me)`、`web/services/docverify/home.py`）:
  - `me`: `settings.current_user()`。
  - `mine`: 全検査の participants のうち name==me の行。各 `{review_id, review_name, role, done, phase, due}`（終了済みも含む。`_mine`）。
  - `active`: 進行中（phase!="closed" かつ status!="closed"）の検査ごとに `{review_id, review_name, phase, due, findings(件数), quality_overall(summary.quality.overall), open(adopted 件数), open_critical(summary.open_critical), candidates(candidate 件数), updated_at(updated_at か created_at), versions(件数), document_name}`。
  - `counts`: `{mine(mine のうち done でない件数), active(active の件数), open_findings(全検査の adopted 件数。終了済みも含む), open_critical(その critical 件数), awaiting_answers(進行中で certainty=要確認・未却下・answer 空の件数)}`。
  - `quality`: 進行中検査の `metrics.summary().quality` の平均。`{overall, items:{キー:{score, label}}, n_reviews, n_scored}`（四捨五入、対象 0 件は None）。
  - `next_actions`: 最大 5 件 `{review_id, review_name, kind, view, label}`。kind は critical/candidates/answers/my_review/no_document/ready_to_close（優先順、同順位は期限の早い順）。
  - `next_scope`: "mine"（自分が参加者の進行中検査がある）か "active"（無ければ進行中すべて）。
- 依存: `flask`（Blueprint 名 `doc_verify`）、`web.services.docverify` の `perm`（先頭 import）、関数内遅延 import で `store`・`ingest`・`checks`・`diff`・`setcheck`・`metrics`・`process`・`questions`・`match`・`settings`・`home`。登録は `web/__init__.py`（33 行 import、145 行 `register_blueprint(doc_verify.bp)`）。
- 注意:
  - 権限が付くのは import_doc・finding_edit（add/answers）・plan_edit（close）のみ。update_finding・patch_inspection・participant_done・match_screens・checklists/settings の PUT・質問票/報告の出力・metrics は権限なし。認証ありでも誰でも status を verified にでき、patch で phase・approval・participants を書き換えられる（R4 の plan_edit/approve/mark_verified/tenant_settings を迂回できる）。
  - PATCH phase="closed" は終了条件（exit_ok）を検査せず status=closed にする。close（409 で止める）と R4 advance(closed) と挙動が食い違う。
  - R1 の更新系は rev（楽観ロック）を扱わない。R4 は rev 必須（`perm.check_rev`）。R1 経由の保存で rev が進むかは `store.save` 側（担当外）。
  - 重複: 作成（R1 POST /inspections と R4 POST /r4/inspections）、回答取り込み（R1 CSV のみ・R4 は CSV/xlsx）、承認（PATCH approval と R4 verdict）、検証（`_valid_participants`・`_ROLES` と R4 `_participants`・`process.ROLES`）。
  - `page()` の JS/CSS 一覧がハードコード。全て無いと `max()` が ValueError。テンプレート側の読み込みと二重管理。
  - `home`・`all_findings`・`metrics_api` は全検査を毎回フル読み込み（`_all_full`）。件数が増えると遅い。
  - upload_document にファイルサイズ上限が無い（R4 は 20MB）。`ingest` 失敗以外の例外は 500。
  - 指摘 ID の採番が `_renumber`（ここ）、R2 `_question_findings`、R3 `_detect` の 3 通り。
  - 状態名・重大度・工程・役割の文字列定数が R1・R4・perm に分散。
  - `update_finding` の severity は `normalize_severity` 経由（旧語彙の吸収）。add_finding も同じ。

### `web/routes/doc_verify_ai.py`（331 行）
- 役割: R2。AI（LLM）の説明を人の承諾つきで 1 件の指摘に付ける。送信前確認、送信、取りやめ、採否、未決定事項の質問票への送り込み、送信先設定、監査ログ。LLM が失敗しても規則の検出・判定には影響しない（FR-06-115）。
- 共通の型: 応答は `_respond`（R1 と同じ `{inspection, summary, ...}`）。検査 ID の形式不正・不在は 404（M_INSP）。メッセージ定数 `M_*` を先頭に集約。
- 権限: R1 の `perm.require` は使わず、モジュール内の `is_admin()`（`web.tenancy.current_auth_user()` が None か role=="admin"。認証オフは全員 admin 扱い）と `is_approver()`（全検査の participants に自分が approver で入っているか）で判定。
- 主な要素:
  - GET /api/docverify/r2/llm-settings → `get_settings`（102）→ `llm_settings.load`/`disclosures` → `{settings, destination{key, model, …開示内容}, disclosures, can_edit}`。権限なし（誰でも読める）。
  - POST /api/docverify/r2/llm-settings → `post_settings`（109）→ `llm_settings.save`、`audit.append("llm_settings")` → 同形（can_edit=true）→ 非管理者 403、ValueError/ConnectionError 400、OSError 500。
  - POST …/r2/inspections/<iid>/findings/<fid>/ai/preview → `preview`（130）→ `llm_assist.source_text`/`word_ranges`/`mask`/`sends_for`、同意トークン発行（`secrets.token_urlsafe`、600 秒、メモリ上の `_consents`）→ `{destination, masked, sends, with_wobble, consent_token, expires_in, timeout_sec}` → 検査/指摘なし 404、送信先 none 409、マスク指定不正 400。送信はしない。
  - POST …/ai/explain → `explain`（187）→ トークンを 1 回消費（検査・指摘・送信先・利用者の一致を確認）、`llm_settings.client_for`、`llm_assist.explain`（別 Event でキャンセル可）、`audit.append("llm_send"/"llm_send_failed")`、`store.save` → `{inspection, summary, ai}` → 送信先 none 409、トークン不正/期限切れ 400、キー未設定 503、AI 失敗 503、タイムアウト 504、取りやめ 409。待機後は検査を読み直して該当指摘の `ai` だけ差し替える。
  - POST /api/docverify/r2/ai/cancel → `cancel`（221）→ `{cancelled: bool}`。権限なし。トークンを知っていれば取りやめられる。
  - POST …/ai/decision → `decision`（232）→ 採用なら disposition に「AI 提案を採用: …」を入れ、`ai` に adopted/decided_by/decided_at を付ける。`audit.append("ai_adopt"/"ai_reject")` → `{inspection, summary}` → 指摘なし 404、`ai` なし 400、decision が adopt/reject 以外 400。
  - POST …/ai/questions → `to_questions`（272）→ 選んだ未決定事項を origin=ai・certainty=要確認・status=candidate の指摘として追加（`AI_QUESTION`）。`audit.append("ai_question")` → `{inspection, summary, added:[ID]}` 201 → indexes 不正/空 400、指摘なし/`ai` なし 404/400。送信済み（`sent_questions`）は再追加しない。
  - GET /api/docverify/r2/audit → `audit_list`（310）→ `audit.query`/`read_all`/`describe`/`ACTIONS` → `{rows[+action_label, summary], users, actions}` → admin でも approver でもなければ 403、期間形式/操作名不正 400。
  - GET /api/docverify/r2/audit.csv → `audit_csv`（323）→ `audit.to_csv` → text/csv 添付 → 403/400。
- 依存: `web.services.docverify` の `audit`・`llm_assist`・`llm_settings`（先頭 import）、遅延で `store`・`metrics`・`settings`。`web.tenancy.current_auth_user`。Blueprint 名 `doc_verify_ai`、登録は `web/__init__.py` 36 行 import・148 行。
- 注意:
  - 同意トークン（`_consents`）と実行中イベント（`_running`）はプロセス内メモリ。複数ワーカーや再起動で preview→explain が 400（M_CONSENT）になる。
  - 監査が 2 系統: R2 は `audit.append`（`audit` モジュール）、R1・R4 は `perm.record`（ハッシュ連鎖ログ）。閲覧は R2 の /r2/audit と R4 の /r4/audit/verify に分かれる。
  - 権限判定が R1・R4 の `perm`（`g.auth_user`・`auth_enabled()`）と別実装（`web.tenancy.current_auth_user`）。preview/explain/decision/to_questions は検査の役割を見ない（finding_edit 相当の確認なし）。
  - R2 は `rev`（楽観ロック）を使わない。explain は読み直し後に保存するが排他ロックなしで、競合の余地がある。
  - explain は同期で最大 60 秒ブロック（NFR 上のタイムアウト 504）。
  - `is_approver` は全検査を走査。`_IID`・`_load`・`_respond`・`_err` が R1・R3・R4 と重複。
  - 指摘 ID 採番が R1 `_renumber` と別に `_question_findings` にある。

### `web/routes/doc_verify_setcheck.py`（208 行）
- 役割: R3。複数文書（要件・設計・テスト）の登録・削除、集合の検査（文書間の突き合わせ）、候補の組の判定、追跡表（trace）とその形式設定、規則と語彙の設定。既存 Blueprint は変えない。
- 共通の型: 状態応答は `_state(insp)`（53 行）= `{documents（passages を除く）, kinds[{id,label}], set_check(setcheck.view), trace(trace.build), formats, trace_format, findings(件数。一覧ではない), coverage}`。更新系は `_save_respond`（保存して `_state` を返す。保存失敗 500）。
- 権限: なし（`perm.require`・rev 照合・管理者判定のいずれも使わない）。
- 主な要素:
  - GET /api/docverify/inspections/<iid>/r3 → `get_state`（74）→ 上記 `_state` → 404。
  - POST …/<iid>/r3/documents → `add_document`（92）multipart: kind（trace.KIND_LABEL にあるもの）, file, include_hidden（"0" 以外は真）→ `ingest_r3.ingest_r3`、`_detect`（`checks.candidates`・`setcheck.apply_rules`/`term_variants`/`missing_attributes`）→ `_state` 201。文書 ID は `D`+uuid 先頭 8 桁、`passages`・`candidates` を検査 JSON の `documents` に保存 → 種別/ファイル未選択・IngestError 400、他 500。
  - DELETE …/<iid>/r3/documents/<did> → `remove_document`（120）→ `_state` → ID 形式不正・不在 404。
  - POST …/<iid>/r3/setcheck → `run_setcheck`（131）→ `setcheck.run(docs, 前回結果)`。対象は単一文書（id "main"）＋R3 文書 → `_state` → 対象なし 400、失敗 500。
  - POST …/<iid>/r3/setcheck/<pid> → `decide_pair`（148）body.decision → `setcheck.decide(insp, pid, decision, current_user)` → `_state` → ValueError 400、組なし（KeyError）404。
  - POST …/<iid>/r3/trace → `set_trace_format`（165）body.format → `trace.pattern` で検証して `trace_format` を保存 → `_state` → 400。
  - GET …/<iid>/r3/trace.xlsx → `trace_xlsx`（179）→ `trace.to_xlsx(trace.build(...))` → xlsx 添付 → 404/500。
  - GET/PUT /api/docverify/r3/settings → `r3_settings`（193）→ `setcheck.load_settings`/`save_settings`（規則と語彙）→ 設定そのもの（`{settings:…}` で包まない）→ PUT の ValueError 400、他 500。
- 依存: `flask`、遅延 import で `web.services.docverify` の `store`・`ingest`・`ingest_r3`・`trace`・`setcheck`・`checks`、`settings.current_user`。Blueprint 名 `doc_verify_setcheck`、登録は `web/__init__.py` 35 行 import・147 行。
- 注意:
  - 権限・楽観ロックなし。認証ありでも誰でも文書の追加削除・設定 PUT ができる（R4 の tenant_settings を迂回）。複数人が同時に保存すると後勝ち。
  - 応答形が R1/R2 と違う（`{inspection, summary}` でなく `_state`）。`findings` キーは件数で、一覧ではない。r3/settings は包みなしで返し、R1 の settings（`{settings}`）と形が違う。
  - R3 文書の `candidates` は文書内に保持され、検査の `findings` に自動では入らない。`_detect` は ID を `F1…` から振り、R1 の `_renumber` と別系統（衝突の可能性）。
  - 文書の全断片を検査 JSON に保存するため、サイズが増える。アップロードにサイズ上限なし（`file.read()` 全量）。
  - 削除 API は ID 形式を検査してから存在確認。set_trace_format は検証のみで権限なし。

### `web/routes/doc_verify_process.py`（382 行）
- 役割: R4。レビューの工程（plan→…→closed）、権限、楽観ロック、種別、工数、判定と承認欄、質問票の回答取り込み（CSV/xlsx）、チェックリストのプリセット、参考範囲、レビュー記録の出力、監査の連鎖検証。
- 共通の型:
  - 定数 `_P="/api/docverify/r4"`。例外 `_Stop(message, status, **extra)` を投げ、デコレータ `_guard` が `{error, ...extra}` に変換（`_err`）。
  - 状態応答は `view(insp)`（63 行）= `{rev, phase, type, participants, r4, exit_options, next_phase, entry_errors, phase_log, effort, indicators, approval, unchecked, findings(個別レビューの独立適用後), record}`。
  - 更新系は `_mutate(iid, op, change, rev=None)`（80 行）: 読み込み → `perm.check(op, insp)`（403 `code:"forbidden"`）→ `perm.locked(store.doc_dir(iid))` で排他 → 読み直し → `perm.check_rev`（不一致・未指定は 409 `code:"conflict", rev`）→ `change(insp)` → `perm.bump`（rev+1）→ `store.save` → `view(updated)` 200。rev は body の "rev"（`answers` だけフォームの "rev"）。
- 権限: `perm.check`（`_mutate` 内）と `@perm.require`。操作名 plan_edit・finding_edit・approve・tenant_settings・audit_view（`perm.MATRIX`）。
- 主な要素（すべて `/api/docverify/r4` 配下）:
  - GET /meta → `meta`（132）→ `process.REVIEW_TYPES/ROLES/KINDS/VERDICTS/STANDARDS/REFERENCE`、`presets.load_reference` → `{types, roles, kinds, verdicts, standards, standards_note, reference, reference_limit, reference_override}`。権限なし。
  - POST /inspections → `create`（144）→ `store.new`・`process.with_r4`・`store.save` → `{id, ...view}` 201 → 名前空・種別不正 400。権限なし。作成者は、種別が作成者を必須にするなら author、他は moderator で参加者に入る。rev 初期 0。
  - GET /inspections/<iid> → `get_state`（166）→ `view` → 404。権限なし。
  - PUT /inspections/<iid>/plan → `save_plan`（172）権限 plan_edit → `process.plan_errors`・`with_r4` → `view` → 計画の誤り 400 `{errors}`、権限 403、rev 409。body: review_type, participants, exit_options（require_all_verified・require_all_individual_done）, independent。
  - POST /inspections/<iid>/advance → `advance`（192）権限 plan_edit → `process.next_phase`/`entry_errors`/`advance`、closed へは `metrics.summary` の exit_ok も要求 → `view` → 未許可の工程 400、入口基準未達 409 `{errors}`。
  - PUT /inspections/<iid>/effort → `save_effort`（212）権限 plan_edit → `process.effort_errors` → `view` → 400。body: prep, meeting_minutes, pages, doc_kind(basic/detail)。
  - POST /inspections/<iid>/findings/<fid>/kind → `set_kind`（231）権限 finding_edit → `perm.record("finding_kind")` → `view` → 種別不正 400、指摘なし 404。
  - POST /inspections/<iid>/verdict → `set_verdict`（246）権限 approve → `perm.record("approval")`、`with_r4(approval=…, verdict=…)` → `view` → 判定不正・承認者/日時空 400。人が入れた値だけ保存し AI は埋めない（D-3）。
  - POST /inspections/<iid>/answers → `import_answers`（267）権限 finding_edit、multipart file（CSV/xlsx、20MB まで）と form rev → `process.answer_rows_xlsx`/`answer_rows_csv`/`apply_answers`/`skipped_message` → `{...view, applied, skipped, message}` → ファイルなし・大きすぎ・読めない 400。
  - POST /inspections/<iid>/preset → `use_preset`（299）権限 plan_edit → `presets.get` → `view` → 不在 404。
  - GET /inspections/<iid>/record.xlsx → `record_xlsx`（310）→ `process.record_xlsx` → xlsx 添付 → 404/500。権限なし。
  - GET /presets → `list_presets`（323）→ `{presets}`。権限なし。
  - POST /presets/<pid>/copy → `copy_preset`（333）権限 tenant_settings → `presets.duplicate` → `{preset}` 201 → ID 不正/不在 404。
  - PUT|DELETE /presets/<pid> → `edit_preset`（345）権限 tenant_settings → `presets.update`/`delete(pid, _in_use)` → PUT は `{preset}`、DELETE は `{presets}` → 不在 404、使用中などの PermissionError 409、検証 400。
  - GET|PUT /reference → `reference`（365）→ PUT は `perm.check("tenant_settings")` 後に `presets.save_reference` → `{reference, override, limit}` → PUT 非管理者 403、検証 400。GET は権限なし。
  - GET /audit/verify → `audit_verify`（379）権限 audit_view → `perm.verify_log()` → その戻り値 → 403。
- 依存: `web.services.docverify` の `perm`・`presets`・`process`（先頭 import）、遅延で `store`・`metrics`・`settings.load_checklists`。Blueprint 名 `doc_verify_process`、登録は `web/__init__.py` 37 行 import・149 行。
- 注意:
  - R1 の同名機能（作成・回答取り込み・承認・検査の取得）と並存する。画面がどちらを呼ぶかで権限・rev の扱いが変わる（R1 は権限・rev なし）。
  - 更新系は rev 必須。未指定は 409（メッセージは M_NO_REV だが code は "conflict"）。フロントが rev を持ち回れていないと全更新が 409。
  - `perm.record`（監査追記）は `change` 内で保存前に実行される。保存が失敗しても記録は残る（set_kind・set_verdict）。
  - `create`・`get_state`・`meta`・`list_presets`・`record_xlsx`・`reference` の GET は権限なし。`_in_use` は全検査を走査。
  - `M_MAX_BYTES` は数値なのに `M_` 接頭辞（メッセージ定数と紛らわしい）。`view` は公開名（他モジュールから使われているかは未確認）。`_guard` の後ろに `@perm.require` が来る順序（`@bp.route` → `@perm.require` → `@_guard`）に依存。
  - `perm._context()`（プライベート関数）を直接呼ぶ。テストは差し替え前提（perm 側の docstring）。

### `web/routes/doc_verify_accuracy.py`（25 行）
- 役割: R5。精度ページ用 API。規則別の適合率・再現率・n・測定日・限界（未測定は「未測定」）。
- 主な要素: GET /api/docverify/accuracy → `accuracy`（16）→ `accuracy.page()` → その戻り値（キーは担当外 `web/services/docverify/accuracy.py`）→ ValueError は `{error: 例外文}` 500、その他は固定文 `{error}` 500。権限なし。
- 依存: `web.services.docverify.accuracy`（遅延 import）。Blueprint 名 `doc_verify_accuracy`、登録は `web/__init__.py` 34 行 import・146 行。測定は `scripts/docverify_eval.py`（docstring 記載）。
- 注意: ValueError の文言をそのまま利用者に返す（実装語が出る恐れ）。権限なし（認証ありでも誰でも読める）。測定の実行 API は無い（スクリプトのみ）。

### `web/services/docverify/__init__.py`（0 行）
- 役割: パッケージ宣言のみ（空ファイル）
- 主な要素: なし
- 依存: なし
- 注意: 空のため再エクスポートは無く、各モジュールは `web.services.docverify.<module>` で個別に import する

### `web/services/docverify/accuracy.py`（140 行）
- 役割: 精度ページの表示データ整形（FR-06-170/172/173/174）と、適合率が低い規則の既定無効リストの算出。測定そのものはしない
- 主な要素:
  - 定数: `RESULT_PATH`（リポジトリ直下 quality/docverify_eval/result.json, L14）、`MIN_PRECISION=0.7`（L15）、`UNMEASURED="未測定"`、`LABELS`（rule→日本語名, L18）、`MEMBERS={"AMBIGUOUS":("RD.AMBIGUOUS","REQ.AMBIGUOUS_TERM")}`（評価単位→checks の rule ID, L28）、`NOT_YET`（SET.DUPLICATE/SET.CONFLICT, 評価セット無し, L30）、`METHOD_LABELS`（injected/authored/real, L34）、`MSG_NONE`/`MSG_BROKEN`
  - `load(path=None) -> dict|None`（L39）: 無ければ None、JSON 破損・`rules` が dict でなければ ValueError(MSG_BROKEN)
  - `fmt(v) -> str`（L54）: None は「未測定」、他は小数 3 桁
  - `_status(r) -> (enabled, reason)`（L58）: precision None は有効（n_predicted==0 かつ n>0 は専用理由）、`< 0.7` は無効
  - `_cell` / `_row` / `_unmeasured_row`（L69/77/92）: 規則 1 行分（precision, recall, n, n_gold, n_predicted, enabled_by_default, reason, by_method, previous, delta）
  - `page(path=None) -> dict`（L102）: 画面用 dict。キー measured, message, measured_on, rules_version, dataset{name,language,n,license,annotators}, kappa, scope, methods, rules, previous_measured_on, limits, min_precision。記録が無ければ全規則を「未測定」行にして返す
  - `disabled_rules(path=None) -> frozenset[str]`（L128）: `_status` が無効の規則を MEMBERS で展開して返す。記録なし・破損は空集合
  - 読む保存先: quality/docverify_eval/result.json（scripts/docverify_eval.py が書く。keys: rules, by_method, previous, delta, dataset, measured_on, rules_version, scope, limits）
- 依存: 標準ライブラリのみ（json, logging, pathlib）。環境変数なし
- 注意: `page()` は壊れた記録で ValueError を投げるが `disabled_rules()` は握りつぶして空を返す（非対称）。LABELS/MEMBERS は scripts/docverify_eval.py の RULES と手で同期が必要。`parents[3]` 依存でファイル移動に弱い

### `web/services/docverify/audit.py`（96 行）
- 役割: テナント別の監査ログ（追記・絞り込み・件数・CSV 出力。NFR-06-04/20/25）
- 主な要素:
  - `ACTIONS`（L18）: llm_send, llm_send_failed, ai_adopt, ai_reject, ai_question, llm_settings → 日本語名。`HEADER`（日時,利用者,操作,対象,内容）
  - `append(action, user, target, detail=None) -> dict`（L35）: ACTIONS 外は ValueError。行 {at(UTC ISO 秒), user, action, target, detail} を JSONL 追記（`threading.Lock` で直列化）
  - `read_all() -> list[dict]`（L48）: 全行。壊れた行は読み飛ばす
  - `query(since="", until="", user="", action="") -> list[dict]`（L61）: 日付は YYYY-MM-DD の文字列比較で両端含む、新しい順
  - `count(action) -> int`（L74）、`describe(r) -> str`（L78: detail の provider/model/chars/masked/outcome/destination/question を `k=v` で連結）、`to_csv(rows) -> str`（L89: 先頭に BOM、CSV インジェクション対策 `_safe`）
  - 保存先: `scoped_output_dir(config.DATA_DIR)/docverify/_audit.jsonl`（1 テナント 1 ファイル、追記のみ）
- 依存: `web.config`（DATA_DIR）、`web.tenancy.scoped_output_dir`
- 注意: 保持期間の自動削除なし（要確認-5）。ロックはプロセス内のみ（複数プロセスでは保証なし）。`read_all` は毎回全読みで、`count`/`query` も全走査。`_safe` は先頭が `= + - @ タブ CR` のとき `'` を前置

### `web/services/docverify/checks.py`（157 行）
- 役割: 取り込んだ断片から自動の指摘候補を作る（曖昧語・未決定・列挙・絶対表現・and/or・数値なし量・複数要求）。ISO/IEC/IEEE 29148 の品質特性を付与
- 主な要素:
  - `candidates(passages: list[dict]) -> list[dict]`（L142）: 唯一の公開関数。各指摘 {id:"F<n>", rule, severity, checklist_item, viewpoint, message, location, passage_id, quote(先頭80字), certainty, status:"candidate", answer:None, origin:"auto"}
  - 規則 ID: RD.AMBIGUOUS（reverse_doc の `find_ambiguous`）、REQ.AMBIGUOUS_TERM（`_EXTRA` 約 30 語、語ごとの境界正規表現）、REQ.INCOMPLETE（`_TBD`）、REQ.OPEN_ENDED、REQ.UNIVERSAL、REQ.AND_OR、REQ.MEASURABILITY、REQ.MULTIPLE_REQUIREMENTS
  - 重大度: 文に `_CRITICAL`（安全・停止・異常 等）を含めば曖昧/未決定/数値なしは critical、他は major。OPEN_ENDED/UNIVERSAL/AND_OR/MULTIPLE は minor。certainty は曖昧・未決定が「要確認」、他は「推定」
  - 内部: `_sentences`（。！？と改行で分割）、`_is_noise`（目次・8 字未満・句点等で終わらない見出し/表セルを除外）、`_is_req`（要求文判定。曖昧語・TBD 以外の規則は要求文のみ）、`_check_sentence`、`_check_passage`
  - 重複排除キー: (passage_id, rule（曖昧系は "A" に統合）, message+quote)
- 依存: `web.vendor.reverse_doc.ambiguity.find_ambiguous`、`accuracy.disabled_rules`（関数内 import）
- 注意: `candidates()` 呼び出しごとに result.json を読む。適合率 0.7 未満の規則は出力から除外（FR-06-170）。ID は除外・重複排除後の連番なので規則を有効/無効にすると F 番号が変わる。`_MULTI`/`_REQ_CORE` の条件は `or`/`and` の優先順に依存（L128: `A or (B and C)`）。正規表現は日本語専用でハードコード

### `web/services/docverify/diff.py`（57 行）
- 役割: 版の差分。断片を正規化本文で対応付け、追加・削除・変更を出し、旧指摘を新版へ引き継ぐ
- 主な要素:
  - `_norm(text)`（L9）: NFKC・空白除去・小文字化
  - `compare(old_passages, new_passages) -> {"added","removed","changed"}`（L17）: 正規化一致しない断片を removed/added とし、removed 各々に最も近い added（difflib ratio > 0.6、1 対 1）を `changed [{old,new}]` として対にする。各要素は `{id,text,location}`
  - `carry_findings(old_findings, old_passages, new_passages) -> list[dict]`（L42）: 旧断片と同文の新断片があれば passage_id と location を付け替え。同文が無く旧断片が存在し status が adopted なら status を "fixed" にする。他の状態（候補・不採用）は passage_id を変えず残す
- 依存: 標準ライブラリのみ
- 注意: 同文の断片が複数あると dict の後勝ちで最後の断片に紐づく。同文が消えた候補/不採用の指摘は旧 passage_id のまま残る（孤立しうる）。`compare` は O(removed×added) の総当たり。`paired_old` の算出（L34）は old id の重複があると誤って除外しうる

### `web/services/docverify/home.py`（131 行）
- 役割: ホーム（SCR-06-01）の集計。契約は WS2D-DD-006 6 章・BD-006 6 章。入力を変更せず新しい dict/list を返す
- 主な要素: `build(reviews: list[dict], me: str) -> dict`（L118。GET /api/docverify/home の応答）。返す値の全項目:
  - `me`: 引数の利用者名そのまま
  - `mine`: 全レビュー（終了含む）から、participants に `name==me` がある行 `{review_id, review_name, role, done(bool), phase, due}`
  - `active`: 進行中レビュー（`phase!="closed"` かつ `status!="closed"`）ごとの行 `{review_id, review_name, phase, due, findings(指摘総数), quality_overall(metrics.summary の quality.overall), open(status=="adopted" の件数), open_critical(summary.open_critical, 既定0), candidates(status=="candidate" の件数), updated_at(updated_at、無ければ created_at), versions(versions の長さ), document_name(document.name)}`
  - `counts.mine`: `mine` のうち done でない件数
  - `counts.active`: 進行中レビュー数
  - `counts.open_findings`: 全レビュー（終了含む）の adopted 指摘の総数（候補は数えない）
  - `counts.open_critical`: 上記 adopted のうち severity=="critical" の件数
  - `counts.awaiting_answers`: 進行中レビューの `awaiting_answers` 合計（certainty=="要確認" かつ status!="rejected" かつ answer が空白のみ/空の指摘数。終了レビューは 0）
  - `quality`: `average_quality(summaries)`（L70）= `{overall: 各レビュー quality.overall の平均（None除外・四捨五入 int(x+0.5)・対象0件は None）, items: {項目キー: {score: 平均, label: 最初に見つかった label、無ければ metrics の項目ラベル表、さらに無ければキー}}, n_reviews: 進行中数, n_scored: overall が非 None の数}`
  - `next_actions`: `next_actions(reviews, me)`（L107）の最大 5 件 `{review_id, review_name, kind, view, label}`。対象は自分が参加者の進行中レビュー（無ければ進行中すべて）。レビューごとに生成: critical（open_critical>0 → view triage, 「重大な指摘 n 件に対応する」）、candidates（候補>0 → triage）、answers（回答待ち>0 → questions）、my_review（自分が role=="reviewer" で未完了 → read）、no_document（document 無し → plan）、ready_to_close（summary.exit_ok → gate）。並び順は kind 優先度（critical0, candidates1, answers2, my_review3, no_document4, ready_to_close5）→ 期限昇順（期限なしは "9999-99-99" で最後）
  - `next_scope`: "mine" または "active"
  - 他の公開関数: `awaiting_answers(review) -> int`（L35）、`average_quality(summaries) -> dict`（L70）、`next_actions(reviews, me) -> (list, str)`（L107）
  - 定数: `_MAX_ACTIONS=5`、`_NO_DUE`、`_ACTIONS`（kind→(優先, view, label書式)）
- 依存: `web.services.docverify.metrics`（`summary(review)`、`ITEM_LABEL` または `_ITEM_LABEL`）。保存先の読み書きなし（reviews は呼び出し側が渡す）
- 注意: `counts.open_findings`/`open_critical` は終了レビューも含むが `active` の open は進行中のみ（範囲が不一致）。`_labels()` は metrics の属性名を getattr で二重に探る。`metrics.summary` を `active` と `_actions_for` で同一レビューに 2 回呼ぶ。`next_actions` の時点で `reviews` の各要素に `id` キー必須（無いと KeyError）

### `web/services/docverify/ingest.py`（138 行）
- 役割: 文書の取り込み。サイズ・形式・zip 爆弾・XML 外部参照・PDF ページ数の検査をして、断片（passage）と文書メタを返す
- 主な要素:
  - 定数: `MAX_BYTES=20MB`、`MAX_ZIP_TOTAL=100MB`、`MAX_ZIP_ENTRIES=2000`、`MAX_PDF_PAGES=500`、`ALLOWED=(.txt,.md,.docx,.xlsx,.pdf)`
  - `IngestError(Exception)`: 利用者向けの文（次の行動つき）
  - `ingest(filename, data: bytes, work_dir) -> (document, passages)`（L103）: `work_dir/source<suffix>` に書き出し、検査後に読む。passages は `{id:"P<n>", text, location}`。document は `{name, format, passages(件数), version:1, unread: unread.scan(path, suffix)}`
  - `unlock_pdf(path) -> bool`（L23）: 暗号化 PDF を空パスワードで復号し同じパスへ書き戻す。パスワード必要なら IngestError
  - `has_xml_declarations(path) -> bool`（L60）: zip 内 .xml/.rels に DOCTYPE/ENTITY があれば True（XXE 対策）
  - 内部: `_check_zip`、`_check_pdf_pages`、`_pdf_passages`（pdfminer で 1 ページずつ。行を連結し「。」で文分割。location は「N頁 M文目」）
  - 保存先: work_dir/source.<ext>（呼び出し側が指定する作業ディレクトリ）。docx/xlsx/txt/md は `readers.read_document`、location は `p.locator.label()`
- 依存: `web.services.docverify.unread`、`web.vendor.reverse_doc.docs_ingest.readers`、pypdf、pdfminer（PDF）、標準 zipfile。環境変数なし
- 注意: PDF が pypdf でなく pdfminer なのは日本語 CID フォントの文字化け回避（2026-10-06）。`import re` が `import zipfile` と離れて並ぶだけで害は無い。PDF 暗号解除は元ファイルを上書きする。`_pdf_passages` はあらゆる例外を「読み取れませんでした」にまとめる。上限値はハードコード。`has_xml_declarations` は各 xml を全量メモリ読み（上限 100MB 内）

### `web/services/docverify/ingest_r3.py`（129 行）
- 役割: R3 の取り込み拡張（FR-06-016〜018）。`ingest.ingest` を包み、表の行断片化・非表示の印・暗号化 Office 判別を足す。ingest.py は変更しない
- 主な要素:
  - `ingest_r3(filename, data, work_dir) -> (document, passages)`（L108）: 暗号化 Office は IngestError(ENCRYPTED)。通常の ingest 後、xlsx は全面再構成、docx は見出し付きの表を行単位断片に置換。document は `{...ingest の document, passages(再計算), tables:[{sheet, headers, location, passage_id}], hidden_passages(hidden==True の数)}`。断片は `{id, text, location, hidden}`
  - `is_encrypted_office(data, suffix) -> bool`（L17）: docx/xlsx が OLE ヘッダ（D0CF11E0A1B11AE1）なら暗号化
  - `_is_header(values)`: 非空 2 個以上かつすべて 30 字以下の文字列
  - `_row_text(headers, values)`: `見出し: 値／...`
  - `_sheet_hidden(ws)` / `_xlsx_sheet(ws, start)` / `_xlsx(path)`: openpyxl（data_only=True）。1 行目が見出しなら行ごとに 1 断片（table 記録を追加）、そうでなければセルごと。非表示シート/行/列のセルは hidden=True
  - `_docx_tables(path)`: python-docx。先頭行が見出しの表を行断片に。置換した表セルの文を `cells` で返し、元断片から除外
  - `_renumber(passages)`: P1.. を振り直す
  - 読む保存先: work_dir/source.<ext>
- 依存: `web.services.docverify.ingest`、openpyxl、python-docx（関数内 import）、logging
- 注意: 表・非表示の読み取り失敗は例外を握りつぶして warning ログ後に通常断片で続行（tables=[]）。xlsx は `_renumber(new) or passages` なので全セル空のときだけ元断片。docx は表セルと完全一致する本文断片も落とすので同文の本文段落も消える。表の `passage_id` は xlsx は `P{start+1}`（再採番前の仮値を使う点に注意）、docx は最初の断片 ID に補完。`data_only=True` で数式セルのキャッシュ値が無ければ空

### `web/services/docverify/llm_assist.py`（249 行）
- 役割: AI の説明（R2）。送信前の伏せ字、説明・書き換え案・質問の生成、解釈の揺れ判定、時間切れ/キャンセル
- 主な要素:
  - 定数: `TIMEOUT_SEC=60.0`（NFR-06-11 暫定）、`POLL_SEC=0.1`、`SIMILARITY=0.8`（FR-06-116 暫定）、`WOBBLE_RUNS=3`、`KINDS`/`LABELS`（email, phone, postal, url_query, api_key, my_number, card, ip, manual）、`_P`（種別→正規表現）、`_ORDER`（重なり時の優先順）、`EXPLAIN_SCHEMA`/`INTERPRET_SCHEMA`
  - 例外: `AssistError(RuntimeError)` ← `AssistTimeout` / `AssistCancelled`
  - `LLMClient` Protocol: `name`, `model`, `request(prompt, schema_name, schema, timeout_sec) -> dict`
  - 伏せ字: `find(text, extra=None) -> list[{kind,start,end}]`（L87。manual を先に確保し、他は重ならないものだけ）、`mask(text, extra=None) -> {text, spans(伏せ字後の位置), counts}`（L124。置換は `［メール］` 形式）、`word_ranges(text, words) -> list[[s,e]]`（L112）、`luhn(digits)`、`sha256(text)`
  - `source_text(insp, finding) -> str`（L145）: 規則/候補/引用/断片全文の送信元テキスト（`insp["passages"]` を参照）
  - `explain(client, masked, *, with_wobble=False, timeout=None, cancel=None) -> dict`（L229）: `{label:"AI の提案", provider, model, explanation(3文まで), rewrite, open_questions(最大3), generated_at, input_sha256, adopted:None, wobble}`。説明と書き換えが両方空なら AssistError("empty")。with_wobble なら解釈を 3 回取り `judge_wobble`
  - `judge_wobble(list[str]) -> {interpretations, max_similarity, split}`（L221。どの組も 0.8 未満で split）、`similarity`/`normalize`（NFKC・記号除去）、`three_sentences`、`sends_for(with_wobble) -> 1 or 4`
  - `run_with_timeout(fn, timeout, cancel=None)`（L178）: 別スレッド + 0.1 秒ポーリング
  - 保存先: なし（状態を持たない。保存は呼び出し側）
- 依存: 標準ライブラリのみ。LLM 呼び出しは注入された `LLMClient`（本物は `llm_settings.client_for` が生成、テストはスタブ）
- 注意: `_call` は AssistError 以外のあらゆる例外を `AssistError(クラス名)` に縮退。タイムアウト/キャンセルでも走行中のスレッドは止まらない（`shutdown(wait=False)` のみ、HTTP は続く）。`api_key` 正規表現末尾の `[A-Za-z0-9]{32,}` は長い英数字を広く伏せる（過検知しうる）。`my_number` は 12 桁を無条件に伏せ字化、`card` は Luhn 通過のみ。`_clean_extra` は重なる範囲を黙って捨て、不正範囲は ValueError。ウォブル有効時は送信が 4 回（`sends_for`）で、監査/課金の回数計上に使う

### `web/services/docverify/llm_settings.py`（170 行）
- 役割: AI 送信先の設定（使わない/OpenAI/Ollama）の保存・読込、Ollama 接続先の検証、送信先の説明文、LLM クライアント生成
- 主な要素:
  - 定数: `DESTINATIONS=("none","openai","ollama")`、`DEFAULT={destination:"none", openai_model:"gpt-4o-mini", ollama_url:"http://127.0.0.1:11434", ollama_model:"qwen2.5:3b"}`、`_PRIVATE`（127/8, 10/8, 172.16/12, 192.168/16）、`_LINK_LOCAL`、`ALLOWED_TEXT`/`OLLAMA_DOWN`/`NOT_ADMIN` の文言、`DISCLOSURES`（送信先別の name/location/training/retention/source/retrieved）
  - `load() -> dict`（L68）: DEFAULT に保存値を重ね、destination が不正なら "none"
  - `save(body, probe=None) -> dict`（L124）: destination 不正は ValueError。ollama は model（空・100 字超は ValueError）と URL を検証し、`probe or check_ollama` が False なら `ConnectionError(OLLAMA_DOWN)`。openai は openai_model（先頭100字）だけ更新。`_llm_settings.json` に原子的に書く（tempfile + os.replace）
  - `disclosures() -> dict`（L73）: 既定の説明文を `_llm_disclosures.json` で上書き（override に source と retrieved が両方あるときのみ、既存キーだけ反映）
  - `validate_ollama_url(url) -> str`（L93）: http/https のみ、認証情報付き不可、host は localhost か私設 IPv4 のみ、リンクローカルと自プロセスのポート（8765・環境変数 WEBSPEC2DOC_PORT・PORT）は不可。戻り値は `scheme://netloc`
  - `check_ollama(url, timeout=3.0) -> bool`: `{url}/api/tags` へ GET
  - `OpenAICompatClient(name, model, base_url, api_key)`: `.request(...)` が `llm.openai_client.request_structured_json`（無ければ `src.llm.openai_client`）を `purpose="docverify_explain"` で呼ぶ
  - `client_for(cfg)`（L158）: ollama → `OpenAICompatClient("ollama", model, f"{url}/v1", "local")`、openai → キーがあれば `https://api.openai.com/v1` 向け、無ければ None、none → None
  - 保存先: `scoped_output_dir(config.DATA_DIR)/docverify/_llm_settings.json` と `_llm_disclosures.json`（任意）
- 依存: `web.config`、`web.tenancy.scoped_output_dir`、`urllib.request`、`llm.openai_client`（既存）。環境変数: `WEBSPEC2DOC_LLM_API_KEY`、`OPENAI_API_KEY`（この順）、`WEBSPEC2DOC_PORT`、`PORT`
- 注意: 管理者権限の確認はここに無い（`NOT_ADMIN` は文言のみで、判定は route 側）。`_read` は JSON 破損で例外（握りつぶさない）。SSRF 対策は IP リテラルと localhost のみ許可し DNS 名は不可。`client_for` は保存済み URL を再検証するので不正値は ValueError。OpenAI キーは環境変数のみ（テナント別ではない）。`DISCLOSURES` の取得日 2026-10-15 は手書きで陳腐化する

### `web/services/docverify/match.py`（64 行）
- 役割: 文書の「」内の語を、System 01 の巡回結果（report.json）の画面文言と突き合わせ、見つからない語を指摘候補にする。
- 主な要素: `_norm(text)`（NFKC・空白除去・小文字化, L15）／`domains()` -> list[str]（L23: 出力ベース直下で report.json を持つサブディレクトリ名）／`_labels(report)` -> set[str]（L30: screens の buttons・headings・forms.fields の label/name/placeholder/element_id）／`match(passages, domain)` -> list[dict]（L46）。出力 finding は rule=`SCREEN.MISMATCH`, severity=warning, certainty=推定, status=candidate, origin=auto。`_QUOTED` は「」内 1〜40 字。読む先: `scoped_output_dir(OUTPUT_DIR)/<domain>/report.json`（読み取りのみ）。
- 依存: `web.config.OUTPUT_DIR`、`web.tenancy.scoped_output_dir`。
- 注意: 未巡回ドメインは ValueError(利用者向け文)。完全一致のみで部分一致・同義語なし。`_labels` の buttons は `b.get("text") or b.get("label") if isinstance(b, dict) else b` で、演算子優先順位により dict 以外は b 自体を渡す（意図通りだが読みにくい）。finding に checklist_item・id は付かない（呼び出し側で採番）。

### `web/services/docverify/metrics.py`（239 行）
- 役割: 終了判定の集計、29148 特性別の品質スコア、版履歴、検査範囲の説明、指摘一覧/集計の Excel 出力。
- 主な要素: `summary(insp)` -> dict（L10: by_status/by_severity/quality/density/open_critical/open_major/open_warning(互換)/exit_ok/reasons/history/unread_lines/scope）／`quality(insp)`（L50: 特性8種 `_ITEMS` ごとに 未解決(candidate,adopted)指摘のある断片を除いた割合を 0〜100。overall は全指摘）／`half_up`／`quality_brief(insp, final)`／`freeze_current(insp)`（最後の版に final 品質を記録）／`history(insp)`／`unread_lines(insp)`／`scope(insp)`（checked/unchecked 2 群）／`overall(inspections)`（レビュー横断の件数・密度・修正完了率）／`to_xlsx(insp)`（シート: 指摘一覧・集計・検査した範囲）／`_safe`（= + - @ 始まりに ' を付ける式インジェクション対策）。定数 `ITEM_LABEL`（L104）, `QUALITY_NOTE`, `_M04/_M13/_M20…`（定型文）。exit_ok は「文書あり・候補未検討 0・open critical ≤ max_open_critical・open major ≤ max_open_major」。保存先: なし（純計算＋バイト列）。
- 依存: openpyxl（遅延 import）、`settings.normalize_severity`、`unread.lines`（遅延）。insp の `exit_criteria`, `versions[].quality`, `document.unread`, `participants[].done`, `checks`, `checklist_id`, `phase/status`。
- 注意: `_OPEN={"adopted"}` のみ未対応扱い（fixed は未対応に数えない）。`ITEM_LABEL` はモジュール下部定義だが関数内参照のため動作する。`summary` の `open_warning` は v1 画面互換で削除不可。品質スコアに「singular」(8特性目)を含むが presets の REQ_ITEMS は 7 項目（singular なし）。スコアは網羅性を示さない旨を `QUALITY_NOTE` に固定。`phase=="closed"` と `status=="closed"` の両方を終了扱い。

### `web/services/docverify/perm.py`（182 行）
- 役割: 役割×操作の権限判定、版番号による楽観ロック、ハッシュ連鎖の追記専用操作記録（監査ログ）。
- 主な要素: `MATRIX`（L18: 操作 -> 許可役割集合。plan_edit, import_doc, finding_edit, mark_fixed, mark_verified, approve, delete_review, tenant_settings, audit_view, tenant_purge）／`OP_LABEL`／`ROLE_NAME`／`Conflict`（例外）／`_context()` -> (利用者名, 管理者か, 認証有効か)（テストで差し替え）／`roles_of(insp, user, is_admin)`／`can(op, roles, auth_on=True)`（認証オフは全許可）／`denied_message(op)`／`check(op, insp=None)` -> 文|None／`require(op)`（Flask デコレータ。kwargs の `iid` で検査を load して判定、無ければ insp=None、不許可は 403 `{error, code:"forbidden"}`）／`rev_of`／`check_rev(insp, client_rev, required=True)`／`bump(insp)`／`locked(path)`（`<dir>/.r4.lock` に fcntl.flock 排他）／`record(op, target, detail, actor)`（追記）／`verify_log()`（連鎖検算）。保存先: `<scoped DATA_DIR>/docverify/_r4_audit.jsonl`（1 行 JSON: seq, at, actor, op, target, detail, prev, hash=SHA-256）。ロックは対象ディレクトリの `.r4.lock`。
- 依存: `web.config.DATA_DIR`、`web.tenancy.scoped_output_dir`、flask.g（`g.auth_user`）、`web.auth.auth_enabled`、`settings.current_user`、`store.load`（require 内遅延）。環境変数は直接参照しない。
- 注意: ロールは検査の participants の name 一致で決まる（利用者名の同名衝突に弱い）。テナント管理者は `auth_user.role=="admin"`。`require` は store.load が KeyError/ValueError/OSError のとき権限判定せず本体を実行（404 判断をルートに委ねる）。fcntl のため POSIX 限定。`record` は全行を読んで末尾ハッシュを取るので件数に比例して遅くなる。`MATRIX` は暫定（コメントで要確認-17）。`.r4.lock` は監査ログ用と store.save 用で同名ファイルだが別ディレクトリ。

### `web/services/docverify/presets.py`（188 行）
- 役割: 観点プリセット（既定4種はコード定数、複製のみ保存）と、組織の指摘密度「参考範囲」の上書き保存。
- 主な要素: `BUILTIN`（req-29148, basic-design, screen-design, dod-ai。各 {id,name,doc_kind,builtin,items[{id,text}]}）／`list_presets()`／`get(pid)`（無ければ KeyError）／`duplicate(pid, name=None)`（id=`c-<hex10>`, copied_from）／`update(pid, name, items)`／`delete(pid, in_use)`／`valid_pid`（`^[a-z0-9-]{1,40}$`）／`load_reference()`／`save_reference(body)`（{"basic":{low,high},"detail":...}、None=上書き解除）／`_clean_items`（id 40 字・text 400 字に切詰め）。保存先: `<scoped DATA_DIR>/docverify/_r4_presets.json`（カスタムのリスト）、`_r4_reference.json`。書込みは tmp + os.replace（アトミック）。
- 依存: `web.config.DATA_DIR`、`web.tenancy.scoped_output_dir`。
- 注意: 既定の変更/削除は PermissionError。`save_reference` は渡されなかった kind を消す（全置換。`None` と未指定の区別なし）。排他制御なし（同時更新は後勝ち）。`_REQ_ITEMS` は settings.DEFAULT_CHECKLISTS と同内容を二重定義（片方だけ直すと乖離）。書籍付録の文面は転載せず自作という著作権上の注記あり（コメント）。使用中判定（in_use）は呼び出し側が計算して渡す。

### `web/services/docverify/process.py`（373 行）
- 役割: R4 レビュー工程管理の純粋関数群。種別・役割・入口/出口基準・工程状態機械・工数・指標・独立性・承認失効・回答取り込み・レビュー記録出力。
- 主な要素: 定数 `PHASES`=(plan, individual, triage, rework, followup, closed)、`ROLES`、`REVIEW_TYPES`（informal, walkthrough, technical, inspection, management, audit。各 required/phases/checklist/exit）、`KINDS`、`VERDICTS`(approved/conditional/rereview)、`STANDARDS`、`REFERENCE`(basic/detail の IPA 値)。関数: `r4(insp)`／`with_r4(insp, **changes)`／`type_info`（r4.review_type 未設定は legacy 扱いで全工程）／`plan_errors(review_type, participants)`（必須役割・作成者と議長/承認者の兼務禁止）／`next_phase(insp)`／`entry_errors(insp, target)`／`exit_options`／`exit_errors`／`advance(insp, target, actor, now)`（phase_log を閉じ/開く。closed で status="closed"）／`effort_errors`／`effort`／`compare(density, doc_kind, override)`／`indicators(insp, override)`／`visible_findings(insp, viewer)`／`unchecked(items, checks)`／`approval_state(insp)`／`answer_rows_csv/xlsx`・`_table`／`apply_answers(insp, rows)` -> (新insp, 件数, skipped)／`skipped_message`／`record_rows`／`record_xlsx`。状態遷移: plan -> individual -> triage -> rework -> followup -> closed（種別ごとに phases で一部省略。逆行は next_phase 側に無し）。保存先: なし（insp["r4"] に phase_log, review_type, exit_options, effort{prep,meeting_minutes}, pages, doc_kind, independent, preset_id, verdict を持つ。保存は呼び出し側が store.save）。
- 依存: openpyxl・csv・decimal（遅延 import）、`metrics._safe`（record_xlsx 内）。
- 注意: 純粋関数だが `r4()` は浅いコピーのため内部 list を直接書き換えると原本に影響。`exit_errors` の require_all_verified は status=="fixed" の残数のみ見る（adopted 未対応は metrics.summary 側）。`approval_state` のバージョン比較は doc.version > approval.doc_version。`indicators` の by_sev は severity を正規化しない（v1 の warning は集計外）。`apply_answers` は certainty を「事実」に固定。`advance` は遷移の妥当性を検査しない（entry_errors を先に呼ぶ前提）。`_ADOPTED` が metrics と重複定義。

### `web/services/docverify/questions.py`（73 行）
- 役割: 確度「要確認」の指摘から質問票を作り、CSV/Excel に出し、回答 CSV を取り込む（旧 v1 経路。xlsx 取り込みは process.answer_rows_xlsx 側）。
- 主な要素: `build(findings)` -> [{id:"Q<n>", finding_id, location, question}]（certainty=="要確認" かつ rejected 以外）／`to_csv(qs)` -> str（BOM 付き・CRLF・列: No./場所/質問/回答）／`to_xlsx(qs)` -> bytes（シート「質問票」）／`import_answers(insp, csv_text)` -> 反映件数（列 No.・回答必須、無ければ ValueError）。「No.」列には質問番号ではなく finding_id を出す。`_safe`: = + - @ 始まりに ' 付加。
- 依存: csv, io, openpyxl（遅延）。
- 注意: `import_answers` は `insp["findings"]` の dict を破壊的に更新する（引数を変更。process.apply_answers は非破壊で別実装）。取り込み時に No. の先頭 `'` を除去。不明 No. は黙って無視（skipped の報告なし）。

### `web/services/docverify/setcheck.py`（297 行）
- 役割: 複数文書集合の決定的な検査（R3）。重複候補・矛盾候補の文対、規則の有効/無効・禁止語・許容語・同義語（用語ゆれ）・要求表の属性欠落。LLM 不使用。
- 主な要素: 定数 `DUP_THRESHOLD=0.9`, `NEG_MIN_SIMILARITY=0.0`, `MAX_UNITS=1500`, `DECISIONS`, `RULES`(8規則名), `DEFAULT_R3_SETTINGS`。関数: `normalize`／`ratio(a,b)`（レーベンシュタイン比）／`units(documents)`（文分割。documents: [{id,name,passages,include_hidden}]）／`subject(norm)`／`contradiction_reason(a,b)`（同主語で同単位の数値相違、または否定/肯定の不一致）／`find_pairs(us)`（O(n²)）／`run(documents, previous)` -> set_check{pairs,decisions,units,checked_units,truncated,documents,ran_at}（前回の判断は同じ組 ID なら引継ぎ）／`view(set_check)`／`decide(insp, pair_id, decision, by)` -> 新 insp（矛盾/重複は finding を adopted で作成/更新、ok は rejected。rule=`SET.CONTRADICTION|SET.DUPLICATE`, origin=set, severity=major, checklist_item=consistent, set_pair=組ID）／`load_settings()`／`save_settings(body)`／`apply_rules(findings, passages, cfg)`（無効規則・許容語を除外、禁止語 `ORG.FORBIDDEN` を追加）／`term_variants`（`ORG.TERM_VARIANT`）／`missing_attributes(tables)`（`REQ.MISSING_ATTRIBUTE`）。組 ID = "S"+sha1(a.key|b.key)[:10]、key=`<doc_id>:<passage_id>:<k>`。保存先: `<scoped DATA_DIR>/docverify/_r3_settings.json`（disabled_rules, forbidden, allowed, synonyms[{canonical,variants}]）。検査結果自体は insp["set_check"] に呼び出し側が保存。
- 依存: hashlib, tempfile, `web.config`・`web.tenancy`（関数内遅延 import）。設計書 WS2D-DD-006 R3 章参照。
- 注意: 比較は O(n²)・MAX_UNITS=1500 超は切り捨て（scope/view に表示）。重複は短い方の長さが長い方×0.9 未満なら距離計算を省略。矛盾判定は主語（「は/が」まで2〜40字）が完全一致のペアのみ。`NEG_MIN_SIMILARITY` は 0.0 で無効（要判断コメント）。`decide` の passage_id は a が doc_id=="main" のときだけ入る（"main" ハードコード）。`decide` で rejected 後に再度矛盾へ変えても同じ finding id を再利用。ok で finding が無ければ何も作らない。`allowed` は quote への部分一致で除外（広く効く）。RULES 名は finding.rule の末尾（`.` 区切り）と照合。`save_settings` は不正入力で ValueError、書込みは tmp+replace。禁止語・同義語の判定は単純な部分一致。

### `web/services/docverify/settings.py`（117 行）
- 役割: 共通設定（指摘の種類・終了条件）と観点チェックリストの保存/読み出し、重大度の旧名読み替え、現在利用者名。
- 主な要素: `SEVERITIES`=(critical, major, minor)／`DEFAULT_SETTINGS`（types 6種, exit_criteria{max_open_critical:0,max_open_major:5}）／`DEFAULT_CHECKLISTS`（req-29148 の 7 項目）／`normalize_severity(v)`（warning->major, info->minor）／`current_user()`（flask.g.auth_user から。無ければ「ゲスト」）／`load_settings()`（+me）／`save_settings(body)`（types は非空文字列リスト、exit_criteria は 0 以上の int）／`load_checklists()`／`save_checklists(body)`。保存先: `<scoped DATA_DIR>/docverify/_settings.json`, `_checklists.json`（tmp+os.replace）。
- 依存: `web.config.DATA_DIR`、`web.tenancy.scoped_output_dir`、flask（遅延）。
- 注意: `save_settings` は exit_criteria の未知キーも通す（キー検証なし）。`isinstance(v, int)` は bool も通す。`_read` と `_write` は presets.py と同一の複製コード。チェックリスト保存は全置換で、使用中のチェックリスト削除の保護なし。`_checklists.json` が無いと既定が返る（保存後は既定が消える）。RuntimeError（アプリ文脈外）は「ゲスト」にフォールバック。

### `web/services/docverify/store.py`（138 行）
- 役割: 検査（レビュー）1 件 = 1 JSON の保存・読込・一覧、v1->v2 形式の読み替え、版番号による楽観ロック付き保存。
- 主な要素: `new(name)`（L37）／`load(iid)`（L59: upgrade 適用、無ければ KeyError）／`upgrade(insp)`（L77）／`upgrade_finding(f)`／`save(insp, expected_rev=None)`（L94: 渡すと `perm.locked` 下で現行を読み `perm.check_rev`、不一致は `perm.Conflict`、一致なら `perm.bump` で rev+1 して保存）／`_write`（updated_at 付与・tmp+os.replace）／`list_all()`（passages・findings を除いた要約、created_at 降順）／`doc_dir(iid)`。iid は `^[0-9a-f]{12}$` 以外は KeyError（パストラバーサル対策）。
- 保存形式・場所: `<scoped_output_dir(DATA_DIR)>/docverify/<iid>/inspection.json`（indent=1・UTF-8・ensure_ascii=False）。同ディレクトリに取り込み文書や `.r4.lock` も置かれる。テナントごとに分離（tenancy）。
- スキーマ（レビュー inspection）: id, name, created_at, updated_at, status(planning|reviewing|fixing|closed。v1由来), phase(plan|individual|triage|rework|followup|closed), goal, exit_criteria{max_open_critical, max_open_major}, participants[{name, role, done,...}], due, checklist_id, checks{item_id: bool}, approval{approver, decided_at, doc_version 他}, document{name, version, format, sha256, unread{images,comments,hidden_sheets,hidden_cols,shapes,scanned}...}|null, passages[{id, text, location, hidden...}], findings[], versions[{version, name, uploaded_at, quality}], diff, rev(int・楽観ロック), r4{review_type, phase_log, effort, pages, doc_kind, independent, preset_id, verdict, exit_options}, set_check{pairs, decisions, ...}。
- スキーマ（指摘 finding）: id("F<n>"), rule, severity(critical|major|minor), checklist_item, viewpoint, message, location, passage_id, quote, certainty(事実|推定|要確認|判断), status(candidate|adopted|rejected|fixed|verified), answer, origin(auto|manual|set...), raised_by, disposition, kind(missing|wrong|ambiguous|contradiction|violation), type, set_pair。質問は保存せず、`questions.build` が要確認の指摘から都度生成（質問票の No. = finding id、回答は finding.answer に格納）。
- 依存: `web.config.DATA_DIR`、`web.tenancy.scoped_output_dir`、`perm`（save 内遅延）、`settings.normalize_severity`（遅延）。
- 注意: `load` は毎回 upgrade するので、読んで保存し直すと v2 形式が書き込まれる。`upgrade` は旧 status から phase を補う（既存 phase があれば優先）。`rev` は new() に含まれず、無い場合は 0 扱い（`rev_of`）。expected_rev=None の保存は照合なし（旧経路の上書き競合に注意）。`save` は insp["id"] 必須。`list_all` は壊れた JSON（ValueError）を黙ってスキップ。ロックは同一プロセス外にも効く flock だが、expected_rev なしの `_write` はロックを取らない。

### `web/services/docverify/trace.py`（108 行）
- 役割: 文書中の ID（REQ-001 等）を決定的に抽出し、要件->設計->テストの追跡表・完全率・孤立 ID を作る。
- 主な要素: `KINDS`(requirement/design/test)、`FORMATS`(REQ, FR, NFR, UC, US, SR)、`DEFAULT_FORMAT="REQ"`、`pattern(fmt)`（`(?<![A-Za-z0-9])FMT-\d+(?![0-9])`。未知書式は ValueError）／`extract(passages, fmt)` -> [{id, location}]／`build(documents, fmt)` -> {format, columns, rows[{id, requirement, design?, test?}], complete{covered,total,rate}, orphans, unreadable, messages, coverage}（documents: [{id,name,kind,passages}]）／`to_xlsx(table)`（シート「追跡表」「完全率と孤立」）。完全率 = 登録済みの全下流種別に対応がある要件 ID の割合（四捨五入 HALF_UP）。保存先: なし。
- 依存: openpyxl（遅延）, decimal。
- 注意: ID は NFKC+大文字化して抽出。下流が未登録だと covered=0 になる（downstream 空のとき）。ID を 1 つも読めない文書は unreadable に入れて集計から外す。要件文書が無いと NO_UPSTREAM を messages に出す。xlsx の `to_xlsx` に式インジェクション対策(`_safe`)は無い（ID・位置が = 等で始まる場合）。網羅性は常に「未検証」。

### `web/services/docverify/unread.py`（212 行）
- 役割: 取り込んだ文書の「読めなかった要素」（画像・コメント・図形・非表示シート/行列）を、中身を読まずに数える。
- 主な要素: `KEYS`=(images, comments, hidden_sheets, hidden_cols, shapes)／`scan(path, suffix)` -> dict（L177: 拡張子で `_xlsx/_docx/_pdf/_md` に振分け。未対応拡張子は全 0・scanned=True。失敗は全 0・scanned=False）／`lines(u)` -> list[str]（画面・xlsx 共通の文言 M-01〜M-05）／内部 `_safe_xml`（DOCTYPE/ENTITY を含む XML は `_Unsafe`）、`_xlsx_*`、`_docx_part`、`_pdf`（pdfminer で LTImage、pypdf で /Annots のうち Link/Widget/Popup 以外をコメント扱い）、`_md`（`![..](` 数）。保存先: なし（結果は document.unread に呼び出し側が入れる）。
- 依存: zipfile, xml.etree.ElementTree.iterparse, pdfminer, pypdf（遅延 import）、`ingest.has_xml_declarations`（docx/xlsx のみ・遅延 import）。
- 注意: `except Exception` で全握りつぶしだが warning ログを出し scanned=False に。XML 宣言付き(has_xml_declarations)の docx/xlsx は数えずに scanned=False を返す。DOCTYPE/ENTITY 検出はバイト列の単純包含（XXE 対策）。xlsx の hidden_cols は列範囲の幅と hidden 行も加算。docx は本文・ヘッダ・フッタのみ走査（脚注・テキストボックス内は未対応）。PDF の画像数は pdfminer のレイアウト解析のため大きい PDF では遅い。

### `tests/test_docverify_api_integration.py`（224 行）
- 役割: R1 の結合テスト。Flask テストクライアントで API の応答だけを見る（画面側は Playwright MCP で別途）。
- 主な要素:
  - フィクスチャ client（13 行目付近 32）: config.DATA_DIR を tmp_path に差し替え、FLASK_TESTING / ALLOW_LOCAL / AUTH_MODE=off を設定し、本物の `app.app.test_client()` を使う。LLM は使わない。
  - ヘルパ: _xlsx_bytes(41)=画像・コメント付き xlsx を openpyxl+PIL で生成、_create(57)、_upload(63)、_rows(68)、_round(72)=ROUND_HALF_UP 平均。
  - test_upload_reports_unread_quality_scope（77）: 画像3・コメント2の xlsx を取り込むと、unread_lines・document.unread・quality(3 文 note)・scope(checked/unchecked) が揃い、再取得でも保持される。
  - test_second_upload_freezes_first_version（100）: 版1の指摘を全却下後に版2を取り込むと、版1 quality.final 真・版2 偽、history に2版で版2のみ current。
  - test_no_document_shows_dash_not_zero（121）: 文書なしで quality.overall None、scope は M-20/M-13、unread_lines 空。
  - 【home】test_home_average_and_items（131）: 進行中2件(片方は全却下) で GET /api/docverify/home の quality.overall・特性別が四捨五入平均、n_reviews/n_scored=2、active 2 行、counts のキー、next_scope、next_actions≦5。
  - test_report_contains_scope_sheet（157）: report.xlsx に「検査した範囲」シート、網羅性「未検証」・規則の精度「未測定」。
  - test_report_failure_is_user_readable（169）: metrics.to_xlsx を例外にすると 500 と M-41、例外名・パスが漏れない。
  - 【home】test_home_failure_is_user_readable（183）: home_mod.build を例外にすると /api/docverify/home が 500 と M-40、LEAK 正規表現に当たらない。
  - test_broken_docx_error_is_user_readable（195）: 壊れた docx は 400、エラー文にパス・例外名なし、document は None のまま。
  - 【home】test_old_json_compat（205）: updated_at/unread/quality の無い旧 JSON を書き換えて検査 API とホーム API が 200、unread_lines は M-04、history は版1のみ current、ホーム active の updated_at は created_at。
- 依存: app.app、web.config、web.services.docverify.home / metrics。ルート /api/docverify/inspections(/…/document, /findings/<id>, /report.xlsx)、/api/docverify/home。データは tmp_path 上の inspection.json。
- 注意: 画像/コメント件数や LEAK の正規表現は文言完全一致（M-04/M-13/M-20/M-40/M-41 の定数）に依存。test_old_json_compat は tmp_path.rglob で inspection.json の保存位置を探索。skip・外部依存なし。

### `tests/test_docverify_unit.py`（640 行）
- 役割: R1 の単体テスト（RD-006 受入基準・DD-006 12.1 章から導出）。checks・readers・unread・ingest・store・metrics・home を関数単位で検証。
- 主な要素:
  - 定数: M01〜M05/M20/M13/M30/M31/M33 の固定文、ZERO 辞書。ヘルパ: build_xlsx（画像/コメント/非表示/チャート/図形注入）、_inject_shapes・_rewrite_zip（zip 内 XML 書き換え）、build_docx_unread / build_docx_structure（python-docx+生 XML でコメント・SmartArt・テキストボックス・入れ子表）、_insp / _f / _v / _review / _ask / _summ（検査 dict の手組み）。LLM は不使用。
  - checks（FR-06-022）: test_incomplete_is_major_or_higher（183）／test_incomplete_applies_to_non_requirement_sentence（191）／test_open_ended_on_requirement（196）／test_open_ended_suppressed_when_ambiguous_term_already_flagged（201）／test_universal_only_on_requirement（208）／test_and_or_on_requirement（214）／test_clean_requirement_has_no_29148_rules（219）。各々 INCOMPLETE・OPEN_ENDED・UNIVERSAL・AND_OR が文を与えて出る/出ない。
  - readers: test_docx_reader_order_nested_merged_textbox_header（226）=docx の文書順・入れ子・結合セル1回・ボックス/ヘッダー/フッター／test_xlsx_reader_formula_without_cache_and_shape_text（237）=式・図形文字・結合セル／test_docx_with_xml_entity_is_rejected（255）=DOCTYPE/ENTITY で IngestError、メッセージに漏れなし。
  - unread.scan: test_scan_keys_constant（273）／test_scan_xlsx_images_and_comments（278）／test_scan_xlsx_hidden（284）／test_scan_xlsx_shapes（290）／test_scan_docx（296）／test_scan_docx_textbox_with_text_is_not_a_shape（302）／test_scan_pdf（308、pypdf で注釈・リンク生成）／test_scan_md_and_txt（326）／test_scan_broken_zip_returns_zero（336、.xlsx/.docx の parametrize）／test_scan_doctype_xml_returns_zero（343）。
  - unread.lines / metrics.unread_lines: test_lines_images_comments（356）／test_lines_all_zero_and_failed_and_hidden（361）／test_metrics_unread_lines_old_json_and_no_document（368）。
  - ingest・store: test_ingest_document_shape（376、document のキー5つ）／test_store_save_adds_updated_at_without_mutating（385、UTC・引数不変）。
  - metrics.quality: test_quality_overall_80_with_labels（420）／test_quality_no_passages_is_none（429）／test_quality_note_three_sentences（436）／test_quality_brief_shape（445）。
  - history/freeze: test_history_final_and_current（458）／test_history_old_version_without_quality（468）／test_freeze_current_marks_last_final_and_is_pure（474）。
  - scope・summary: test_scope_labels_and_limits（490、checked 7 行/unchecked 5 行のラベルと文言）／test_scope_without_document（504）／test_summary_keeps_old_keys_and_adds_new（511）。
  - to_xlsx: test_to_xlsx_scope_sheet（524、3 枚目、列幅、集計の版ごと行）／test_to_xlsx_formula_injection_escaped（540、先頭 `=` に「'」前置）。
  - 【home】test_average_quality_70（556）=80/60 の平均70・特性別60・n_reviews 2／【home】test_average_quality_rounds_half_up_and_skips_none（563）=70.5→71、None は分母外／【home】test_average_quality_none_when_unscored（569）／【home】test_awaiting_answers_counts_open_questions（580）=未回答2、closed は build で0／【home】test_next_actions_priority_limit_and_scope（598）=7件から優先順5件・期限順・scope active・ラベル文／【home】test_next_actions_mine_scope_and_my_review（618）=scope mine・my_review・view read／【home】test_build_keeps_existing_keys_and_adds_new（627）=build の mine/active/counts キーと updated_at=created_at フォールバック・next_scope mine。
- 依存: web.services.docverify の checks / home / ingest / metrics / store / unread、web.vendor.reverse_doc.docs_ingest.readers。openpyxl・python-docx・PIL・pypdf で tmp_path にデータ生成。
- 注意: 規則 ID（REQ.*、RD.AMBIGUOUS）や固定文言・列幅に厳密一致する脆い assert が多い。test_open_ended_suppressed… は集合の和で緩く判定。test_incomplete_… は件数1と severity 範囲のみ。_inline_drawing は hash() で docPr id を作る（実行ごとに変動しうるが衝突しなければ無害）。test_next_actions… は日付固定（2026-10-xx）の期限順でソートに依存。skip・環境変数なし（monkeypatch は config.DATA_DIR のみ）。

### `tests/test_docverify_ai.py`（332 行）
- 役割: R2（LLM 補助・伏せ字・送信先設定・監査ログ）の単体＋結合テスト。docstring なし、FR/NFR 番号はコメント見出しのみ。
- 主な要素:
  - Stub（24）: OpenAICompatClient.request の差し替え。(client._base, prompt, schema_name) を calls に記録し、interp/fail/delay を指定可。schema_name が docverify_interpret なら解釈文字列、他は reason/rewrite/open_questions を返す。
  - フィクスチャ env（42）: DATA_DIR を tmp_path、Flask アプリに doc_verify.bp と doc_verify_ai.bp だけ登録、g.auth_user を TEST_USER で制御、llm_settings.check_ollama を True に、OPENAI_API_KEY をダミー設定。
  - ヘルパ: _insp（保存済み検査+指摘 F1）、_use（送信先設定）、_preview / _explain（preview→consent_token→explain）。
  - 伏せ字: test_mask_recall_per_kind（100、KINDS 全種 parametrize、再現率≥0.95）／test_mask_removes_email_and_marks_span（107）／test_card_requires_luhn_and_manual_range（114）／test_wobble_split_and_not_split（122）／test_three_sentences_and_timeout_cancel（127、タイムアウト・キャンセルは time.sleep 使用）。
  - 接続先: test_ollama_url_rejected（140、6 URL）／test_ollama_url_allowed（147、5 URL）／test_disclosure_override_needs_source（153）。
  - 送信先: test_default_none_and_zero_sends（165、既定 none は 409 で送信0・監査0）／test_settings_show_location_and_training_per_destination（174）／test_ollama_down_is_not_saved（182）／test_link_local_rejected_and_loopback_saved（189）／test_only_admin_can_change_destination（197、403）。
  - 送信前確認・説明: test_preview_has_five_items_and_sends_nothing（204）／test_explain_with_ollama_only_and_state_unchanged（214、openai に送らない・メール漏れなし・状態 candidate 維持）／test_consent_token_is_single_use（229）／test_failure_degrades_and_other_ops_continue（240、503・他操作継続・監査 llm_send_failed）／test_timeout_is_user_readable（253、504）／test_wobble_flag（261、送信4回）。
  - 採否・質問票: test_adopt_records_and_keeps_original（273）／test_decision_without_ai_is_rejected（288）／test_send_one_question_adds_one_row（294）。
  - 監査: test_audit_filter_csv_and_permission（307、絞込・CSV・403）／test_audit_csv_formula_guard（323）／test_preview_extra_words_are_masked（328）。
- 依存: web.routes.doc_verify / doc_verify_ai、web.services.docverify の audit / llm_assist / llm_settings / questions / store。ルート /api/docverify/r2/…（llm-settings, findings/F1/ai/{preview,explain,decision,questions}, audit, audit.csv）。
- 注意: 本物のアプリでなく最小 Flask に Blueprint 登録（本線の結線は未確認）。timeout テストは実時間 sleep(2)/(3) を含み遅い。test_mask_recall_per_kind は assert が割合のみ。test_disclosure_override_needs_source は env を受けるが未使用。test_audit_csv_formula_guard は env 不要でグローバル DATA_DIR を使う可能性。ホーム検証なし。

### `tests/test_docverify_setcheck.py`（329 行）
- 役割: R3（集合の検査＝重複・矛盾、追跡表、取り込み拡張、規則・語彙）の単体＋結合テスト。
- 主な要素:
  - ヘルパ: _doc（断片付き文書 dict）、_xlsx（行リスト+非表示シート）、_trace_docs、_insp_with_pair。フィクスチャ client（210）: 本物の app.app を使い doc_verify_setcheck が未登録なら _got_first_request を一時退避して登録する。LLM は不使用。
  - 集合検査: test_120_near_duplicate_is_one_pair（43）／test_120_normalizes_space_width_and_punctuation（50）／test_120_different_sentences_no_pair（54）／test_121_numbers_with_same_unit_are_contradiction（59）／test_121_negation_vs_affirmation_is_contradiction（66）／test_121_different_subject_not_contradiction（72）／test_122_decide_contradiction_adds_finding（82、入力不変・F4 追加・ok で rejected）／test_122_invalid_decision_and_unknown_pair（94）／test_122_decision_carried_over_on_rerun（102）／test_123_zero_candidates_shows_coverage_unverified（110）。
  - 追跡表: test_131_132_trace_rows_rate_and_orphans（123、率 67%）／test_132_orphan_downstream_id（131）／test_134_format_picks_only_that_form（138）／test_135_document_without_ids_is_excluded_with_reason（145）／test_133_xlsx_has_same_rows（152）。
  - 取り込み拡張: test_016_table_row_is_one_passage（161）／test_017_hidden_sheet_is_marked（167）／test_018_encrypted_office_is_not_called_broken（175、OLE ヘッダの偽データ）。
  - 規則・語彙: test_026_missing_verification_column（184）／test_026_full_columns_no_candidate_and_non_requirement_table_ignored（189）／test_027_term_variant（194）／test_025_forbidden_and_allowed_words（201）。
  - 結合(API): test_130_register_two_documents_with_kinds（237）／test_130_bad_kind_and_missing_inspection（247）／test_018_api_encrypted_message（253）／test_025_disabled_rule_suppresses_candidate（259、設定 PUT で UNIVERSAL 無効化）／test_026_027_api_candidates（270）／test_017_api_hidden_excluded_from_detection（280）／test_120_123_122_api_setcheck_flow（287、空→矛盾→判定→finding 反映）／test_setcheck_without_documents_is_400（306）／test_133_134_api_trace_format_and_xlsx（311）／test_delete_document（325）。
- 依存: web.services.docverify の ingest / ingest_r3 / setcheck / trace、web.routes.doc_verify_setcheck。ルート /api/docverify/inspections/<id>/r3/{documents,setcheck,trace,trace.xlsx}、/api/docverify/r3/settings、/inspections/<id>/r3。
- 注意: client フィクスチャが Flask 内部属性 _got_first_request を書き換える（Flask 版依存で壊れやすい）。DATA_DIR は monkeypatch するが app.app はプロセス共有のため登録状態が他テストと共有。test_130_register… の `trace.complete.rate == 100` など、固定数値・固定文言に依存。docstring なし（ID はテスト名の番号のみ）。ホーム検証なし。

### `tests/test_docverify_process.py`（325 行）
- 役割: R4（レビュー種別・役割・工程・工数指標・監査ハッシュ連鎖・プリセット・楽観ロック・権限）の API 結合＋単体テスト。
- 主な要素:
  - フィクスチャ app（24）: DATA_DIR を tmp_path、AUTH_MODE=off、最小 Flask に r4route.bp のみ登録。client（34）。as_user（39）で perm._context を差し替え（名前・管理者・認証オン）。seed（43）で store.new に rev=0 と上書きを入れて保存、load（50）。fnd（60）= 指摘 dict。DOC/PS 定数。LLM 不使用。
  - FR-06-140〜144: test_create_requires_type（67）／test_inspection_requires_moderator_and_scribe（74）／test_legacy_without_type_opens（85）／test_author_cannot_be_moderator（93、兼務不可・未保存・rev 不変）／test_entry_needs_document（103）／test_exit_requires_all_verified（110）／test_phase_log_two_steps（118）。
  - 工数・指標・参考範囲: test_effort_total（129）／test_indicators_density_and_speed（135）／test_reference_low_does_not_change_verdict（144、参考範囲 0.12/0.76/0.28・detail 0.07/0.42/0.16）／test_reference_override（152）。
  - 改ざん検知: test_audit_tamper_detected（162、4行目書き換えで line 5・「改ざんの疑い」）。
  - プリセット: test_preset_select_screen（178）／test_preset_copy_keeps_original（188、組込は 409）／test_unchecked_items（199）／test_preset_in_use_cannot_delete（204）。
  - 独立個別レビュー・種別: test_independent_individual_review（214、自分の完了まで他人の指摘は見えない）／test_finding_kind_in_list_and_report（225、record.xlsx の「種別」列=欠落）。
  - 回答取り込み: test_answers_xlsx_same_as_csv（245）／test_answers_unknown_row_reported（256、スキップ行 3・5）。
  - 承認・記録: test_approval_stale_after_new_version（266）／test_record_has_all_items（277）／test_no_certification_claims（289、「認証済み」「規格に準拠」が無く「ISO/IEC 20246」「2017」が有る。templates/docverify/_process.html と static/js/docverify-process.js を読む）。
  - 楽観ロック・権限: test_optimistic_lock（304、後の更新は 409）／test_reviewer_forbidden（313、403・LEAK なし・perm.can 判定）。
- 依存: web.routes.doc_verify_process、web.services.docverify の perm / presets / process / store。ルート /api/docverify/r4/…（inspections, plan, advance, effort, reference, presets, preset, answers, verdict, record.xlsx, meta, findings/<id>/kind）。ファイル直読み: templates/docverify/_process.html、static/js/docverify-process.js。
- 注意: 最小 Flask なので本物の app の結線は検証しない（R4 wire 側で補う）。perm._context・perm._audit_path・presets.BUILTIN[0] など内部（アンダースコア）APIに依存。指標・参考範囲は固定数値。test_no_certification_claims は静的ファイル内容に依存し、文言変更で壊れる。ホーム検証なし。

### `tests/test_docverify_process_wire.py`（105 行）
- 役割: R4 を既存ルートへ結線した部分の結合テスト（本物の app.app、wire_R4 の受入基準）。
- 主な要素:
  - フィクスチャ client（24）: DATA_DIR を tmp_path、FLASK_TESTING / ALLOW_LOCAL / AUTH_MODE=off。ヘルパ _create_legacy / _create_r4 / _upload（txt 2 行）/ _audit_ops（audit ファイルの (op,target) 一覧）。LLM 不使用。
  - test_finding_triage_approval_are_recorded（59）: 取り込み済み検査で指摘追加・採否変更・承認を保存すると、監査に finding / finding_update / approval が記録され perm.verify_log() が ok（FR-06-149）。
  - test_entry_criteria_block_auto_advance_and_legacy_advances（81）: 種別 inspection で必須役割未割当のまま取り込むと phase は plan のまま・entry_errors に「割り当てられていません」、旧形式は individual へ進み entry_errors なし（FR-06-006/142）。
  - test_new_review_from_screen_has_type（96）: static/js/docverify-global.js に '/api/docverify/r4/inspections' と review_type があることを文字列確認し、informal で作成すると type_info が legacy False・参加者が author 1 人。
- 依存: app.app、web.services.docverify の perm / process。ルート /api/docverify/inspections(…/document, /findings, /findings/<id>, PATCH)、/api/docverify/r4/inspections。ファイル直読み: static/js/docverify-global.js。
- 注意: JS の存在確認は文字列一致のみ（挙動未検証）。_audit_ops は監査ファイルの保存位置（perm._audit_path）に依存。app.app が共有プロセス内で他テストの状態と重なる可能性。ホーム検証なし。

### `tests/test_docverify_accuracy.py`（177 行）
- 役割: R5（規則の精度測定スクリプト・精度ページ）の単体＋API＋テンプレート契約テスト。
- 主な要素:
  - 準備: sys.path に scripts/ を追加し docverify_eval を import。_rule / _write ヘルパ、client フィクスチャ（36）は最小 Flask に doc_verify_accuracy.bp を登録（template_folder=templates）。LLM は不使用（評価は LLM 対象外）。
  - 評価セット: test_dataset_has_80_or_more_sentences_with_valid_labels（44、80 文以上・id 一意・空集合を含む・全 RULES を網羅）／test_dataset_rejects_unknown_label（52）。
  - 測定: test_score_counts_tp_fp_fn_per_rule（60、ev.predict を差し替え。検出0件は precision None）／test_eval_is_deterministic_and_records_regression（69、2回実行で同一出力・previous/delta・規則版変更で差分）／test_cli_runs_with_venv_python（93、subprocess で scripts/docverify_eval.py を実行、timeout 120 秒）。
  - 精度ページ: test_low_precision_rule_is_disabled_with_reason（102、0.600 は既定無効・理由文）／test_three_measured_two_unmeasured（111）／test_methods_are_separate_columns（120）／test_no_result_file_shows_unmeasured（129）／test_zero_detections_not_disabled（136）。
  - API: test_api_returns_page（143、acc.RESULT_PATH を差し替え）／test_api_broken_file_returns_user_message（154、500 と acc.MSG_BROKEN）。
  - 整合: test_committed_result_matches_dataset（165、quality/docverify_eval/result.json の n と sha256 がデータセットと一致）／test_partial_has_dom_contract（171、_accuracy.html に dvAccMeta・dvAccTable・dvAccMethods・dvAccLimits・dvAccReload の id と data-view="accuracy"）。
- 依存: scripts/docverify_eval.py（ev.DEFAULT_DATASET, RULES, score, predict, main, load_dataset, _sha）、web.routes.doc_verify_accuracy、web.services.docverify.accuracy、quality/docverify_eval/result.json、templates/docverify/_accuracy.html。
- 注意: test_committed_result_matches_dataset は評価セットを編集して result.json を再生成しないと落ちる（運用上の関門）。test_cli… は subprocess・実ファイル出力で遅め。sys.executable に依存。test_eval_is_deterministic… は ev.main が実データセットを走らせる。ev._sha はプライベート関数。ホーム検証なし。

### `docs/design/docverify/home-v1.html`（120 行）
- 役割: System 06 ホーム画面の承認済み見本（HTML 案）。実 CSS を `http://127.0.0.1:8766/static/...`（tokens.css・app.css・app-components.css・css/components.css・css/user-menu.css）から読む静的モック。title「ドキュメント検証 見本」
- 主な要素（上から）:
  - サイドバー: ブランド「WebSpec2Doc / ドキュメント検証」、システム切替（「システム ドキュメント検証 切替」）、主ボタン「+ 新しいレビュー」、ナビ 3 件（ホーム[active]・レビュー一覧・指摘一覧）、グループ「管理」（観点プリセット・メトリクス・設定）。各項目にアイコン
  - トップバー: パンくず「WebSpec2Doc / ドキュメント検証」、h1「ホーム」、ユーザーメニュー（アバター「ゲ」・「ゲスト」）
  - ヒーロー（`dash-hero`）: 見出し「仕様書を検証して、指摘と質問票を作る」／副文「要件定義書・設計書を読み込み、ISO/IEC/IEEE 29148 の品質特性で曖昧さ・抜け・検証できない記述を洗い出します。」／ドロップ領域「ファイルをここへドラッグ、またはクリックして選ぶ」＋「Word・Excel・PDF・Markdown・テキスト（1 ファイル 200MB まで）」／右列に select「レビューの種類: インスペクション」、select「観点: 29148 標準（8 特性）」、主ボタン「検証を始める」／手順「1 取り込み → 2 自動検出 → 3 仕分け → 4 質問票・報告」、注記「目安: 50 頁で約 10 秒（外部への送信なし）」、ボタン「見本のレビューを見る」＋緑バッジ「取り込みなし」
  - セクション見出し「レビュー」／「進行中のレビューと、品質スコアの推移を確認できます。」／ボタン「再読み込み」「+ 新しいレビュー」
  - 統計カード 4 枚（アイコン付き）: 進行中のレビュー 4（うち自分の担当 2 件）／未対応の重大な指摘 3（終了判定を止めています。`is-warn`）／回答待ちの質問 12（仕様の持ち主に送付済み）／品質スコア（平均）78（前週から +6）
  - 2 列カード: 「特性別の品質スコア」（副題「進行中 4 件の平均（ISO/IEC/IEEE 29148）」、曖昧でない 58・検証可能 66 が橙、完全 84・単一 91・一貫 100 が青。5 特性のみ）／「次にやること」（副題「自分の担当から」。重大な指摘 2 件を仕分ける→基本設計書、回答 5 件を取り込む→要件定義書、改版を取り込んで再検査→画面設計書）
  - 表（列: 文書・工程・品質スコア・未対応・更新・操作）4 行: 基本設計書_会員登録 v1.3[改版あり]／仕分け／62／重大 2 / 9／今日、要件定義書_ポイント機能 v2.0／質問票／81／4／2日前、画面設計書_管理画面.xlsx／取り込み済み／44(赤)／重大 1 / 17／3日前、外部IF仕様書 v1.0／完了(緑)／93／0／9日前。各行に「開く」「報告」
  - 見本専用 CSS（`dv-*`: drop・hero-row・score-bar・stage・qrow・todo・grid2・card）。スコア色は 3 段階（青／is-warn／is-bad）
- 関連: `templates/doc_verify.html` の home ビュー、`templates/docverify/_global.html`、`static/css/docverify.css`、`web/services/docverify/home.py`、GET `/api/docverify/home`（契約 R1 追補）。実装後のスクリーンショットは `st-r1/02_home_normal.png`
- 注意: 見本のサイドバーは「観点プリセット」だが契約 v2 は「観点チェックリスト」（実装は後者）。見本は「自分の担当」ナビと 5 手順目「判定」が無い（実装は 5 手順・自分の担当あり）。ドロップ領域・種類/観点 select・「見本のレビューを見る」は実装スクショに写っていない。数値は全て架空の見本値。「前週から +6」の根拠となるデータ源は契約に無い

### `docs/design/docverify/home-v1.png`（画像）
- 役割: home-v1.html の描画結果（1440 幅・下部は表の見出しで切れる）
- 主な要素: HTML と同一構成。ヒーロー（ドロップ領域・2 select・青い「検証を始める」・手順・見本ボタン）、統計 4 枚（4 / 3 / 12 / 78）、特性別スコア 5 本、次にやること 3 件、表見出し（文書・工程・品質スコア・未対応・更新・操作）。重大カードのみ警告色
- 関連: home-v1.html、`st-r1/02_home_normal.png`（実装後の比較対象）
- 注意: 表本体の行は画像に写っていない（HTML を正とする）

### `docs/design/docverify/st-r1/02_home_normal.png`（画像）
- 役割: R1 実装後のホーム（通常状態）の実機スクショ
- 主な要素: サイドバー（システム切替・「+ 新しいレビュー」・グループ「ドキュメント検証」: ホーム/自分の担当/レビュー一覧/指摘一覧、「管理」: 観点チェックリスト/メトリクス/設定）。ヒーロー: 見出し・副文・「検証を始める」ボタン・手順 5 つ（取り込み→自動検出→仕分け→質問票→判定）。統計: 進行中 6／未対応の重大 0／回答待ち 3／品質スコア 88（算出できた 6 件の平均）。特性別 8 本（曖昧でない 88・検証可能 88・他 100: 完全・一貫・実現可能・必要・単一・追跡可能）。次にやること 5 件（長い名前のレビューが … で省略、「未検討の候補 2 件を仕分ける」×3、「回答待ちの質問 1 件の回答を取り込む」×2）。下に表見出し
- 関連: home-v1.html、`web/services/docverify/home.py`（next_actions・quality）、`templates/docverify/_global.html`
- 注意: 見本と比べ、ドロップ領域・select 2 つ・見本ボタン・統計アイコン・サブ文言が無い。長い名前の省略表示（テスト用データ）が確認できる。画面では特性 8 本を出し見本の 5 本と異なる

### `docs/design/docverify/st-r1/04_gate.png`（画像）
- 役割: 「判定と記録」（gate）画面の通常状態
- 主な要素: パンくず「…/基本設計書_会員登録」、工程タブ（計画✓・個別レビュー[現在]・指摘の検討・修正・修正版の確認・判定と記録）。サイドに同レビューの 7 項目（計画/文書を読む/指摘の検討/質問票/修正版の確認/実画面との照合/判定と記録）。「報告を Excel で出力」。指標 4 枚: 未対応の重大 0／未対応の主要 0／指摘密度（1 文あたり）0.00／出口基準「満たす」。総合 100、特性 8 行（必要・曖昧でない・完全・一貫・実現可能・検証可能・追跡可能・単一、全て 100・未解決 0）、「スコアの意味」リンク、版表（版 1 確定・版 2 現在、s.docx、2026-10-15、総合 100）
- 関連: `templates/docverify/_review.html`（gate）、`web/services/docverify/metrics.py`（summary・quality）
- 注意: 下端が切れており、判定の理由欄・承認欄が写っていない。版表の「スコアの意味」リンクが表に密着（余白狭い）

### `docs/design/docverify/st-r1/06_error.png`（画像）
- 役割: 取り込み失敗（エラー）状態の「計画」画面
- 主な要素: 赤い帯「文書が壊れているため読めませんでした。元のアプリで保存し直してから取り込んでください。」が画面上部と計画フォーム内の 2 か所に表示。非常に長いレビュー名（パンくず・サイドで … 省略）。計画フォーム: 名前・目的・期限・参加者と役割（ゲスト/司会、「外す」「参加者を追加」）・観点チェックリスト（選ばない）・出口基準（未対応の重大 0 件以下・主要 5 件以下）・文書（shape.xlsx xlsx・4 文・第 1 版、ファイル選択 st_bad.docx、「文書を取り込む」）、「計画を保存」「個別レビューを始める」。サイドの「文書を読む」に件数 2
- 関連: `web/services/docverify/ingest.py`（IngestError）、契約「失敗（赤い帯、API の error をそのまま）」
- 注意: 同じ文言の帯が 2 重に出る。エラー文は「次の行動を 1 行」の規約を満たしている

### `docs/design/docverify/st-r1/08_narrow_read.png`（画像）
- 役割: 狭い画面（1280×720）での「文書を読む」（read）画面
- 主な要素: 工程タブ、「あなたの役割: 司会」「自分の確認を終える」、文書の帯（shape.xlsx・xlsx・4 断片・版 1・「読めなかった要素はありません。」）、スコア帯（総合 75・8 特性の小バー・曖昧でない/検証可能が黄）、左「本文 4 文・自動候補 2 件をハイライト・文を押すと指摘を追加」（Sheet!A1 項目／B1 =CONCAT("合計","値")／A2 結合セルの説明／図形!図1-1「図形の注記: 速やかに通知する」を黄色ハイライトし F1・F2 バッジ）、右タブ「自分の指摘・候補 2／全員 2／チェックリスト」、指摘カード F1（主要・曖昧さ・「速やかに」は解釈が分かれます…・起票: 自動候補・状態: 未検討・作成者に質問中、ボタン「指摘にする」「却下」「作成者に質問」）、F2（検証可能性）
- 関連: `templates/docverify/_review.html`（read）、`static/js/docverify-review.js`、reverse_doc readers（xlsx の数式・図形の読取）
- 注意: 右カラムが下端で切れ、最下部まで届くかは画像から判断できない（契約の「最下部まで届くこと」要確認）。2 列がやや詰まる

### `docs/design/docverify/st-r1/09_keyboard_gate.png`（画像）
- 役割: キーボード操作（フォーカスリング）確認時の「判定と記録」画面。出口基準が「満たさない」の状態
- 主な要素: レビュー名「二重送信」。サイドの「判定と記録」に太い青いフォーカス枠。「文書を読む」に件数 4。指標: 未対応の重大 0／主要 0／指摘密度 0.00／出口基準「満たさない」（赤）。総合 71。特性: 曖昧でない 86（未解決 1）・完全 86（1）・検証可能 71（2）・他 100。版表: 版 1 numbers_real.xlsx・2026-10-15・71・現在。下に「判定の理由」欄（「未検討の候補が 4 件あります。「指摘にする」か「却下」を選んでください」の行が見切れ）
- 関連: `metrics.summary`（exit_ok・reasons）、契約 close の 409 `reasons`
- 注意: 重大・主要が 0 でも未検討の候補 4 件で「満たさない」になる判定。「判定の理由」が下端で切れて読めない（見切れ検査対象）。指標 0 件なのにスコアが 100 未満となる点は特性の candidate 計上による

### `docs/process/docverify-contract.md`（113 行）
- 役割: System 06 実装契約（並列担当向け）。v1 本体＋v2 追補（2026-10-06 23:30 保守者承認）＋R1 追補（WS2D-DD-006）。食い違いは後勝ち（R1 > v2 > v1）
- 主な要素:
  - 作業規則: worktree `webspec2doc-dv2`、pytest/lint/make 不実行、python -c と Flask test_client で確認（環境変数 FLASK_TESTING=1・WEBSPEC2DOC_ALLOW_LOCAL=1・WEBSPEC2DOC_AUTH_MODE=off、POST は Origin ヘッダ）、commit しない、担当外編集禁止
  - 部品: `web.vendor.reverse_doc`（readers.read_document→DocumentIR、ambiguity.ambiguous_words、編集禁止、暗号化 PDF は unlock_pdf 経由）。テナント `scoped_output_dir`・`DATA_DIR`
  - データ: `<base>/docverify/<iid>/inspection.json`（id=uuid4 hex12、status planning/reviewing/fixing/closed、goal、exit_criteria、document、passages、findings[id/rule/severity/viewpoint/message/location/passage_id/quote/certainty 事実|推定|要確認/status candidate|adopted|rejected|fixed|verified/answer/origin]、versions、diff）。iid は `^[0-9a-f]{12}$` で照合し違えば 404
  - サービス: store（new/list_all/load/save 一時ファイル＋os.replace/doc_dir）、ingest（20MB、.txt .md .docx .xlsx .pdf、zip 展開後 100MB・2,000 エントリ、PDF 500 頁、断片 0 件は IngestError）、checks（reverse_doc 曖昧語＋Doc2AI Lint 5 規則: AMBIGUOUS_TERM warning／MEASURABILITY info／MULTIPLE_REQUIREMENTS 義務表現 2 回以上 warning／MISSING_UNIT info／MISSING_SUBJECT info。追加規則 INCOMPLETE=全文対象・安全語で critical、OPEN_ENDED、UNIVERSAL、AND_OR=minor）、questions（build/to_csv BOM・式注入対策/to_xlsx/import_answers→certainty を事実に）、diff（compare/carry_findings、消えた断片の採用済みは fixed）、match（report.json との突合、「」内の語、viewpoint「実画面との食い違い」・warning・推定、未巡回は ValueError）、metrics（summary・to_xlsx 2 シート・quality: score=100×(1−未解決指摘のある断片数÷断片数)、断片 0 は null）
  - API（v1）: GET /docverify、GET/POST inspections、GET inspection、POST document、POST findings/<fid>、POST findings（人の指摘＝origin human・adopted・事実）、questions.csv/.xlsx、POST answers、GET domains、POST match、POST close（exit_ok でなければ 409 {error, reasons}）、GET report.xlsx。エラーは JSON {"error": 利用者向けの文}
  - 画面（v1）: `templates/doc_verify.html` 1 ファイル。サイドは検査一覧/検査、topbar partial 使用、タブ（指摘/質問票/版の差分/実画面との照合/終了判定）、状態（読込中・取り込み中・失敗・0 件「確認した範囲では指摘はありません。N 断片を確認しました」）、値のエスケープ、実装語・「（任意）」禁止、PC 専用・ta2.css 方式の内側スクロール、識別色 #BE185D / #FCE7F3 / #9D174D
  - v2 追補: 用語（検査→画面上「レビュー」）。メニュー: ホーム/自分の担当/レビュー一覧/指摘一覧、レビュー内 計画/文書を読む/指摘の検討/質問票/修正版の確認/実画面との照合/判定と記録、管理 観点チェックリスト/メトリクス/設定。データ追加: phase（plan|individual|triage|rework|followup|closed）、participants（role author|moderator|reviewer|approver・done）、due、checklist_id、checks、findings に checklist_item・raised_by・disposition・severity critical|major|minor（warning→major・info→minor）、approval{approver,decided_at}（人だけが埋める）。共通 `_settings.json`（severities・types・exit_criteria・me=ゲスト）・`_checklists.json`（初期値に 29148 7 特性）。API: GET home、GET findings?status&severity&review、PATCH inspections/<iid>、POST participants/me/done、GET/PUT checklists・settings、GET metrics。approve API は作らない。画面土台: `dv-view[data-view]` の partial（_global.html・_review.html）、JS docverify-core/global/review.js、`window.DV`（api/esc/show/state/openReview/toast/on）、CSS docverify.css
  - R1 追補: GET home に home.py `build(reviews, me)`。active[] に quality_overall/open/open_critical/candidates/updated_at/versions/document_name、counts.awaiting_answers、quality{overall, items{score,label}, n_reviews, n_scored}、next_actions[]（kind 優先順 critical > candidates > answers > my_review > no_document > ready_to_close、期限の早い順、最大 5）と next_scope（mine|active）、失敗は 500 の固定文。summary に history・unread_lines・scope、quality に label・note。POST document は取り込み前に metrics.freeze_current、版に quality_brief を記録、document.unread 保存。close は versions を確定。report.xlsx に「検査した範囲」シート、失敗は 500
- 関連: `web/routes/doc_verify.py`、`web/services/docverify/`（store/ingest/checks/questions/diff/match/metrics/home）、`templates/doc_verify.html`・`templates/docverify/`、`static/js/docverify-*.js`、`web/vendor/reverse_doc/`
- 注意: 作業場所が worktree `webspec2doc-dv2` の記述で古い。本文が v1→v2→R1 と積層で、v1 の severity warning/info・画面（検査一覧中心）は v2 で置換済み。checks の MISSING_UNIT/MISSING_SUBJECT は ja_v1 評価対象外。LLM 二段構成（R2 以降）・矛盾/追跡（R3/R4）は本契約に無い。ホーム見本の「観点プリセット」と契約の「観点チェックリスト」が不一致

### `quality/docverify_eval/README.md`（44 行）
- 役割: 規則ベース検出の評価セット ja_v1 の説明
- 主な要素: 測定は `venv/bin/python scripts/docverify_eval.py`、結果は result.json、表示は精度ページ SCR-06-10。ファイル: ja_v1.jsonl（id・text・labels・method・role・base）、result.json（手で書き換えない）。全文自作（E1_datasets.md「日本語: 公開データなし」に従う）。method: injected（基準文 14＋欠陥注入）／authored（基準なし）／real（未作成・精度ページで「未測定」＝FR-06-174）。ラベル方針: 人が読んで欠陥と判断するか（検出器に合わせない）。ID 表 AMBIGUOUS（約/程度つき近似値も含む。「要約」「制約」は除外）・INCOMPLETE（TBD・未定・検討中・調整中・別途定める・後日・XXX・???）・OPEN_ENDED（等・など・ほか・その他）・UNIVERSAL（常に・必ず・決して・いかなる。閉じた集合の「すべての…」は除外）・AND_OR（「および/または」）・MEASURABILITY（数値の無い時間・量・頻度）・MULTIPLE_REQUIREMENTS。注釈者 AI 1 名、2 名独立注釈・裁定・kappa は未実施（FR-06-171 未達、kappa=null）。版 ja_v1（2026-10-15）99 文（injected 65・authored 34）
- 関連: `scripts/docverify_eval.py`、`ja_v1.jsonl`、`result.json`、`web/services/docverify/checks.py`
- 注意: E1_datasets.md への参照は本担当範囲外（docs/research/docverify に A〜C のみ。E1 は別ファイル）。「人 2 名で独立注釈」が未実施の既知ギャップ

### `quality/docverify_eval/ja_v1.jsonl`（99 行）
- 役割: 評価用の日本語要求文データ
- 主な要素: 99 行・JSON Lines。キー id（JA-001〜099）・text・labels（規則 ID 配列、空は欠陥なし）・method・role・base。JA-001〜014 は基準文（base B01〜B14、labels 空、injected/base）。JA-015〜065 は基準文に欠陥注入（injected/variant、51 行）。JA-066〜099 は authored（34 行）。labels 例: JA-015「速やかに」→AMBIGUOUS＋MEASURABILITY、JA-027「TBD」→INCOMPLETE、JA-033「すべての利用者アカウント」→空、JA-044「CSV形式またはExcel形式」→空、JA-097→MULTIPLE_REQUIREMENTS＋UNIVERSAL。AMBIGUOUS の正解 37・INCOMPLETE 9・OPEN_ENDED 7・UNIVERSAL 5・AND_OR 2・MEASURABILITY 18・MULTIPLE 9（result.json の n_gold と一致）
- 関連: `scripts/docverify_eval.py`（load_dataset が labels・method・text を検証）、README.md
- 注意: 基準文 14＋バリアント 51＋自作 34＝99。MULTIPLE_REQUIREMENTS の例文は義務表現が 1 回しか無く、契約の検出条件（義務表現 2 回以上）と合わない（再現率 0 の原因）。自作文のため実文書の分布を反映しない

### `quality/docverify_eval/result.json`（252 行）
- 役割: 規則別精度の測定結果（スクリプトだけが書く）
- 主な要素: schema 1、measured_on 2026-10-15、rules_version 7be8dab6efa6、dataset ja_v1（n 99・sha256 dd858576b51b・ja・自作文・注釈者 1 名 AI・adjudicated false・kappa null）。全体の規則別（tp/fp/fn・適合率 P・再現率 R）: AMBIGUOUS gold37 pred30 tp26 fp4 fn11 P0.867 R0.703／INCOMPLETE 9/8 tp8 fp0 fn1 P1.0 R0.889／OPEN_ENDED 7/1 tp1 fn6 P1.0 R0.143／UNIVERSAL 5/6 tp5 fp1 P0.833 R1.0／AND_OR 2/2 P1.0 R1.0／MEASURABILITY 18/8 tp6 fp2 fn12 P0.75 R0.333／MULTIPLE_REQUIREMENTS 9/0 tp0 fn9 P=null R0.0。by_method: injected（n65）AMBIGUOUS P0.81 R0.63、INCOMPLETE 1.0/0.857、OPEN_ENDED 1.0/0.2、UNIVERSAL 0.75/1.0、AND_OR 1.0/1.0、MEASURABILITY 0.714/0.312、MULTIPLE null/0.0。authored（n34）AMBIGUOUS 1.0/0.9、INCOMPLETE 1.0/1.0、OPEN_ENDED null/0.0、UNIVERSAL 1.0/1.0、AND_OR 1.0/1.0、MEASURABILITY 1.0/0.5、MULTIPLE null/0.0。real=null、previous=null、delta=null。limits 4 件（自作のみ・注釈者 1 名・LLM 対象外・文単位で位置未照合）
- 関連: `scripts/docverify_eval.py`、精度ページ SCR-06-10、`web/services/docverify/checks.py`
- 注意: 検出が弱い規則は OPEN_ENDED（R0.143）・MEASURABILITY（R0.333）・MULTIPLE_REQUIREMENTS（R0、予測 0 件）。前回値が無いので回帰比較（FR-06-173）は未発動。値は 2026-10-15 時点で、その後の checks.py 変更（R2 以降）後は rules_version が変わるため再測定が必要

### `scripts/docverify_eval.py`（149 行）
- 役割: ja_v1 の各文を `checks.candidates` に通し、規則別の適合率・再現率を計算して result.json を書く（FR-06-170・171・173・174）
- 主な要素: 入力 `--dataset`（既定 quality/docverify_eval/ja_v1.jsonl）、`--out`（既定 result.json）、`--date`（既定今日）。出力: result.json、標準出力に規則ごとの `P= R= gold= pred=`。使い方: `venv/bin/python scripts/docverify_eval.py [--dataset PATH] [--out PATH] [--date YYYY-MM-DD]`。評価単位 RULES 7 個（AMBIGUOUS は RD.AMBIGUOUS と REQ.AMBIGUOUS_TERM を統合）。METHODS: injected/authored/real。文単位判定（位置は照合しない）。決定的（同じ規則・セット・日付なら同一出力）。rules_version=checks.py と vendor/reverse_doc/ambiguity.py の sha256 先頭 12 桁。規則版かデータが前回と違えば旧値を previous に移し delta（P/R の差）を書く。load_dataset は不明ラベル・method・空 text で ValueError
- 関連: `web/services/docverify/checks.py`、`web/vendor/reverse_doc/ambiguity.py`、`quality/docverify_eval/`
- 注意: 実行はゲート扱い（要求時のみ）。MISSING_UNIT・MISSING_SUBJECT 規則と LLM 指摘は測らない。LLM 指摘は対象外のため二段構成の精度は未測定

### `docs/research/docverify/00_summary.md`（67 行）
- 役割: 商用化に向けた調査（A 競合・B 研究・C 規格、2026-10-15）の統合と改訂ロードマップ
- 主な要素: 競合の共通機能（曖昧語指摘・スコア化・カスタム観点・文書間矛盾と追跡・採否は人）。空白 6 件（精度公開／実画面と仕様の突合／網羅性／指摘の根拠と再現可能な記録／日本語特化の規格準拠／規格に沿った工程・役割・メトリクス管理）。構成: 決定的ルール検出＋LLM は説明・書き換え案の二段、EARS からのずれ指摘、言い換えの揺れを曖昧さの合図に、矛盾・重複は確認候補、網羅性は常に「未検証」。ロードマップ P1〜P5（P1 29148 規則と品質スコア＝済 PR #242／P1b 取り込み修正 E3／P1c スコア画面表示／P2 LLM 二段・Ollama／P3 矛盾・追跡・完全率／P4 工程管理と IPA 指標／P5 精度測定・公開）。追加調査 E1〜E5・D〜D3: 英語評価データ PURE・ARTA、日本語注釈データは公開無し、docx の多くが未対応（テキストボックス・ヘッダー/フッター・入れ子表・xlsx 数式）、商用の非機能必須 11 項目のうち送信先開示・送信前確認・監査ログ・精度と限界の明記が未実装、P4 既定しきい値は IPA 白書（基本設計の指摘密度 中央値 0.28 件/頁・通常範囲 0.12〜0.76）、書籍付録 C の DoD 4 項目をチェックリスト初期値に
- 関連: A/B/C、`docs/process/docverify-contract.md`（R1 以降の実装）、`quality/docverify_eval/`（P5）
- 注意: 見出しが「System 01 docverify」で、現在の System 06 と呼称が異なる。ロードマップ状態は調査時点（P1b〜P5 未着手）で、git log では R2〜R5（LLM 二段・矛盾と追跡・工程管理と権限・精度測定）が実装済み。ja_v1 評価は P5 に相当。規格正文は未入手、日本語研究は本文未読

### `docs/research/docverify/A_competitors.md`（98 行）
- 役割: 競合調査（WebSearch 11＋WebFetch 5 回、2026-10-15）。区分は実証/主張/未確認
- 主な要素: 製品別 — QuintSpect（バルテス: 5 観点・矛盾検知・Excel/PDF・履歴と通知・14 社利用・精度なし）／QVscribe（QRA: 曖昧さ・測定可能性・構造・一貫性・類似、INCOSE と EARS、1-5 スコア、スナップショット時系列、網羅性とモデル/テスト/コード突合は未対応）／IBM RQA（Watson NLP、1-100 スコア、INCOSE/NASA、SaaS は終了し REQUISIS 後継の記述）／Visure Quality Analyzer（8 指標、QVscribe 基盤）／Jama Connect Advisor（INCOSE/EARS、欠落リンク、テスト下書き）／Copilot4DevOps（INVEST 等）／SpecLens 系は特定できず／国内 SIer のレビュー製品は確認できず（富士通は設計書生成、KPMG は要件レビュー自動化は困難と指摘）。比較表（規格・矛盾・改版・管理・入力・精度公開）。必須機能: 曖昧語指摘・スコア化・人の採否・既存ツール内の入口。空白: 精度公開、実画面との突合、網羅性、根拠と再現可能な記録、日本語特化、改版差分再検査。引用禁止数値: 「5 アカウント 0 円」、富士通「30分の1」、Visure 導入統計、「41 ルール」
- 関連: 製品の差別化（match=実画面突合、diff.py、metrics 精度）
- 注意: 本文の「国内 SIer 製品なし」等は「確認できず」でありなし証明ではない。競合の機能は 2026-10 時点の公開情報で更新される

### `docs/research/docverify/B_research.md`（69 行）
- 役割: 要求仕様の欠陥自動検出と LLM レビューの研究調査（全件 abstract のみ確認）
- 主な要素: 16 件の表。Femmer 2016 Smella（平均 P59%/R82%）、Paska 2023（13 smell、検出 89/89・推薦 96/94、金融単一企業・英語・preprint）、Zakeri-Nasrabadi 2024、Gentili 2024、TAPHSIR 2022、Luitel 2023、Lubos 2024（LLM の 29148 評価）、Krishna 2024、PassionNet 2024（+13% F1 相対）、Malik 2023、LEREDD 2026（accuracy 0.93・F1 0.84）、VERIMED 2026（55.4%→98.5% は修復後精度）、Vogelsang 2025 ほか。日本語: 有賀・ReqQA・富山県立大・デンソー 2025（言語処理学会）・KBSE 2017（数値未取得）。古典: NASA ARM・QuARS・EARS（記憶由来で未確認）。製品化の指針 6 件（辞書ルール、EARS 書式強制と書き換え、LLM は説明・書換案、複数回形式化の不一致を曖昧性シグナル、矛盾・重複は候補、孤立要求の決定的チェック）。人の判断が要る領域（不完全性・矛盾・実害判定・用語同一性・日本語・LLM 再現性）。引用禁止数値 9 項目
- 関連: P2（LLM 二段構成）・P3（矛盾・追跡）の設計根拠
- 注意: Semantic Scholar は HTTP 429 で取得失敗、IPA/SEC・JaSST 該当資料は未発見。数値は小モデル要約経由で一次確認前。本ファイルの 2026 年の arXiv ID の一部は未検証

### `docs/research/docverify/C_standards.md`（146 行）
- 役割: レビュー・インスペクション規格を製品機能要件へ翻訳する調査（規格本文は有償・未入手、二次資料のみ）
- 主な要素: 出典 S1〜S11。29148:2018（個別と集合の 2 層特性。個別=必要/適切/曖昧でない/完全/単一/実現可能/検証可能/正確/適合は未確認、Clause 4 で適合宣言可）／IEEE 1028-2008（5 種のレビュー・体系的レビューの最低要件、作者≠議長、入口/出口基準）／Fagan 7 工程（Russell 1991 の速度と検出率は二次引用）／ISO/IEC 20246:2017／ISTQB（5 活動・役割・アノマリー）／機能安全（ISO 26262 確認措置、IEC 61508 SIL と独立性、DO-178C Table A-3）／IPA/SEC 白書／INCOSE GtWR v4（C1〜C14・規則 R1〜）。9 章に商用ツールが規格準拠を謳う必須機能チェックリスト（A プロセス・種別／B 役割・独立性／C 指摘管理／D 品質特性検査／E メトリクス／F 記録・監査証跡／G 表示・宣言）。未確認事項（規格本文・1028 の現行ステータス・26262 の I0〜I3 対応・DO-178C 独立性目的数・Fagan 推奨速度・IPA 基準値）。引用禁止: 「Fagan 80-90%検出・コスト25%削減」、「規則 30〜40 個」
- 関連: v2 の phase/participants/approval（計画・個別レビュー・指摘の検討・修正・修正版確認・判定と記録）、metrics の検査速度・密度、「準拠」を謳わない表現規則
- 注意: 「規格準拠」と書けない（認証規格ではない・範囲宣言のみ）。画面の工程名は ISTQB 5 活動と Fagan に概ね対応するが、独立性レベル（I0〜I3）・不変ログ・電子署名・準備速度警告の実装有無は本担当範囲では未確認

### `docs/research/docverify/D_formal_methods_book.md`（289 行）
- 役割: 書籍『形式的手法の基礎と応用』第1〜13章・付録・note 記事2本・QuintSpect の精読メモ。章ごとに製品機能への示唆を抜き出す。
- 主な要素:
  - 読了範囲は申告付き。全文は第1〜7章・第10章・付録F・記事・QuintSpect。第8,9章は前半、第11〜13章と付録A〜Eは見出し・キーワード抽出のみ（実証）。
  - 曖昧性の4分類（語彙・構文・意味・実用）。曖昧点を「箇所×解釈候補数×リスク3段階」で出す表が主画面候補。
  - 完全性チェックリスト5項目（操作・状態遷移・エラーケース・不変条件・操作間関係）を採点軸に。正常系＋エラー系で全入力を覆うか、エラー時に状態不変の記載があるかを検査。
  - 反例の4分類（欠陥・要求不明確・モデル不備・許容）を指摘のトリアージ列に。指摘に検査範囲と未検証範囲を併記。
  - 安全性/活性の区分、結果は検証済み/未検出/未完走/タイムアウトを区別。
  - 付録F: LLM は提案者、検証器が判定者。指摘カードは事実と仮説を分離。外部 LLM へ送る前のマスキング。
  - note A: 暗黙に確定された境界（0可否・1000含む等）を持ち主に承認させる。型検査の合格は意図適合ではない。境界値テスト条件（0・1・1000・1001）の導出。
  - QuintSpect: 5観点採点・矛盾検知・抜け漏れ検知（トレーサビリティ表＋完全率）。月額6.6万〜30万円。差別化案は原文根拠、検査範囲明示、決定的検査、Web仕様との突き合わせ。
- 関連: 検出（曖昧語・暗黙の前提・TBD・エラー系欠落）、指摘カード構造（事実/仮説/範囲）、質問票（疑問→確定値）、メトリクス（完全率）、精度の見せ方、競合比較、外部LLM送信前マスキング。
- 注意: 「1ページ15〜20個の曖昧表現」「重要機能要求の約30%が複数解釈可」「非機能の約50%が定量基準欠如」は出典なしで引用不可。第11〜13章のコスト数値（開発+20〜50%、14号線+20〜30%・重大問題60%減）は原典未確認で販促に使わない。26.6%/8.6%（TLA+生成、2026年6月論文）は note 経由の二次情報で論文未確認。note A の著者は z-spec を未実行。書籍は CC BY-NC-SA 4.0 で文面の商用転載は不可の可能性（未確認）。

### `docs/research/docverify/D2_book_ch8-13.md`（252 行）
- 役割: 同書の第8章後半〜第13章の全行読み抜き出し（第11,12,13章は全行、第8,9章は指示範囲のみ）。
- 主な要素:
  - 判定は三値以上（成功/反例あり/未完走）。「未完走」を緑にしない。前提（assume相当）を足して通すことの検知。
  - 「LLM は提案、判定は決定的な検査器」を製品中核に。TBD・未定義・暗黙前提の「未解決穴」ダッシュボード。
  - 要求指摘は3カテゴリ（矛盾/不完全/トレーサビリティ欠落）。形式化ラダー（構造化日本語→半形式→形式）。
  - 検証証跡パッケージ（入力ハッシュ・版・設定・判定・反例・未検証一覧）と例外台帳（期限・責任者）。success/failure/timeout/unknown/flaky の区別。
  - 実行プロファイル3層（PR 約90秒以内/夜間/リリース前）。
  - 第13章: Cedar 流の表形式仕様（権限表・料金表・状態遷移表）の差分検査（権限拡大・到達不能・等価）。欠陥版/修正版の対照テストセット。結果分類は整合/矛盾/曖昧/未述の前提/判定不能。各検証に「形式化と保証範囲」5欄。
- 関連: 検出（矛盾・不完全・トレーサビリティ）、指摘の判定ラベル、メトリクス（MTTR・反例再現率・検出密度）、精度の提示（過大訴求防止）、導入ロードマップ、回帰テスト。
- 注意: 章URLはファイル名からの推定で実在未確認。導入期間（PoC2〜4週等）、コスト倍率（業界別10〜100%）、14号線のソフト障害75%減、s2n開発費2〜3倍などは本書の主張で原典未確認、引用しない。ROI は顧客実測で算出し本書倍率を既定値にしない。ベンチマーク数値（AlphaProof 等）は本書自身が製品品質の証拠でないと注記。CI例（formal-checks.yml）は CI 厳禁方針のため採用しない。

### `docs/research/docverify/D3_book_appendix.md`（300 行）
- 役割: 付録A〜F・用語集・序文/あとがき/索引・QuintSpect LP・note記事の読了メモと、商用化機能候補の優先度表。
- 主な要素:
  - 事前・事後・不変条件の三点セットで記載項目の網羅性を機械判定。量化語（すべて/どれか）の母集合の有無を指摘。
  - 結果は合格/不合格/判定不能の3値。実行ごとに入力ハッシュ・ルール版・モデル版・日時を記録。
  - 曖昧性出力形式「曖昧語→解釈候補→影響」と、分岐の積による曖昧度スコア。採点5観点（正確性・完全性・一貫性・再現性・妥当性）。競合の5観点との差別化余地は完全性・再現性。
  - F.9 仕様チェックリスト5項目（用語定義・前提・不変条件・活性・数値出典）を観点プリセットに。DoD 4項目もプリセット候補。
  - 用語集機能を3分解（未定義略語・異表記・定義矛盾）。数値境界（以上/以下/未満/超過、0可否、上限）の抽出と境界値案提示。数値出典の有無チェック。
  - 優先度「高」: カスタム観点プリセット、曖昧語/数値境界、用語統一、判定不能表示。QuintSpect LP に用語統一・docx・Web画面の記載なし（機能不在の証明ではない）。
  - 価格比較: 約¥13,200/ファイル（スターター）、約¥2,000/ファイル（スタンダード）は調査者の割り算。
- 関連: 検出（曖昧語・数値境界・用語ゆれ・数値出典）、質問票、メトリクス（曖昧度スコア）、精度表示（判定不能）、観点プリセット、証跡、送信前マスキング。
- 注意: 優先度は主観で市場検証なし（未検証）。26.6%/8.6% は原論文未確認。QuintSpect の不在判断は LP 本文の範囲のみ。第1〜13章は範囲外。書籍文面の製品転載は不可、構造のみ参照（窓口 knowledge@itdo.jp）。

### `docs/research/docverify/E1_datasets.md`（51 行）
- 役割: 要求品質検査の精度評価に使える公開データセットの調査と、日本語評価セット作成手順。
- 主な要素:
  - 候補: ARTA（4,752件・9種smell手動注釈・ライセンス記載なし）、PURE（79文書・CC BY 4.0・注釈なし）、PROMISE NFR（CC BY 4.0・分類用）、矛盾系は変異ペア等（ライセンス要確認）。実証は取得ページでの確認分のみ。
  - 公開順位: ARTA（ライセンス確認までは社内評価のみ）→ PURE+自前注釈 → PROMISE NFR → 矛盾系。日本語の公開注釈データは確認できず、自作が唯一の道。
  - 日本語評価セット手順: 許諾済み文書のみ公開、良文への欠陥機械注入と実文書手動注釈の併用（数値は区別）、2名独立注釈＋裁定＋Cohen's kappa、300〜500文から、適合率/再現率を種別別・n併記。
- 関連: 精度（評価セット設計・公開方法）、検出（曖昧語・smell・矛盾の正解データ）。
- 注意: PROMISE の625件は既知情報で今回未確認。TRAINNLI 約50万対・AraREQ 27K対は主張。矛盾・曖昧データのライセンスは未確認。Semantic Scholar 取得失敗（429）。IPA 文書は未調査。「無い」ではなく「確認できず」。ISO/IEC/IEEE 29148 は規格名のみ引用。

### `docs/research/docverify/E2_japanese_research.md`（131 行）
- 役割: 日本語の要求仕様品質評価研究3本（デンソー NLP2025、デンソー JSAI2025、有賀ら 2013）の本文確認と数値転記。
- 主な要素:
  - LLM 単独は不十分、規則ベース前後処理（GiNZA 解析・誤字候補の事前絞り込み）併用で大幅改善（主張・単一車載製品）。例: 簡潔な文は適合率 0.31→0.97、再現率 0.71→1.00（NLP2025 表1の画像読み取り）。
  - JSAI2025: 仕様書を知識グラフ化して検査。完全な場合分けの再現率 0.00→0.75、誤った記載場所 0.11→0.90（ゼロショット・温度0）。意味理解型規則（単一要求）は効果が限定的。
  - 有賀ら: 構文解析ベースで適合率0.66・再現率0.87（14要求・著者1人作成の正解53件）。項目別に差が大きく、誤検出が被験者に悪影響。
  - 示唆: 候補を規則で絞ってから LLM、専門用語辞書の供給、表構造の確定、スコープ明記、精度は項目別・適合率/再現率を分けて表示。
- 関連: 検出（規則＋LLM 二段構成）、精度（項目別表示）、前処理（表・入れ子・括弧）、用語辞書。
- 注意: 同じ「完全な場合分け」の LLM 単体再現率が NLP2025=0.57、JSAI2025=0.00（few-shot 有無等の条件差）。条件抜きで並べて引用不可。有賀らの 0.66/0.87 を現代 LLM の目標値にしない。n・人手正解件数・試行回数は本文に無く、1.00 は信頼区間なし。ReqQA(SES2015)、IEICE ISS-P-038、佐野町らデータセットは未確認。GiNZA での括弧問題は未検証。

### `docs/research/docverify/E3_jp_documents.md`（67 行）
- 役割: 日本の設計書・仕様書の実態と、取り込み処理（readers.py / ingest.py）の難点対応表、P1 の優先順位。
- 主な要素:
  - 17行中 対応3・一部3・未対応11。未対応: 行と見出しの対応、docx 結合セル重複・文書順序・テキストボックス・入れ子表・ヘッダ/フッタ、xlsx 図形、数式セル（保存値なしで欠落）、隠しシート、セルコメント、画像のみ文書。
  - P1 優先順位: ①行と見出しの対応（項目表の断片化が誤検出の根） ②docx 文書順序 ③結合セル重複排除 ④テキストボックス/図形 ⑤ヘッダ/フッタ/入れ子表 ⑥数式セル ⑦隠し要素と欠落の申告。
  - 方針: 拾えなかった要素（図形・画像・数式・コメント）の件数を取り込み結果に出す。無言の欠落が最悪。
- 関連: 取り込み（ingest）、検出精度（checks.py）、取り込み結果の欠落申告、項目表の抽出。
- 注意: 実測は xlsx/docx 各1ファイル。xlsx 図形はコード根拠のみ（未実測）。実設計書での頻度は未検証。「項目定義の列は通例」は一般知識（未検証）。デジタル庁・総務省一次資料は未取得。総務省ルールは統計表向けで設計書への拡張は断定不可。行番号は当時の readers.py/ingest.py のもので現行とずれる可能性。

### `docs/research/docverify/E4_nfr_commercial.md`（94 行）
- 役割: 日本市場向けの仕様書AI検査SaaSの商用非機能要件（法令・ガイドライン・LLM各社条件・競合）調査。
- 主な要素:
  - 必須NFRチェックリスト14項: 送信先開示、学習不使用、保持期間と削除、国内保存と国内処理の区別、マスキング・送信前確認、DPA、テナント分離、暗号化、監査ログ、AI生成明示と人の判断、精度開示、認証、縮退動作、解約時消去。
  - LLM各社条件（実証、取得日2026-10-15）: OpenAI 学習不使用・不正利用監視ログ最大30日・地域内処理は不可、Azure 学習不使用・指定地域内処理、Gemini(Vertex) 学習不使用・キャッシュ最大24時間。「学習不使用」と「保持ゼロ」、国内保存と国内処理は別。
  - ローカルLLM（送信しない）はオプション提供として検証。主軸にはしない。次の一手は見込み顧客5〜10社への聞き取りとクラウド/ローカルの同一データ比較。
- 関連: 外部LLM送信設計、マスキング、監査ログ、精度開示、データ保持/削除、運用プラン、競合比較。
- 注意: 59.9%（機密漏えい懸念、JIPDEC/ITR 2025）は二次記事経由で原本未確認、設計書限定でもない。ローカルLLM導入率など導入支援会社の数値は引用禁止（需要は未確認）。AI事業者ガイドライン第1.2版（2026/3）は二次1件のみで要確認、条文レベルの義務は未読。ISMAP-LIU の要件・費用は未確認。Japan East/東京リージョンの提供モデルは未確認。QuintSpect の料金は資料間で不一致。ISMS/SOC2 の購買影響は未検証。ローカルLLM比較に Ollama を挙げているが、プロジェクト方針は Ollama 不使用（スタブで試験）で食い違い。

### `docs/research/docverify/E5_review_metrics.md`（156 行）
- 役割: 設計書・要件定義書レビューの業界基準値（IPA 白書、NASA 検査速度）と製品既定しきい値の根拠。
- 主な要素:
  - IPA『ソフトウェア開発データ白書 2018-2019』（一次確認）: 指摘密度（件/頁）基本設計 中央0.276（P25 0.117〜P75 0.764, N=206）、詳細設計 中央0.164（0.072〜0.416, N=199）。レビュー工数比率は基本・詳細とも中央約8%、製作5%。設計書1頁あたり審査工数は基本新規0.610人時、詳細新規0.448人時（中央値）。
  - 製品既定しきい値案: 指摘密度は P25 未満を「低すぎ」、P75 超を「高すぎ」の警告にし、良否の断定には使わない。中央値と四分位を使い、平均は使わない。日本のIT企業の集計であり Web アプリ・AI 生成文書には外挿できない旨を画面併記。
  - レビュー速度の上限目安は約50頁/時（Litton 単一組織）。
- 関連: メトリクス（指摘密度・レビュー速度・工数比率の目安表示）、しきい値警告、画面の注記。
- 注意: 引用禁止＝IPA 図7-3-7 の元値（N=404・中央16.3、正誤表で N=380・中央3.1 に差替）、平均値全般、Gilb「1頁/時」・Fagan・NASA推奨頁率（原典未確認）、100〜200行/時等（二次引用でコード向け）、Basili 1.6→0.6%、頁/人時の逆数（約1.6・約2.2は導出値）、48頁/時の一般化、JUAS の数値（未取得）、欠陥除去率。NASA 頁率の効果は現代データで有意差なし（p=0.5）。要件定義レビュー指標、新規/改良別密度、JUAS 本文は未確認。

