# Agent D 監査: /orchestration（指揮）

対象: worktree wt-gui（origin/main 0efbd20）。根拠は file:line か curl（監査サーバ 8768）。ブラウザ未使用のため見た目・実機の挙動は「未検証」。

## 事実

### 入口と 3 画面の関係
- `/orchestration` は `orchestration.html`（5 工程ステッパー + 1 枚のカード）を返す。`web/routes/orchestration.py:189-199`
- `/orchestration/<variant>` で旧案 `b`（一覧）と `d`（サイト別の記録）が残る。`orchestration.py:203-209`。docstring は「開発・比較用」。
- 正本は `/orchestration`（`orchestration.html` + `orchestration.js` 998 行 + `/api/orchestration/workflow`）。ただし `d` は左メニュー「実行履歴」の遷移先（`partials/conductor-sidebar.html`、href=/orchestration/d）で、事実上の本番画面。`b` はどこからもリンク無し（未検証: 他テンプレのリンク全数は grep していない）。
- 3 画面は別々の殻。新画面は conductor-sidebar + topbar、`d` は topbar のみ（サイドバー無し、`orchestration_d.html:21-24`）、`b` は独自 `cb-shell`。ナビが画面ごとに変わる。
- `ASSET_VERSION` が不揃い。`/orchestration` と `/d` は `?v=1`、`/b` は `?v=1792447684`（curl）。`b` は `_ver` を set していない（`orchestration_b.html` 冒頭に `{% set %}` 無し）。

### 現行 5 工程（`workflow_view.py:37-43`）
- 解析 / テスト設計 / 実行 / 分析して直す / 判断。1 サイトずつ、現在の 1 工程だけをカードに出す。
- データ源: 実データ。conductor の run 記録（`run_store`）、healing の project・報告書、`autorun_bridge.load_failures`（失敗件数）。見本（mock）ではない。
- `current.text_source` で measured / user / llm / unverified を区別（`workflow_view.py:60-72`）。出所表示の仕組みはある。
- 応答キー: `domain, sites[{domain,label}], repos, rounds, steps[{key,label,no,state,summary}], current{key,state,headline,text,text_source,elapsed_sec,error,action}, run_id, updated_at`（curl）。
- 操作 API: `POST /api/orchestration/workflow/actions` は `require_admin`（`orchestration.py:421-426`）。閲覧 API は無認可で読める。
- 更新: 実行中のみ 5 秒ポーリング、タブ非表示で停止（`orchestration.js:958-972`）。

### 実測した不整合
- サイトが 2 件（`/api/healing/sites`: demo.realworld.show, localhost:8792）あるのに、`/api/orchestration/workflow` は `key=setup`「まだサイトが登録されていません」を返す。healing の project が 0 件（`/api/healing/projects` が空）のとき観測済みサイトを無視する。ユーザーには「登録済みなのに未登録」と見える。
- `/orchestration/d` の JS は起動時に sites / projects / runs(400) / reports(200) の 4 本を取る（`orchestration-d.js:27-39`）。集計はすべてクライアント側で、他画面から再利用できない。
- 存在しない API: `/api/sites` `/api/dashboard` は 404、`/api/snapshot-diff-summary` `/api/autorun/status` も 404（パス違いの可能性。正しいパスは未特定）。

### shell・状態・a11y・responsive・deep-link
- shell: 新画面は `app-shell` + sidebar（7 項目: サイト/実行履歴/報告書/見張り/コードの場所/ガイド/設定）+ topbar。`skip-link` あり（`orchestration.html:19`）。
- 状態: 読込み中は「読み込み中…」固定文、失敗は `renderLoadError`（`orchestration.js:166-174`）で再試行ボタン無し（開き直し案内のみ）。empty は setup カード。partial（一部 API 失敗）の扱いは無い（1 API のため）。`d` は `role=alert` のバナー 1 枚（`orchestration_d.html:26`）。
- a11y: `aria-live="polite"` はカード 1 つ。JS 内の aria/role/focus は `orchestration.js` 1 箇所・`-d.js` 3 箇所・`-b.js` 4 箇所のみ。状態遷移時のフォーカス移動は無い（`.focus()` は textarea 1 箇所 `orchestration.js:849`）。ステッパーは `<ol aria-label>` だが `aria-current` は未確認。
- responsive: `orchestration.css` の `@media` は `prefers-reduced-motion` のみ（`orchestration.css:256`）。幅の分岐は無し。`-d.css` `-b.css` に `@media` 無し（grep 0 件）。親 CSS（app.css/ta2.css）の効果は未検証。
- deep-link: `?site=` を `replaceState` で更新（`orchestration.js:142-146`）。履歴に積まないため戻るボタンでサイト切替は戻れない。工程・run_id への deep link は無い。
- テスト: tests/ に orchestration / workflow を名に持つファイルは 0 件（`ls tests | grep`）。内容 grep では参照ファイル 0 件。JS は `window.__cw` で露出するが対応テストは見当たらない。

## 日常運用ホームとの差（表 1 個）

判定: ある / 部分 / 無し。

