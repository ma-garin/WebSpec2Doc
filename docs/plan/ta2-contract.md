# テスト自動化（System 02）採用契約書 — TA2

承認済みデザイン: `docs/plan/design-ideas/prototype-visual-editor.html`（**この見た目・操作を製品化する。独自解釈で変えない**）
状態: 実装中（2026-08-30）。担当は全員この文書だけを正とする。不明点は推測せず、本文書に無い場合は最も単純な実装を選び、完了報告に「契約外の判断」として書く。

## 0. 全員共通の絶対ルール

- **禁止語**: 「準備中」「未実装」「Coming soon」を UI に出さない。作れない機能はボタンごと置かない
- **disabled は理由必須**: 押せないボタンは `title` と隣接テキストで理由を出す。プライマリ配色のまま disabled にしない
- **Jira / TestRail への言及・連携は一切作らない**（ユーザー指示）
- **PC 専用**（1280px 以上）。モバイル対応・レスポンシブは作らない
- **捏造禁止**: 数字はすべて実データ。データが無いときは「未実行」「基準なし」と書く
- 既存の System 01（ドキュメント作成）・AutoRun・CLI には触らない
- `web/routes/test_activity.py` と `tests/test_testcase_*.py` は**触らない**（他が依存）
- pytest は**自分が書いた新規テストファイルだけ**実行してよい（`venv/bin/pytest tests/test_ta2_*.py -q`）。全量 `make test` は走らせない
- サーバ検証は `FLASK_TESTING=1 WEBSPEC2DOC_ALLOW_LOCAL=1 WEBSPEC2DOC_AUTH_MODE=off venv/bin/python app.py`（ポート 8765）。**編集後は再起動が必要**
- 表示データの種: `mkdir -p output/demomart && cp -r docs/demo/sample_output/. output/demomart/`（report.json あり・対象 http://127.0.0.1:8766/ は `cd demo/site && python3 -m http.server 8766`）
- 完了報告は 10 行以内。変更ファイル一覧・未検証項目・契約外の判断 を必ず含める

## 1. 全体構成

```
/test-automation            → templates/test-automation.html（独立シェル。index.html は使わない）
  #/tests/<id>  #/run  #/drift  #/site   （URL ハッシュで画面状態を持つ。?domain=<domain> で対象サイト）
/api/ta2/...                → web/routes/ta2.py（Blueprint "ta2"）
web/services/ta2_store.py   → 永続化と導出ロジック（ルートから呼ぶ。ルートにロジックを書かない）
output/<domain>/ta2/tests.json     テスト定義（scoped_output_dir 経由。テナント対応）
output/<domain>/ta2/drift.json     変更の対応状態（dismissed / applied）
```

旧 12 画面（`/test-activity` ほか `_TESTLAB_VIEWS` 全部）は `/test-automation` へ 302。フロント資産は削除する（§6）。

## 2. データモデル（tests.json）

```jsonc
{
  "version": 1,
  "domain": "demomart",
  "next_seq": 100,
  "tests": [
    {
      "id": "PW-0043",                 // PW- + 4桁。case_id 由来なら TC-xxxx を case_id に保持
      "case_id": "TC-0012",            // 由来のテストケース表の行。無ければ ""
      "screen": "P004",                // report.json screens[].page_id
      "name": "必須項目が空だと送信できない",
      "technique": "同値分割",          // テストケース表の技法列。無ければ "生成" / "手動"
      "source": "table|gap|manual",
      "steps": [
        {"kind":"pre","action":"開く","target":"page","arg":"/checkout.html","loc":"page.goto"},
        {"kind":"act","action":"入力欄を空のままにする","target":"name","arg":"氏名","loc":"input[name=\"name\"]","stab":"high"},
        {"kind":"act","action":"押す","target":"submit","arg":"注文を確定する","loc":"button[name=\"submit_order\"]","stab":"mid",
         "issue":{"type":"missing","msg":"要素が見つからない · 15.0s でタイムアウト","detail":"…","fix":"[data-testid=\"place-order\"]","fix_stab":"high","key":"submit_order"},
         "fixed":false},
        {"kind":"ver","action":"表示される","target":"alert","arg":"必須項目を入力してください","loc":"[role=\"alert\"]","stab":"high"}
      ],
      "status": "pass|fail|flaky|fixed|new|running",
      "history": [1,1,1,0,0,0],        // 1=成功 0=失敗 2=不安定(再試行で回復)。直近 10 件
      "last": {"dur_ms": 15000, "at": "2026-08-29T23:14:05", "step": 3, "run_id": "…", "error": "…"},
      "updated_at": "…"
    }
  ]
}
```

