# WS2D-DD-006 詳細設計書 System 06「ドキュメント検証」R1

- 文書ID: WS2D-DD-006 / 版数: 0.1（草案・未承認） / 作成日: 2026-10-15 / 作成者: 開発チーム / 承認者: 未承認（保守者が記入する）
- 準拠: IPA 共通フレーム（ソフトウェア詳細設計相当）。テスト観点は ISTQB CTFL のテストレベル（単体・結合・システム）で分け、受入基準（RD-006 の G/W/T）から導く
- 上位文書: WS2D-BD-006 基本設計書 System 06 R1・WS2D-RD-006 要件定義書
- 範囲: BD-006 0 章と同じ（FR-06-015・075・100〜104、SCR-06-01・04・08・20〜26、NFR-06-08・16・18、AC-06-05）。FR-06-123 は含めない

## 1. ファイル一覧と並列の単位

1 行＝実装担当 1 本。**ファイル間の契約（関数名・JSON キー・クラス名・DOM の id）は本書で固定する。**変えるときは本書を先に改版する。

| # | ファイル | 区分 | 依存（契約だけを使う） | 節 |
|---|---|---|---|---|
| F1 | `web/services/docverify/unread.py` | 新規 | なし | 2 |
| F2 | `web/services/docverify/ingest.py` | 変更 | F1 `scan` | 3 |
| F3 | `web/services/docverify/store.py` | 変更 | なし | 4 |
| F4 | `web/services/docverify/metrics.py` | 変更 | F1 `lines` | 5 |
| F5 | `web/services/docverify/home.py` | 新規 | F4 `summary` | 6 |
| F6 | `web/routes/doc_verify.py` | 変更 | F4・F5 | 7 |
| F7 | `templates/doc_verify.html` | 変更 | — | 8.1 |
| F8 | `templates/docverify/_global.html` | 変更 | — | 8.2 |
| F9 | `static/js/docverify-core.js` | 変更 | F7 の DOM | 8.3 |
| F10 | `static/js/docverify-global.js` | 変更 | F5 の JSON・F8 の DOM・F9 | 8.4 |
| F11 | `static/js/docverify-review.js` | 変更 | F4 の JSON・F9 | 8.5 |
| F12 | `static/css/docverify.css` | 変更 | 8.6 のクラス | 8.6 |
| — | `web/vendor/reverse_doc/docs_ingest/readers.py` | **変更しない** | — | — |
| — | `docs/process/docverify-contract.md` | 変更（F6 の担当が同じ PR で） | 4 章の API 差分を追記 | — |

共通の規約: 関数 50 行未満・ファイル 400 行以内・入力の dict/list を変更せず新しいものを返す・利用者向けの文は 9 章の文だけを使う・CSS は `tokens.css` の変数だけ（直値の色・px の余白を新たに書かない。既存の px 値の慣習は踏襲してよい）。

## 2. F1 `unread.py`（新規）— 読めなかった要素を数える

| 公開 | 引数 → 戻り値 | 内容 | ID |
|---|---|---|---|
| `KEYS` | `tuple[str]` | `("images", "comments", "hidden_sheets", "hidden_cols", "shapes")` | FR-06-015 |
| `scan(path: Path, suffix: str) -> dict` | 例: `{"images":3,"comments":2,"hidden_sheets":0,"hidden_cols":0,"shapes":0,"scanned":True}` | 形式で振り分け。**例外を外へ出さない**（失敗は全 0＋`scanned: False`、`log.warning` に詳細） | FR-06-015 |
| `lines(u: dict \| None) -> list[str]` | 9 章 M-01〜M-05 の文 | 画面と xlsx の共通文 | FR-06-015 |

数え方（中身は読まない。XML に `<!DOCTYPE` / `<!ENTITY` があれば `scanned: False`）:

| 形式 | images | comments | hidden_sheets | hidden_cols | shapes |
|---|---|---|---|---|---|
| xlsx | `xl/drawings/drawing*.xml` の `xdr:pic` 数 | `xl/comments*.xml` の `comment` 数。0 なら `xl/threadedComments/*.xml` の `parentId` 無し `threadedComment` 数 | `xl/workbook.xml` の `sheet` で `state` が `hidden`/`veryHidden` | 各 `xl/worksheets/sheet*.xml` の `col[hidden=1]`（max−min+1）＋`row[hidden=1]`。`iterparse` で読む | 図面内の `xdr:graphicFrame`（グラフ・SmartArt）＋`a:t` を持たない `xdr:sp` |
| docx | `word/document.xml`・`header*.xml`・`footer*.xml` の `pic:pic` 数 | `word/comments.xml` の `w:comment` 数 | 0 | 0 | `a:graphicData` の `uri` が chart / diagram のもの＋`w:t` を持たない `wps:wsp` |
| pdf | pdfminer の `LTImage`（`LTFigure` の中も再帰） | pypdf の `/Annots` のうち `/Subtype` が `/Link`・`/Widget`・`/Popup` 以外 | 0 | 0 | 0（測れない。BD6-Q5） |
| md / txt | md は `!\[[^\]]*\]\(` の数。txt は 0 | 0 | 0 | 0 | 0 |

内部関数（非公開・名前は担当の裁量）: `_xlsx(path)`・`_docx(path)`・`_pdf(path)`・`_md(path)`・`_safe_xml(raw: bytes)`。