| 要素 | 判定 | 根拠 |
|---|---|---|
| 全サイト数 | 部分 | workflow.sites 配列 |
| 正常 / 失敗 / 実行中 件数 | 無し | 集計 API 無し、d は 14 日帯のみ |
| 確認待ち・承認待ち件数 | 部分 | /api/healing/reports/count |
| 未確認・今日の変更件数 | 無し | 集計 API 無し |
| テスト・修正・報告 件数 | 無し | 件数集計の API 無し |
| 一覧の latest status | 部分 | d の run 状態をクライアント集計 |
| current stage | 部分 | workflow は 1 サイトのみ |
| last run | 部分 | d が runs から導出 |
| evidence health | 無し | 実測/AI/未検証は 1 文単位のみ |
| pending human action | 部分 | run.human_action |
| latest change / failure | 無し | 失敗件数は選択サイトのみ |
| 各 System 結果 deep link | 部分 | 報告書リンクのみ |

補足:
- 「部分」は 1 サイト単位、または画面ごとに別実装で、全サイト横断の一覧が 1 回の呼び出しで取れない。
- 現行入口は「1 サイトを 5 工程で進める作業画面」で、日常運用ホームではない。

## 使える既存 API

- `GET /api/healing/sites`: `domain, title, screens, observed, updated_at`（全サイトの最小一覧。状態は無い）
- `GET /api/healing/projects`: 保守下のサイト（`monitor_enabled` 等。件数 0 のときが多い）
- `GET /api/orchestration/runs?limit=N`: ConductorRun 全体。`run_id, domain, goal, status, step_index, steps[], human_action, error, started_at, finished_at`（last run・実行中・失敗・人の判断待ちの源）
- `GET /api/healing/reports?status=awaiting&limit=N` と `/count`: 承認待ち報告書と件数
- `GET /api/healing/runs`: 修正実行の一覧
- `GET /api/history/runs`: `stats{total,complete,failed,cancelled}` を既に返す（テスト実行の件数源。ドメイン別かは未検証）
- `GET /api/runs/<domain>`: `current_run_id, runs, total`（サイト別実行）
- `GET /api/orchestration/workflow?site=`: 1 サイトの現在工程・次の操作
- `GET /api/orchestration/goals`: 目標（daily/onboard/continue）と工程名
- `GET /api/snapshot-diff`（pages 系、`/api/snapshot-diff-summary` は 404）: 今日の変更の源候補。返却項目は未検証

### 新しい集計 API の最小形（提案）
`GET /api/home/summary` 1 本。サーバ側で上の API 群を束ね、次を返す。
- `counts`: `sites, ok, running, failed, awaiting_confirm, awaiting_approval, unverified, changes_today, tests, fixes, reports`
- `sites[]`: `domain, label, status, stage, last_run{id,at,status}, evidence{measured,llm,unverified}, human_action, latest_change{at,text,href}, latest_failure{at,text,href}, links{docs,tests,autorun,healing,reports}`
- `partial_errors[]`: 取得に失敗した源の名前（画面側で部分表示にする）
既存関数 `workflow_view._list_sites` `_latest_run` `_failure_count` `_awaiting_reports` を流用できる（`workflow_view.py:130,181,347,361`）。

## 採点（0〜4）

| 軸 | 点 | 根拠 |
|---|---|---|
| 1 IA | 1 | 3 画面が別殻でサイドバー有無が違い、ホームが無い |
| 2 Golden Path | 2 | 5 工程の誘導は明快。ただし未登録誤判定と全体俯瞰が無い |
| 3 Loading・Empty・Error・Recovery | 1 | 読込み固定文、失敗に再試行ボタン無し、partial 無し |
| 4 Product Truth・Evidence | 3 | 実データで出所区分あり。ただし件数の集計が無い |
| 5 Permission・Safety | 3 | 操作系は require_admin、audit 記録あり。閲覧は無認可（未検証: ロール別の見え方） |
| 6 Accessibility | 1 | live 領域 1 つ、フォーカス管理無し、aria 記述が少ない |
| 7 Responsive・Browser Navigation | 1 | 幅の分岐無し、replaceState で戻れない |
| 8 Visual Consistency | 2 | 画面ごとに CSS が別（3 本）。見た目は未検証 |
| 9 Performance・Feedback | 2 | workflow は 32ms（curl）。d は 4 本取得 + 400 件を全部クライアント集計 |
| 10 Maintainability・Testability | 1 | JS 3 本 2,300 行超、旧案 b 残置、専用テスト 0 件 |

## P0 候補

- D-P0-1: 日常運用ホームを新設する。`/api/home/summary`（上記）と、件数 8 項目 + サイト一覧 + 各 System への deep link を 1 画面にする。`/orchestration` の入口を置換し、現行 5 工程は `?site=` の詳細へ下げる。
- D-P0-2: 観測済みサイトがあるのに「まだサイトが登録されていません」と出る誤判定を直す（`workflow_view.py:462` 周辺。project 0 件のとき `sites` を見る）。
- D-P0-3: 3 画面の殻を 1 つに揃える（`d` にサイドバー追加、`b` は削除または廃止）。ASSET_VERSION も統一する。
- D-P0-4: 状態表示を揃える。loading のスケルトン、error の再試行ボタン、一部取得失敗の partial バナー、empty の次の行動。
- D-P0-5: a11y と戻る操作。状態更新時の `aria-live` と見出しへのフォーカス移動、`?site=` を `pushState` にして戻るで復元、幅の分岐（狭幅）を追加する。
- D-P0-6: `/orchestration` と workflow API のテストを新設する（setup 誤判定・admin 以外の操作拒否・日次ホームの件数）。