**action の語彙**（これ以外を作らない）: `開く` `入力する` `入力欄を空のままにする` `押す` `選ぶ` `表示される` `含む` `無効になっている` `URL が`
**kind**: `pre`（開く）/ `act` / `ver`
**stab**（ロケータ安定度）: `high` = `[data-testid]` `#id` `[role]` / `mid` = `[name]` `text=` / `low` = CSS パス・nth-child・XPath
**issue.type**: `missing`（要素なし→ロケータ差替）/ `timeout`（待機不足→wait_ms 延長）/ `expect`（期待値差→arg 更新）/ `flaky`（不安定→待機条件+ロケータ差替）

### 2.1 初期導出（tests.json が無いとき）

`web.services.testcase_table_store.compose(domain, report)` の `rows` から作る。行の `actions[]` / `assertions[]` の形は `src/generator/testcase_table.py` と `web/services/testcase_spec_generator.py`（`_action_lines` / `_assertion_lines`）を読んで対応表を作ること。`automation` が「自動化可」以外の行も**取り込む**（status=`new`、実行対象にするかは §3 run 側で `steps` の実行可否で判定）。`run_result.json`（`load_run_result`）があれば `last`/`history`/`status` に反映する。

### 2.2 要素辞書（report.json → elements）

`screens[].forms[].fields[]` から `{key: field.name || element_id, label: placeholder||name, type: field_type, loc: locators[0], stab}` を、`buttons[]` から `{key:"btn_<n>", label, loc:"text=<label>", stab:"mid"}` を、`headings[]` 先頭から `{key:"hero", loc:"h1", stab:"high"}` を作る。`alert` は `[role="alert"]` 固定で常に含める。

## 3. API（すべて JSON。エラーは `{"error": "<日本語の理由>"}` と 4xx。500 を返さない）

| メソッド・パス | 入力 | 出力 |
|---|---|---|
| GET `/api/ta2/sites` | — | `{sites:[{domain, name, screens, tests, fails, last_run_at}]}` report.json を持つドメインのみ |
| GET `/api/ta2/tests?domain=` | — | `{domain, tests:[Test], elements:{P004:{name:{…}}}, screens:[{id,name,path}]}` 無ければ §2.1 で導出して保存 |
| POST `/api/ta2/tests` | `{domain, screen, name?, gap_ids?:[]}` | `{created:[Test]}` gap_ids から生成（§4）。name のみなら `開く` 1 ステップの手動テスト |
| PUT `/api/ta2/tests/<id>` | `{domain, name?, steps?}` | `{test}` 保存。status が pass/fail/flaky なら `fixed` に変える |
| DELETE `/api/ta2/tests/<id>?domain=` | — | `{ok:true}` |
| POST `/api/ta2/tests/<id>/duplicate` | `{domain}` | `{test}` |
| POST `/api/ta2/tests/<id>/fix` | `{domain, step:<index>}` | `{test}` issue.type に応じて loc/arg/wait_ms を書換え `fixed=true` status=`fixed` |
| POST `/api/ta2/run` | `{domain, ids?:[], browser?:"chromium"}` | `{run_id, total}` **非同期**（スレッド）。既に実行中なら 409 |
| GET `/api/ta2/run/status?domain=` | — | `{running, run_id, total, done, passed, failed, current_id, tests:[{id,status,duration_ms,error}]}` |
| POST `/api/ta2/run/cancel` | `{domain}` | `{ok}` |
| GET `/api/ta2/runs?domain=` | — | `{runs:[{run_id, at, passed, failed, total, duration_ms}]}` 直近 30 |
| GET `/api/ta2/artifact?domain=&id=&kind=trace\|screenshot\|report` | — | ファイル送信。無ければ 404 `{error}` |
| GET `/api/ta2/screenshot?domain=&screen=` | — | `output/<domain>/screenshots/<screen>.png` を送る。無ければ 404 |
| GET `/api/ta2/map?domain=` | — | `{screens:[{id,name,path,tests,fails,coverage,gaps:[{id,title,detail,steps:[…]}]}]}` |
| GET `/api/ta2/drift?domain=` | — | `{baseline_at, current_at, items:[{id,kind,screen,title,old,now,impact:[test ids],fix:{loc,stab},state:"open\|applied\|dismissed"}]}` 比較元が無ければ `{items:[], reason:"比較の基準となる前回のクロールがありません"}` |
| POST `/api/ta2/drift/<id>/apply` | `{domain}` | `{applied:[test ids]}` 影響テストの該当 loc を fix に差替え `fixed=true` |
| POST `/api/ta2/drift/<id>/dismiss` | `{domain}` | `{ok}` |
| POST `/api/ta2/recrawl` | `{domain}` | 既存の再クロール API（`web/routes/crawl.py` の recrawl 系）へ委譲。無ければ `{error:"…"}` 501 |