## 3. F2 `ingest.py`（変更）

| 関数 | 変更 | ID |
|---|---|---|
| `ingest(filename, data, work_dir) -> (document, passages)` | 戻り値の `document` に `"unread": unread.scan(path, suffix)` を足す。PDF は `unlock_pdf` の後に数える。断片 0 件の `IngestError` は現行どおり（数える前に判定） | FR-06-015 |

`document` の形（固定）: `{"name","format","passages","version","unread"}`。

## 4. F3 `store.py`（変更）

| 関数 | 変更 | ID |
|---|---|---|
| `save(insp) -> dict` | 書く直前に `{**insp, "updated_at": <UTC ISO 8601>}` を作って保存し、その dict を返す（引数は変更しない。現行の呼び出し側は戻り値を使わなくてよい） | SCR-06-01 |
| `upgrade(insp)` | 変更しない（追加キーは読み手が `get()` の既定で扱う） | 互換 |

## 5. F4 `metrics.py`（変更）

### 5.1 公開関数

| 関数 | 引数 → 戻り値 | 内容 | ID |
|---|---|---|---|
| `QUALITY_NOTE` | `tuple[str, str, str]` | 9 章 M-10〜M-12 の 3 文 | FR-06-103 |
| `ITEM_LABEL` | `dict` | 現行 `_ITEM_LABEL` を公開名に（旧名は別名で残す） | FR-06-100 |
| `quality(insp) -> dict` | 現行に追加: `items[k]["label"]`・`"note": list(QUALITY_NOTE)` | 式は変えない。断片 0 は `overall`・各 `score` が `None` | FR-06-100・102・103 |
| `quality_brief(insp, final: bool) -> dict` | `{"overall": int\|None, "items": {k: int\|None}, "final": bool}` | 版の記録に入れる形 | FR-06-104 |
| `freeze_current(insp) -> list[dict]` | 新しい `versions` | 最後の版に `quality_brief(insp, True)` を入れた新しい list。`versions` が空なら `[]` | FR-06-104 |
| `history(insp) -> list[dict]` | 5.2 | 版ごとのスコア。最後の版が未確定なら現在値 | FR-06-104 |
| `unread_lines(insp) -> list[str]` | 文の list | 文書なし `[]`／`document` に `unread` 無し M-04／それ以外 `unread.lines()` | FR-06-015 |
| `scope(insp) -> dict` | 5.3 | 検査した範囲・検査していないこと | FR-06-075・NFR-06-08 |
| `summary(insp) -> dict` | 現行に `history`・`unread_lines`・`scope` を追加 | 既存キーは変えない | 全体 |
| `to_xlsx(insp) -> bytes` | 10 章 | シート「検査した範囲」を追加 | FR-06-075 |

### 5.2 `summary` の追加分（JSON・固定）

```json
{
  "quality": {
    "overall": 80, "passages": 10,
    "items": {"unambiguous": {"open": 2, "score": 80, "label": "曖昧でない"}},
    "note": ["…", "…", "…"]
  },
  "history": [
    {"version": 1, "name": "要件.xlsx", "uploaded_at": "2026-10-01T…Z", "overall": 60, "final": true, "current": false},
    {"version": 2, "name": "要件.xlsx", "uploaded_at": "2026-10-08T…Z", "overall": 80, "final": false, "current": true}
  ],
  "unread_lines": ["画像 3・コメント 2 は読んでいません。"],
  "scope": {
    "checked":   [{"label": "文書", "value": "要件.xlsx（版 2・xlsx）"}],
    "unchecked": [{"label": "網羅性", "value": "未検証。…"}]
  }
}
```

`history` の規則: 版の `quality` が無ければ `overall: null`。最後の版で `final` が偽（または `quality` 無し）かつレビューが未終了なら `overall` は `quality(insp)["overall"]`、`current: true`。

### 5.3 `scope` の行（label は固定。value は 9 章の文）

| 区分 | label | value |
|---|---|---|
| checked | 文書 | `{name}（版 {version}・{format}）`／未取り込みは M-20 |
| checked | 断片数 | `{n} 断片` |
| checked | 読めなかった要素 | `unread_lines` を空白で連結 |
| checked | 自動検出 | `規則による候補 {a} 件（採用 {x}・却下 {y}・未検討 {z}）` |
| checked | 人の確認 | `レビュアー {done}/{n} 人が確認を終えました`／参加者なしは M-21 |
| checked | 観点チェックリスト | `確認済みの観点 {n} 項目`／未選択は M-22 |
| checked | 品質スコア | `総合 {overall}`／`None` は M-13 |
| unchecked | 網羅性 | M-30 |
| unchecked | 意味の正しさ | M-31 |
| unchecked | 読めなかった要素の中身 | 読んでいない要素があれば M-32、無ければ「該当なし」 |
| unchecked | スコアの限界 | `QUALITY_NOTE[2]` |
| unchecked | 規則の精度 | M-33 |

## 6. F5 `home.py`（新規）— ホームの集計