### 3.1 実行の実装

- `ta2_store.to_table_rows(tests)` で `testcase_spec_generator.generate_spec()` が受ける行（`case_id`,`name`,`automation`="自動化可",`actions`,`assertions`）へ変換。**ステップ→actions/assertions の対応は §2.1 の逆**
- `playwright_executor.run_playwright(spec, run_dir(domain), egress_policy=EgressPolicy(allow_local=_local_targets_allowed()), on_proc=…)` を**別スレッド**で呼ぶ。進捗は既存の `_read_progress_ndjson(run_dir/"playwright_progress.ndjson")`
- 完了時: `save_run_result` を呼びつつ、tests.json の `status/history/last` を更新。失敗ステップの特定は error 文中のロケータ文字列と steps[].loc の一致で行い、一致しなければ `step:null`
- issue の自動付与: 失敗テストで `Timeout` かつ `locator` 文言 → `missing`（fix は同画面の要素辞書から**同ラベル**の要素があればその loc、無ければ `null` で「修正案なし」）。`expect` は `Expected … Received …` から。判定できないものは issue 無し（捏造しない）
- キャンセルは既存 `/api/testcases/cancel` と同じく `_RUNNING_PROCS` へ登録して kill

## 4. 穴（gaps）と生成

`screens[].forms[].fields[].test_conditions[]` の各項目を候補にし、同じ screen・同じ target を持つテストが 1 件も無い条件だけを gap にする。`transitions.to` の各遷移先に「URL が <path>」検証を持つテストが無ければ遷移 gap。gap.id は `"<screen>:<field>:<index>"`。生成ステップは `開く` → 条件に応じた `入力する`/`入力欄を空のままにする` → `押す`（フォームの送信ボタン。`buttons[0]`）→ `表示される`（alert）。

## 5. フロントエンド

- **プロトタイプの HTML/CSS をそのまま移植**する（`prototype-visual-editor.html` の `<style>` を `static/css/ta2.css` に、body 構造を `templates/test-automation.html` に）。色・余白・角丸・フォントを変えない。`.idea` バナーと `.proto` 表記は付けない
- JS は `static/js/ta2/` に分割。**グローバル `window.TA2`** で連携する

```js
// state.js が定義（FE-A）
TA2.state   // {domain, tests, elements, screens, sel, step, mode, filter, q, view, run:{running,…}, drift:[], map:[]}
TA2.api     // {sites(), tests(d), create(d,body), update(d,id,body), remove(d,id), duplicate(d,id), fix(d,id,step),
            //  run(d,ids), runStatus(d), cancel(d), runs(d), map(d), drift(d), driftApply(d,id), driftDismiss(d,id), recrawl(d)}
            //  すべて fetch → JSON。error キーがあれば throw new Error(error)
TA2.on(evt, fn) / TA2.emit(evt, payload)   // 'tests' 'select' 'view' 'run' 'drift' 'map' 'toast'
TA2.select(id) / TA2.setView('test'|'run'|'drift'|'site') / TA2.toast(msg, 'ok'|'ng'|'')
TA2.render()   // 全再描画。各モジュールは TA2.on で部分再描画してもよい
```

- ファイル所有: FE-A = `templates/test-automation.html` `static/css/ta2.css` `static/js/ta2/{state,app,list,editor,viewer}.js` / FE-B = `static/js/ta2/{panels,modals}.js`
- 読み込み順: state → list → editor → viewer → panels → modals → app（app.js が `TA2.boot()` を呼ぶ）
- 右ペイン（viewer）: `失敗時` = 直近失敗のスクショ（`/api/ta2/artifact?kind=screenshot`。無ければ「この実行の証跡はありません」）/ `期待` `いま` = report.json から描くワイヤーフレーム（プロトタイプの `pageHTML` 方式。フィールドは要素辞書から動的生成）。要素ハイライトはワイヤーフレーム上の `[data-el]` の実座標から計算（プロトタイプと同じ）
- 実行中は `run/status` を 1 秒ポーリングし、現在ステップを進める。`R` キー・`⌘K`・`↑↓` を実装
- 状態の永続化は URL ハッシュのみ（localStorage は使わない。サーバが正）
- 初回ヘルプモーダルはプロトタイプのまま残す（内容は実装に合わせて更新）