| 関数 | 引数 → 戻り値 | 内容 | ID |
|---|---|---|---|
| `build(reviews: list[dict], me: str) -> dict` | 6.1 の JSON | 現行 `home()` の集計を移し、追加分を足す | SCR-06-01・FR-06-101・102 |
| `awaiting_answers(review) -> int` | 件数 | BD 6 章の定義 | SCR-06-01 |
| `average_quality(summaries: list[dict]) -> dict` | `{"overall": int\|None, "items": {k: {"score": int\|None, "label": str}}, "n_reviews": int, "n_scored": int}` | `None` を除いた平均（四捨五入） | FR-06-101・102 |
| `next_actions(reviews, me) -> tuple[list[dict], str]` | （項目, `"mine"`\|`"active"`） | BD 6 章の優先順・最大 5 件・同順位は期限の早い順（期限なしは最後） | SCR-06-01 |

### 6.1 `GET /api/docverify/home` の応答（固定。★は追加）

```json
{
  "me": "山田",
  "mine": [{"review_id": "…", "review_name": "…", "role": "reviewer", "done": false, "phase": "individual", "due": null}],
  "active": [{"review_id": "…", "review_name": "…", "phase": "triage", "due": null, "findings": 12,
              "quality_overall": 62, "open": 3, "open_critical": 1, "candidates": 4,
              "updated_at": "…", "versions": 2, "document_name": "基本設計書.docx"}],
  "counts": {"mine": 1, "active": 2, "open_findings": 3, "open_critical": 1, "awaiting_answers": 5},
  "quality": {"overall": 70, "items": {"unambiguous": {"score": 58, "label": "曖昧でない"}}, "n_reviews": 2, "n_scored": 2},
  "next_actions": [{"review_id": "…", "review_name": "…", "kind": "critical", "view": "triage", "label": "重大な指摘 2 件に対応する"}],
  "next_scope": "mine"
}
```

★: `active[]` の `quality_overall`〜`document_name`、`counts.awaiting_answers`、`quality`、`next_actions`、`next_scope`。`updated_at` が無い旧 JSON は `created_at` を入れる。

`next_actions[].kind` と `view`・`label`（固定）:

| kind | 条件 | view | label |
|---|---|---|---|
| `critical` | 未対応の重大 > 0 | `triage` | `重大な指摘 {n} 件に対応する` |
| `candidates` | 未検討の候補 > 0 | `triage` | `未検討の候補 {n} 件を仕分ける` |
| `answers` | 回答待ち > 0 | `questions` | `回答待ちの質問 {n} 件の回答を取り込む` |
| `my_review` | 自分がレビュアーで `done` が偽 | `read` | `自分の確認を終える` |
| `no_document` | 文書なし | `plan` | `文書を取り込む` |
| `ready_to_close` | `exit_ok` かつ未終了 | `gate` | `出口基準を満たしました。判定して終える` |

## 7. F6 `routes/doc_verify.py`（変更）

| 関数 | 変更 | エラー | ID |
|---|---|---|---|
| `upload_document(iid)` | ①`versions = metrics.freeze_current(insp)`（旧の断片・指摘で確定）②新しい版の記録 `entry` に `"quality": metrics.quality_brief(<新しい insp>, False)` ③`document` は ingest の `unread` をそのまま保存 | 現行どおり | FR-06-015・104 |
| `close(iid)` | `{**insp, "status": "closed", "versions": metrics.freeze_current(insp)}` を保存 | 現行どおり | FR-06-104 |
| `home()` | `home.build(_all_full(), current_user())` を返す | 現行の 500 文（M-40） | SCR-06-01 |
| `report_xlsx(iid)` | `metrics.to_xlsx` を try で包む。失敗は `log.exception` と 500 `{"error": M-41}` | 404（現行）・500 | FR-06-075・NFR-06-16 |

## 8. 画面

### 8.1 F7 `templates/doc_verify.html`

| 追加 | DOM（固定） | ID |
|---|---|---|
| 新規ボタン | サイドバーの `app-nav` の直前に `<button type="button" class="btn-primary sidebar-primary-action" id="dv-new-review">＋ 新しいレビュー</button>` | SCR-06-01 |
| 失敗帯 | 現行 `#dv-banner`（role=alert）を維持 | SCR-06-22 |
| モーダル | `<dialog class="dv-modal" id="dv-modal" aria-labelledby="dv-modal-title"><h2 class="dv-modal-title" id="dv-modal-title"></h2><div class="dv-modal-body" id="dv-modal-body"></div><div class="dv-modal-actions"><button type="button" class="b" data-modal="cancel"></button><button type="button" class="b p" data-modal="ok"></button></div></dialog>` を `</main>` の直前に置く | SCR-06-25 |

### 8.2 F8 `templates/docverify/_global.html`（ホームを作り替え）

`#dvgHomeCounts`・`#dvgHomeMine`・`#dvgHomeActive` を削除し、次に置き換える（他の view は変更しない）。旧 id を参照するテストは同じ PR で直す。

```html
<section class="dv-view" data-view="home" hidden>
  <section class="dash-hero"><div class="dash-hero-main">
    <h2 class="dash-hero-title">仕様書を検証して、指摘と質問票を作る</h2>
    <p class="dash-hero-sub">要件定義書・設計書を読み込み、ISO/IEC/IEEE 29148 の品質特性で曖昧さ・抜け・検証できない記述を洗い出します。</p>
    <button type="button" class="btn-primary dash-hero-start" id="dvgHeroStart">検証を始める</button>
    <div class="dash-hero-steps">（取り込み→自動検出→仕分け→質問票→判定 の 5 段。dash-hero-step / dash-hero-arrow）</div>
  </div></section>
  <div class="dashboard-section-head">
    <div><h2 class="dash-section-title">レビュー</h2><p class="dashboard-section-copy">進行中のレビューと品質スコアを確認できます。</p></div>
    <div class="dashboard-section-actions"><button type="button" class="btn-outline-sm" id="dvgHomeReload">再読み込み</button><button type="button" class="btn-outline-sm" id="dvgHomeNew">＋ 新しいレビュー</button></div>
  </div>
  <div class="stat-cards" id="dvgHomeStats" aria-live="polite"></div>
  <div class="dv-grid2">
    <section class="dv-card" id="dvgHomeQuality"></section>
    <section class="dv-card" id="dvgHomeTodo"></section>
  </div>
  <div class="dv-tscroll" id="dvgHomeTable"></div>
</section>
```

### 8.3 F9 `static/js/docverify-core.js`（共通部品）

`window.DV` に追加する（既存の公開名は変えない）。

| 名前 | 引数 → 戻り値 | 内容 | ID |
|---|---|---|---|
| `DV.busy(btn, p, label)` | `Promise` | `p` は Promise か関数。実行中は `disabled`・`aria-busy="true"`・文言を `label` に。`btn.dataset.busy==="1"` の間は 2 回目を無視して同じ Promise を返す。終わったら元の文言に戻す | SCR-06-21 |
| `DV.modal(opt)` | `Promise<boolean>` | `opt={title, html, ok, cancel}`。`ok` が null なら OK ボタンを隠す。`showModal()`・Esc（`cancel` 事件）で false・Tab/Shift+Tab をモーダル内で循環・閉じたら開いた時の `document.activeElement` へ `focus()`。開いた直後は OK（無ければ取りやめ）へフォーカス | SCR-06-25 |
| `DV.download(path, filename)` | `Promise` | `fetch`→失敗時は JSON の `error` を `banner()`（無ければ `NET_ERR`）→成功時は Blob を `a[download]` で保存 | FR-06-075・SCR-06-22 |
| `DV.emptyFindings(n)` | `string` | M-50 | SCR-06-23 |
| `DV.scoreText(v)` | `string` | `null`/`undefined` は `—`、それ以外は整数の文字列 | FR-06-102 |
| `DV.scoreClass(v)` | `string` | `null`→`is-none`、`<60`→`is-bad`、`<80`→`is-warn`、それ以外 `''` | FR-06-100 |
| `DV.scoreBar(v, label)` | HTML | `<span class="dv-score-bar" role="img" aria-label="{label} {text}"><i class="{class}" style="width:{v}%"></i></span>`（`null` は幅 0） | FR-06-100 |
| `DV.keyOpen(root)` | なし | `root` 内の `[data-key-open]` に `tabindex="0"` を付け、Enter / Space で `click()` を発火 | NFR-06-18 |
| `DV.NO_SCORE` | 定数 | M-13 | FR-06-102 |
| `api()` の `raw` | 変更 | `!res.ok` のとき JSON の `error` を読んで `banner()` に出す（現行は常に NET_ERR） | NFR-06-16 |

### 8.4 F10 `static/js/docverify-global.js`（ホーム）

| 関数 | 入力 → 出力 | DOM・クラス | ID |
|---|---|---|---|
| `renderHome(d)` | 6.1 の JSON → なし | 下 4 関数で `#dvgHomeStats`・`#dvgHomeQuality`・`#dvgHomeTodo`・`#dvgHomeTable` を描き、`DV.keyOpen` を掛ける | SCR-06-01 |
| `homeStats(d)` | → HTML | `.stat-card[data-stat=active|critical|answers|quality]` ×4。`stat-card-head`/`stat-card-label`/`stat-card-num`/`stat-card-sub`。重大 > 0 は `.stat-card.is-warn`。品質の sub は「算出できた {n_scored} 件の平均」／`null` は num `—`・sub M-13 | SCR-06-01・FR-06-101・102 |
| `homeQuality(q)` | → HTML | `h3`「特性別の品質スコア」・`p.sub`・`.dv-qrow`×8（`span.dv-ellipsis` 名前・`DV.scoreBar`・`b`）。スコアの低い順、`null` は最後。`n_scored=0` は M-13 の 1 行だけ | FR-06-101・102 |
| `homeTodo(list, scope)` | → HTML | `h3`「次にやること」・`p.sub`（scope=mine「自分の担当から」／active「進行中のレビューから」）・`ul.dv-todo > li > span.dv-ellipsis + button.dv-link[data-review][data-view]`。0 件は M-51 | SCR-06-01 |
| `homeTable(active)` | → HTML | `table.data.dashboard-table`。列: 文書・工程（`span.dv-stage`）・品質スコア（`span.dv-score` = bar＋数）・未対応（`td.num`、重大 > 0 は `span.dv-sev.c`）・更新・操作（`button.btn-outline-sm`「開く」）。行 `tr[data-id][data-key-open]`、文書名は `td.site-cell > span.dv-ellipsis[title]`、版 > 1 は `span.diff-badge`「改版あり」。0 件は M-52 | SCR-06-01・26 |
| `startNew()` | なし | `DV.show('reviews')` の後 `#dvgNewForm [name=name]` へフォーカス。`#dv-new-review`・`#dvgHeroStart`・`#dvgHomeNew` に掛ける | SCR-06-01 |
| `reviewTable`・`loadFindings`（現行） | 変更 | 行に `data-key-open` を付ける | NFR-06-18 |
| 新規作成フォーム（現行） | 変更 | `DV.busy(btn, …, '文書を読み取り中…')` に置き換え。失敗時は `form.reset()` しない | SCR-06-21・22 |