## 6. 配線と撤去（WIRE）

- `web/routes/pages.py`: `GET /test-automation` を追加（`render_template("test-automation.html")`。`_may_use_testlab()` を流用し非管理者は 403）。`_TESTLAB_VIEWS` の各 URL は `/test-automation` へ 302
- `templates/system-select.html`: System 02 カードの href を `/test-automation`、タグを「テスト設計 / コード生成 / 自動テスト実行 / 変更の事前検知 / トレーサビリティ」に
- **削除**: `templates/partials/view-ta-*.html`（12）、`static/js/ta-*.js`（全部）、`static/css/test-activity.css`、`static/css/ta-design-system.css`。`templates/index.html` の include と `<script>`、`templates/partials/nav.html` の `data-system="testlab"` 項目、`static/js/core.js` の `VIEW_HEADER` の TA 12 項目、`static/js/system-scope.js` の testlab 分岐 を取り除く。`grep -rn "view-ta-\|ta-.*\.js\|test-activity.css\|ta-design-system" templates static web` が 0 件になるまで
- `docs/screens/` のカタログは古くなる。README に「System 02 は再構築のため T01〜T12 は旧画面」と 1 行追記
- `web/__init__.py` への Blueprint 登録は BE-B が行う（WIRE は触らない）

## 7. 受入基準（VERIFY が確認する）

1. `/test-automation?domain=demomart` が 200。JS エラー 0。1440×900 で**縦スクロールなし**（一覧と手順欄の内部スクロールは可）
2. 一覧にテストが並び、選択で手順と右ペインが変わる。ステップ選択でハイライトが対象要素へ移る
3. 「このテストを実行」で `run/status` が進み、完了で status/history/last が更新され一覧の点が変わる（対象 http://127.0.0.1:8766 が起動している前提）
4. 赤いステップの「適用」→ 再実行で結果が変わる（DemoMart では実サイトが変わらないため missing は再現しない。**timeout/expect の issue 付与と apply が動くことを API で確認**）
5. 「＋ ステップを追加」→ 右ペインの要素クリック → 追加され PUT が飛ぶ
6. 「＋ 新しいテスト」→ map の gaps が出る → 生成される
7. ▶ 実行と結果 / ◈ 変更 / ⌂ 地図 の各パネルが実データで描画される（drift は基準なしなら理由を表示）
8. 旧 URL `/test-plan` 等が 302 → `/test-automation`。`/systems` のカードから遷移できる
9. `venv/bin/pytest tests/test_ta2_store.py tests/test_ta2_api.py -q` が緑
10. `grep -rn "準備中" templates/test-automation.html static/js/ta2 static/css/ta2.css` が 0 件

## 8. 担当とファイル所有（重なり禁止）

| 担当 | 所有ファイル |
|---|---|
| BE-A | `web/services/ta2_store.py` `tests/test_ta2_store.py` |
| BE-B | `web/routes/ta2.py` `web/__init__.py`（Blueprint 登録 1 行）`tests/test_ta2_api.py` |
| FE-A | `templates/test-automation.html` `static/css/ta2.css` `static/js/ta2/{state,app,list,editor,viewer}.js` |
| FE-B | `static/js/ta2/{panels,modals}.js` |
| WIRE | §6 の全ファイル |
| VERIFY | 書き込みは `docs/plan/ta2-verify.md` のみ |

BE-B は BE-A の関数名を本契約 §2〜§4 から決め打ちで呼ぶ。BE-A が提供する公開関数（この名前で実装すること）:
`load(domain)` `save(domain, data)` `derive_initial(domain, report)` `elements_of(report)` `screens_of(report)` `to_table_rows(tests)` `apply_run_result(domain, result, run_id, at)` `apply_fix(domain, test_id, step_index)` `gaps_of(domain, report, tests)` `generate_from_gaps(domain, report, screen, gap_ids, name)` `drift_items(domain)` `drift_apply(domain, item_id)` `drift_dismiss(domain, item_id)` `duplicate(domain, test_id)` `update_test(domain, test_id, patch)` `delete_test(domain, test_id)`