### 8.5 F11 `static/js/docverify-review.js`（文書を読む・判定と記録）

| 関数 | 入力 → 出力 | DOM・クラス | ID |
|---|---|---|---|
| `docBand(r, s)` | inspection・summary → HTML | `div.dvr-docband`: `strong.dv-ellipsis[title]` 名前・`span.chip` 形式・`span` 「{n} 断片」・`span`「版 {v}」・`p.dv-unread`（`s.unread_lines` を 1 行ずつ。読んでいない要素を含む行は `.is-warn`） | FR-06-015・SCR-06-04 |
| `scoreBand(q)` | `summary.quality` → HTML | `div.dv-scoreband`: `div.dv-score-big`（`DV.scoreText`）・`ul.dv-mini > li`×8（label・`DV.scoreBar`）・`button.dv-link[data-act=score-help]`「スコアの意味」。`overall=null` は M-13 の 1 行 | FR-06-100・102・103 |
| `qualityTable(q)` | → HTML | `div.dvr-quality > table.dv-t`（特性・スコア・未解決）。同上の「スコアの意味」 | FR-06-100 |
| `historyTable(h)` | `summary.history` → HTML | `div.dvr-history > table.dv-t`（版・文書名・取り込み日・総合・状態「確定」/「現在」）。0 件は M-53 | FR-06-104 |
| `scopeTables(sc)` | `summary.scope` → HTML | `div.dvr-scope` に `h3`「検査した範囲」「検査していないこと」と `table.dv-t`（項目・内容）。value が「未検証」「未測定」で始まる行は `span.dv-unverified` を前置 | FR-06-075・NFR-06-08 |
| `showScoreHelp(q)` | → Promise | `DV.modal({title:'スコアの意味', html: q.note を p で 3 つ, ok:null, cancel:'閉じる'})` | FR-06-103・SCR-06-25 |
| `confirmClose()` | → `Promise<boolean>` | `DV.modal({title:'レビューを終えますか', html:M-54, ok:'終える', cancel:'取りやめる'})` | SCR-06-25 |
| `renderRead(view)` | 変更 | 本文の上に `docBand`＋`scoreBand`。本文の行 `.ln` に `data-key-open`・`role="button"`。0 件の文を `DV.emptyFindings(ps.length)` に | SCR-06-04・23・NFR-06-18 |
| `renderGate(view)` | 変更 | KPI の後に `qualityTable`・`historyTable`、理由の後に `scopeTables`。報告は `button.b[data-act=report]` → `DV.busy(b, DV.download(base()+'/report.xlsx', 'inspection-{id}.xlsx'), '報告を作成中…')`。終了は `confirmClose()` が true のときだけ POST。インラインの `style` を `.dv-err-text`・`.dvr-gap` に置き換え | SCR-06-08・21・25 |
| `busy()`（内部・現行） | 変更 | `DV.busy` へ委ねる | SCR-06-21 |
| `body.onclick` の `data-act=score-help` | 追加 | `showScoreHelp(E().state.summary.quality)` | FR-06-103 |

### 8.6 F12 `static/css/docverify.css`（追加クラス。値は tokens の変数のみ）

| クラス | 主な指定 | ID |
|---|---|---|
| `.dv-grid2` | `display:grid; grid-template-columns:1fr 1fr; gap:var(--space-4)` | SCR-06-01・24 |
| `.dv-card` | 背景 `--color-surface`・枠 `--color-border` | SCR-06-01 |
| `.dv-qrow` | grid `96px 1fr 40px`。`b` は右寄せ・tabular-nums | FR-06-101 |
| `.dv-score`・`.dv-score-bar`・`> i` | 棒の地 `--color-surface-2`、塗り `--color-primary` | FR-06-100 |
| `.dv-score-bar > i.is-warn`／`.is-bad`／`.is-none` | `--color-medium`／`--color-critical`／幅 0 | FR-06-100・102 |
| `.dv-stage`・`.dv-stage.is-done` | 地 `--color-primary-light`・文字 `--color-primary-dark`／地 `--color-low-bg`・文字 `--color-text`（`--color-low` は文字に使わない。白地で 4.5:1 未満） | NFR-06-18 |
| `.stat-card.is-warn` | 左枠 `--color-critical` | SCR-06-01 |
| `.dv-todo`・`li`・`.dv-link` | 罫線 `--color-divider`。`.dv-link` は枠なしボタン・文字 `--color-primary-dark`・下線は hover/focus | SCR-06-01 |
| `.dv-tscroll` | `overflow-x:hidden`。表は `table-layout:fixed`・セルは省略 | SCR-06-20・24 |
| `.dv-ellipsis` | `display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:0` | SCR-06-26 |
| `.dvr-docband`・`.dv-unread`・`.dv-unread .is-warn` | 地 `--color-surface-2`。警告行は文字 `--color-text`・左印 `--color-medium` | FR-06-015 |
| `.dv-scoreband`・`.dv-score-big`・`.dv-mini` | 大きな数 `--text-xl`、8 特性は 4 列 grid | FR-06-100 |
| `.dvr-quality`・`.dvr-history`・`.dvr-scope`・`.dvr-gap` | 区画の間 `--space-3` | SCR-06-08 |
| `.dv-unverified` | 地 `--color-medium-bg`・文字 `--color-text` | NFR-06-08 |
| `.dv-err-text` | 文字 `--color-critical` | SCR-06-22 |
| `.dv-modal`・`::backdrop`・`-title`・`-body`・`-actions` | 地 `--color-surface`・影 `--shadow-lg`・最大幅 560px・本文は内側スクロール | SCR-06-25 |
| `[aria-busy="true"]` | `cursor:progress` | SCR-06-21 |
| `[data-key-open]:focus-visible`・`.dv-link:focus-visible` | `outline:2px solid var(--color-primary)` | NFR-06-18 |

## 9. 利用者向けの文（NFR-06-16。ここ以外の文を足さない）

| ID | 使う場所 | 文 |
|---|---|---|
| M-01 | 読んでいない要素 | `{画像 n・コメント n・図形 n（0 の種類は省く）} は読んでいません。` 例「画像 3・コメント 2 は読んでいません。」 |
| M-02 | 非表示の要素 | `{非表示シート n・非表示の行・列 n} は読み取りました（画面では見えない内容です）。` |
| M-03 | 全 0 | `読めなかった要素はありません。` |
| M-04 | `unread` 無し（旧 JSON） | `読めなかった要素は数えていません。文書を取り込み直すと数えます。` |
| M-05 | `scanned: False` | `読めなかった要素を数えられませんでした。画像やコメントが無いか、元の文書で確かめてください。` |
| M-10 | スコアの説明 1 | `スコアは、未解決の指摘（候補・採用）が無い断片の割合を 0〜100 で示します。` |
| M-11 | スコアの説明 2 | `式は 100 ×（1 − 未解決の指摘がある断片数 ÷ 断片数）です。` |
| M-12 | スコアの説明 3 | `指摘が無い特性も 100 になるため、文書の内容が正しいことや、検査の網羅性は示しません。` |
| M-13 | スコアなし | `— 文書を取り込むと表示されます。` |
| M-20 | 文書なし | `文書はまだ取り込まれていません。` |
| M-21 | 参加者なし | `参加者が登録されていません。計画の画面で登録できます。` |
| M-22 | チェックリスト未選択 | `観点チェックリストを使っていません。` |
| M-30 | 網羅性 | `未検証。見つかった指摘は検出規則と人の確認の範囲に限られ、ほかに欠陥が無いことは示しません。` |
| M-31 | 意味の正しさ | `未検証。記述が業務として正しいかは判断していません。` |
| M-32 | 読めなかった中身 | `{画像 n・コメント n・図形 n} の中身は検査していません。` |
| M-33 | 規則の精度 | `未測定。規則ごとの適合率・再現率はまだ測っていません。` |
| M-40 | ホーム 500（現行） | `ホームを読めませんでした。時間をおいて再読み込みしてください。` |
| M-41 | 報告 500 | `報告を作れませんでした。もう一度出力してください。` |
| M-50 | 指摘 0 件 | `確認した範囲では指摘はありません。{n} 断片を確認しました。網羅性は未検証です。` |
| M-51 | 次にやること 0 件 | `いまやることはありません。` |
| M-52 | 進行中 0 件 | `進行中のレビューはありません。「＋ 新しいレビュー」から始められます。` |
| M-53 | 版 0 件 | `まだ版がありません。文書を取り込むと記録されます。` |
| M-54 | 終了確認 | `終えると判定と記録が確定します。指摘の状態はこのあとも変えられます。` |

禁止の確認: 上の文に実装語・パス・例外名・HTTP コード・「（任意）」が無いこと（IT-14）。

## 10. 報告 xlsx（F4 `to_xlsx`）

| シート | 変更 | 内容 | ID |
|---|---|---|---|
| 指摘一覧 | なし | 現行 | — |
| 集計 | 追加 | 末尾に `版 {v} の品質スコア` 行を `history` の数だけ（`None` は `—`） | FR-06-104 |
| **検査した範囲**（新規・3 枚目） | 新規 | 1 行目見出し `区分`・`項目`・`内容`。続けて `scope.checked` を区分「検査した範囲」、`scope.unchecked` を区分「検査していないこと」で 1 行ずつ。列幅 A=18・B=24・C=80、C は折り返し。全セルを現行 `_safe()` に通す | FR-06-075・NFR-06-08 |

## 11. キーボード操作（NFR-06-18）

| 画面 | キー | 動作 |
|---|---|---|
| 共通 | Tab / Shift+Tab | サイドバー → 新しいレビュー → 本文の順に移る。フォーカスは `:focus-visible` の枠で見える |
| ホーム | Enter / Space（表の行・次にやること） | 該当レビューの該当画面を開く |
| 一覧・指摘一覧 | Enter / Space（行） | 行を開く |
| 文書を読む | Enter / Space（本文の行） | 指摘の追加欄を開く。追加欄は Tab で入力し Enter で追加 |
| 判定と記録 | Enter（報告・終える・スコアの意味） | ボタンの動作 |
| モーダル | Esc | 閉じて開いた要素へフォーカスを戻す |
| モーダル | Tab / Shift+Tab | モーダル内のボタンを循環（外へ出ない） |

## 12. テスト観点（受入基準から導出）

### 12.1 単体（UT。pytest／JS は Playwright の evaluate）

| ID | 対象 | 入力（G） | 期待（T） | 由来 |
|---|---|---|---|---|
| UT-06R1-01 | `unread.scan` xlsx | 画像 3・セルコメント 2 | images 3・comments 2・scanned 真 | FR-06-015 |
| UT-06R1-02 | 同 | 非表示シート 1・非表示列 2・非表示行 1 | hidden_sheets 1・hidden_cols 3 | FR-06-015 |
| UT-06R1-03 | 同 | グラフ 1・文字なし図形 1・文字あり図形 1 | shapes 2 | FR-06-015 |
| UT-06R1-04 | 同 docx | 画像 2・コメント 1・SmartArt 1 | 2・1・shapes 1 | FR-06-015 |
| UT-06R1-05 | 同 pdf | 注釈 1・リンク 1・画像 1 | comments 1・images 1（実データで確認） | FR-06-015 |
| UT-06R1-06 | 同 md | `![a](b)` 2 個 | images 2 | FR-06-015 |
| UT-06R1-07 | 同 | 壊れた zip・DOCTYPE 入り XML | 例外なし・全 0・scanned 偽 | FR-06-015 |
| UT-06R1-08 | `unread.lines` | images 3・comments 2 | `["画像 3・コメント 2 は読んでいません。"]` | FR-06-015 |
| UT-06R1-09 | 同 | 全 0／None 相当／scanned 偽／非表示のみ | M-03／M-04（metrics 側）／M-05／M-02 | FR-06-015 |
| UT-06R1-10 | `ingest.ingest` | 正常な xlsx | `document` のキーが 5 つ、`unread` に KEYS＋scanned | FR-06-015 |
| UT-06R1-11 | `store.save` | 任意の insp | 戻り値と保存内容に updated_at、引数は不変 | SCR-06-01 |
| UT-06R1-12 | `metrics.quality` | 10 断片中 2 断片に未解決 | overall 80、各 items に label | FR-06-100 |
| UT-06R1-13 | 同 | 断片 0 | overall None・全 score None（0 でない） | FR-06-102 |
| UT-06R1-14 | 同 note | — | 3 文、式と「正しいこと」「網羅性」を含む | FR-06-103 |
| UT-06R1-15 | `metrics.history` | 版 1 確定 60・版 2 現在 80 | overall [60, 80]、版 2 だけ current 真 | FR-06-104 |
| UT-06R1-16 | 同 | quality 無しの旧版 | overall None | FR-06-104 |
| UT-06R1-17 | `freeze_current` | 版 2 つ | 最後だけ final 真、入力は不変、空なら [] | FR-06-104 |
| UT-06R1-18 | `metrics.scope` | 任意 | unchecked に網羅性「未検証。…」・意味の正しさ・規則の精度「未測定。…」 | FR-06-075・NFR-06-08 |
| UT-06R1-19 | `to_xlsx` | 任意 | シート「検査した範囲」、網羅性の C 列が「未検証」で始まる、集計に版ごとの行 | FR-06-075・104 |
| UT-06R1-20 | 同 | 先頭 `=` の文 | `'` で始まる（現行の回帰） | 現行 |
| UT-06R1-21 | `home.average_quality` | 進行中 2 件（80・60） | overall 70 | FR-06-101 |
| UT-06R1-22 | 同 | 算出できる 0 件 | overall None・n_scored 0 | FR-06-102 |
| UT-06R1-23 | `home.awaiting_answers` | 要確認未回答 2・回答済み 1・却下 1 | 2。終了済みレビューは build で数えない | SCR-06-01 |
| UT-06R1-24 | `home.next_actions` | 重大・候補・回答待ちを含む 7 件 | 優先順どおり 5 件、参加なしなら scope active | SCR-06-01 |
| UT-06R1-25 | `home.build` | 現行と同じ入力 | mine・active の既存キーと counts 既存 4 キーが不変 | 回帰 |
| UT-06R1-26 | `DV.scoreText`・`scoreClass` | null・59・60・79・80 | `—`・is-bad・is-warn・is-warn・'' | FR-06-100・102 |
| UT-06R1-27 | `DV.emptyFindings` | 12 | M-50 で 12 断片 | SCR-06-23 |
| UT-06R1-28 | `DV.busy` | 解決前に 2 回呼ぶ | 関数の実行 1 回、終了後に文言が戻る | SCR-06-21 |

### 12.2 結合（IT。Flask テストクライアント＋Playwright MCP で実機）

| ID | 経路 | G / W / T | 由来 |
|---|---|---|---|
| IT-06R1-01 | 取り込み→保存→文書を読む | G 画像 3・コメント 2 の xlsx W 取り込む T 応答の unread_lines と文書の帯に「画像 3・コメント 2 は読んでいません」、JSON に document.unread | FR-06-015・SCR-06-04 |
| IT-06R1-02 | 2 回取り込み→判定 | G 版 1 で 60 W 指摘を解決し版 2 を取り込む T versions[0].quality.final 真、判定の推移に 2 版の値 | FR-06-104 |
| IT-06R1-03 | 終了 | G 出口基準を満たす W 確認モーダルで「終える」 T 最後の版が確定、取りやめなら POST なし | FR-06-104・SCR-06-25 |
| IT-06R1-04 | ホーム API→画面 | G 進行中 2 件（80・60） W ホーム T カード「70」、特性別 8 行、表 2 行 | FR-06-101・SCR-06-01 |
| IT-06R1-05 | 未取り込み | G 文書なし W 文書を読む・判定・ホームを開く T 「—」と案内 1 行、0 の表示なし | FR-06-102 |
| IT-06R1-06 | スコアの説明 | G 判定 W 「スコアの意味」 T 3 文以内、Esc で閉じボタンにフォーカス | FR-06-103・SCR-06-25 |
| IT-06R1-07 | 報告 | G 任意 W 報告を出力 T xlsx に「検査した範囲」、網羅性「未検証」、規則の精度「未測定」 | FR-06-075・NFR-06-08 |
| IT-06R1-08 | 報告の失敗 | G to_xlsx が失敗 W 出力 T 500 と M-41、赤い帯、ボタンが戻る | SCR-06-22・NFR-06-16 |
| IT-06R1-09 | 二重送信 | G 取り込み中 W ボタンを 2 回押す T POST 1 回、文言「文書を読み取り中…」 | SCR-06-21 |
| IT-06R1-10 | 失敗時の入力保持 | G API が 400 W 新規作成 T 帯が出てレビュー名が残る | SCR-06-22 |
| IT-06R1-11 | 0 件 | G 候補 0 W 文書を読む T M-50 と断片数 | SCR-06-23 |
| IT-06R1-12 | 長文 | G 200 字の名前 W ホーム・一覧・文書の帯 T 1 行で省略、title に全文 | SCR-06-26 |
| IT-06R1-13 | キーボード | G 主要導線 W Tab と Enter だけ T 作成→文書を読む→判定まで通る | NFR-06-18 |
| IT-06R1-14 | 文言 | G 全エラー経路 W 画面の文 T パス・例外名 0 件、次の行動 1 行 | NFR-06-16 |
| IT-06R1-15 | 互換 | G unread・quality・updated_at の無い旧 JSON W 全 API・3 画面 T 200、M-04 と「—」 | 互換 |
| IT-06R1-16 | 次にやること | G 重大 1 件のレビュー W 項目を Enter T そのレビューの指摘の検討 | SCR-06-01 |

### 12.3 システム（ST）

| ID | 内容 | 合格 | 由来 |
|---|---|---|---|
| ST-06R1-01 | 3 画面と既存画面を 1280×720 で全状態（通常・実行中・失敗・0 件・モーダル・長文）を開き、最下部まで撮る。`scripts/check_clipping.py` | 見切れ 0・`scrollWidth ≤ clientWidth` | AC-06-05・SCR-06-20・24 |
| ST-06R1-02 | 追加した文字色と背景のコントラスト（computed style で計算） | 全て 4.5:1 以上 | NFR-06-18 |

## 13. トレース表

| 要件 ID | BD | DD の節 | 実装ファイル | テスト |
|---|---|---|---|---|
| FR-06-015 | 3.2・5 | 2・3・5.1・8.5・9 | F1・F2・F4・F6・F11 | UT-01〜10・IT-01・15 |
| FR-06-075 | 3.3・4 | 5.3・8.5・10 | F4・F6・F11 | UT-18・19・IT-07 |
| FR-06-100 | 3.2・3.3 | 5.1・8.3・8.5 | F4・F9・F11 | UT-12・26・IT-04 |
| FR-06-101 | 3.1・6 | 6・8.4 | F5・F10 | UT-21・IT-04 |
| FR-06-102 | 1・3 | 5.1・6・8.3〜8.5・9 | F4・F5・F9〜F11 | UT-13・22・26・IT-05 |
| FR-06-103 | 3.2・3.3 | 5.1・8.5・9 | F4・F11 | UT-14・IT-06 |
| FR-06-104 | 3.3・5 | 5.1・5.2・7・8.5・10 | F4・F6・F11 | UT-15〜17・19・IT-02・03 |
| SCR-06-01 | 3.1 | 6・8.1・8.2・8.4 | F5〜F8・F10・F12 | UT-11・21〜25・IT-04・16 |
| SCR-06-04 | 3.2 | 8.5 | F11・F12 | IT-01 |
| SCR-06-08 | 3.3 | 8.5・10 | F11・F12 | IT-02・07 |
| SCR-06-20 | 7 | 8.6 | F12 | ST-01 |
| SCR-06-21 | 7 | 8.3・8.4・8.5 | F9〜F11 | UT-28・IT-09 |
| SCR-06-22 | 7 | 7・8.3・8.4 | F6・F9・F10 | IT-08・10 |
| SCR-06-23 | 7 | 8.3・8.5・9 | F9・F11 | UT-27・IT-11 |
| SCR-06-24 | 7 | 8.6 | F12 | ST-01 |
| SCR-06-25 | 7 | 8.1・8.3・8.5・11 | F7・F9・F11・F12 | IT-03・06 |
| SCR-06-26 | 7 | 8.4・8.6 | F10・F12 | IT-12 |
| NFR-06-08 | 3.3 | 5.3・8.5・10 | F4・F11 | UT-18・IT-07 |
| NFR-06-16 | 8 | 7・8.3・9 | F6・F9 | IT-08・14 |
| NFR-06-18 | 7 | 8.3・8.6・11 | F9〜F12 | IT-13・ST-02 |
| AC-06-05 | 7 | 12.3 | 全画面 | ST-01 |

（テスト ID は `UT-06R1-` / `IT-06R1-` / `ST-06R1-` の接頭辞を表内で省略）
