# TA2 統合検証 (2026-08-30)

対象: branch `feat/ta2-visual-editor` / `http://127.0.0.1:8765/test-automation?domain=demomart`
検証時刻: 11:38〜11:55 JST。証跡は `.playwright-mcp/` 配下。

> **環境の前提を1件修正した。** 検証開始時、`127.0.0.1:8766` には 8/25 起動の古い WebSpec2Doc プロセス (pid 3742, IPv4 127.0.0.1) が居座り、DemoMart 静的サーバ (pid 88807, `python -m http.server 8766`, IPv6 `*`) を遮蔽していた。`curl http://127.0.0.1:8766/` の `<title>` が `WebSpec2Doc`、`/checkout.html` が 404。この状態で走らせた1回目の実行は全件が「タイトル不一致」で失敗する。pid 3742 を kill 後に DemoMart が応答するようになり、以降の結果はすべて修正後のもの。**製品の不具合ではないが、この踏み台を踏むと「実装が壊れている」と誤診する。**

---

## 結果一覧（§7 の番号ごとに PASS/FAIL + 1行証拠）

| # | 判定 | 証拠 |
|---|---|---|
| §7-1 | **FAIL（条件付き）** | 200 / `scrollHeight=900`（1440×900・縦スクロールなし）は OK。だが失敗テストを選ぶと console に `Failed to load resource: the server responded with a status of 400 (BAD REQUEST)` が 2 件出る（`/api/ta2/artifact` 起因・下記 B-1）。失敗ゼロの初期ロードでは 0 件 |
| §7-2 | PASS | PW-0001 / PW-0009 / PW-0034 / PW-0035 で手順と右ペインが切替わる。PW-0035 の手順2を押すと `#hl` が `x903,y487,490×34` へ移動し、対象 `[data-el="card_number"]` の `x905,y489,484×28` にほぼ一致（`ta2-hl.png`）。※「失敗時」タブでは `#hl` が `hide` のまま＝仕様どおり。フォームなし画面（P001）は手順の対象が `page/title/text` のためハイライト対象が無く、正しく非表示 |
| §7-3 | **FAIL（部分）** | 単体実行は完走（PW-0001: `running:false`, `status:new→pass`, `history:[0,1]`, `last.at=11:43:40`, 一覧の点も緑化）。だが**全件実行が 125 件中 123 件しか実行されず、2 件が黙って消える**（下記 B-3）。全件: 26.2s / passed 122 / failed 1 / 未実行 2。`/tmp/ws2d.log` に実行由来の traceback は無し（traceback 12 件はすべて `/api/ta2/artifact` の B-1） |
| §7-4 | **FAIL** | issue の自動付与は動く（`type:"missing"`, `msg:"要素が見つからない"`, `key:"btn_x"`, `fix:null`）。しかし `POST /api/ta2/tests/PW-0127/fix` が **400** `{"error":"処理に失敗しました。サーバーのログを確認してください。"}`（下記 B-2）。再実行しても `fixed:false` のまま。加えて `last.step` が常に `null` で、赤い手順を `last` から特定できない |
| §7-5 | PASS | 「＋ ステップを追加」→ `#page [data-el="cvc"]` クリック→ popover（入力する／入力欄を空のままにする／表示される／やめる／ステップに追加）→「ステップに追加」で `PUT /api/ta2/tests/PW-0035` が 1 回発行。手順 8→9 に増え、リロード後も 9 のまま |
| §7-6 | PASS（限定） | 「＋ 新しいテスト」→ P007 選択→ `POST /api/ta2/tests` → `PW-0128` 生成・自動選択、リロード後も存在（126 件）。ただし**全 7 画面で gap が 0 件**のため gap 一覧は「この画面に、まだテストされていない箇所は見つかりませんでした」しか出せず、gap 由来の生成経路は未実証 |
| §7-7 | **FAIL（部分）** | ▶ は KPI（成功2/失敗0/不安定0/未実行123）と 125 行の表を実データで描画。⌂ は 7 画面すべて `網羅` (`tests/(tests+gaps)`＝gaps 0 なので 100%) で API の `map` と一致。**◈ が誤った理由を表示**：API は `reason:"比較の基準となる前回のクロールがありません"` を返すのに、画面は「前回のクロールとの差分はありません」（＝差分なしと断言）と出す（下記 B-4） |
| §7-8 | PASS | `/test-plan` `/test-design` → 302 `http://127.0.0.1:8765/test-automation`。`templates/system-select.html:65` の card href が `/test-automation`。`/dashboard` 200・console error 0、`/auto-run` 200・console error 0。`grep -rn "view-ta-\|ta-design-system\|test-activity.css" templates static web` = 0 件 |
| §7-9 | PASS | `venv/bin/pytest tests/test_ta2_store.py tests/test_ta2_api.py -q` → `81 passed in 1.23s` |
| §7-10 | PASS | `grep -rn 準備中 templates/test-automation.html static/js/ta2 static/css/ta2.css` = 0 件 |

**PASS 6 / FAIL 4**

---

## 壊れている箇所（重大度順）

### B-1【重大】証跡 API が常に 400 を返す（右ペイン「失敗時」が永久に空）

- **症状**: `GET /api/ta2/artifact?domain=demomart&kind=report|screenshot|trace` が、実ファイルが存在しても **400** `{"error":"処理に失敗しました。サーバーのログを確認してください。"}`。UI 側は console error になり §7-1 を落とす。契約が定める 404「この実行の証跡はありません」にも到達しない。
- **再現**: 失敗するテストを 1 件実行 → `curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8765/api/ta2/artifact?domain=demomart&kind=report"` → `400`。ファイルは `output/demomart/testcases/playwright-report/index.html` に存在。
- **証拠**（`/tmp/ws2d.log`）:
  ```
  File "/Users/…/webspec2doc/web/routes/ta2.py", line 490, in api_ta2_artifact
      return send_file(str(target))
  FileNotFoundError: [Errno 2] No such file or directory:
    '/Users/…/webspec2doc/web/output/demomart/testcases/playwright-report/index.html'
  ```
  パスに `web/` が挿入されている＝`run_dir()` が相対 Path を返し、`send_file` が Blueprint の `root_path`（`web/`）基準で解決している。
- **推定原因ファイル**: `web/routes/ta2.py:466-490`（`send_file(str(target))` に相対パスを渡している）／`web/services/testcase_table_store.py:46-62` `_base_dir` が相対 Path。`Path(...).resolve()` するか `send_file(target.resolve())` が必要。

### B-2【重大】「適用」（fix）が 500 相当の 400 で落ちる

- **症状**: `POST /api/ta2/tests/<id>/fix` が **400** `{"error":"処理に失敗しました。サーバーのログを確認してください。"}`。ユーザーには「修正案がありません」ではなく「サーバーのログを確認してください」と出る。§7-4 の「適用 → 再実行で結果が変わる」が成立しない。
- **再現**: PW-0034 を複製 → 手順末尾に `{"action":"押す","arg":"存在しないボタン","loc":"button[name=\"does_not_exist\"]","op":"click","target":"btn_x","kind":"act"}` を PUT → 実行（失敗し `issue.type="missing"` が step 3 に付く）→ `POST /api/ta2/tests/<id>/fix {"step":3}` → 400。
- **証拠**:
  ```
  File "/Users/…/web/services/ta2_store.py", line 803, in apply_fix
      raise Ta2StoreError("修正案がありません（要素辞書に同じラベルの要素が見つかりません）")
  web.services.ta2_store.Ta2StoreError: 修正案がありません（…）
  ```
  `_guard`（`web/routes/ta2.py:62-78`）は `Ta2Error` しか意味のあるメッセージに変換せず、`Ta2StoreError` を汎用エラーに潰している。
- **推定原因ファイル**: `web/routes/ta2.py:62-78`（`_guard` が `Ta2StoreError` を扱わない）／`web/services/ta2_store.py:803`。
- **付随**: `issue.fix` が `null`（修正案なし）のケースを「エラー」として返している。契約 §3.1 は「無ければ `null` で修正案なし」＝正常系のはず。UI に「適用」ボタンを出す条件も要確認。

### B-3【重大】全件実行が 2 件を黙って捨て、進捗が 123/125 で止まる

- **症状**: `POST /api/ta2/run` は `{"total":125}` を返すが、実際に生成される spec は 123 件。`run/status` は `total:125, done:123, running:false` で終了し、2 件は永遠に「未実行」。UI の進捗バーは 98.4% で完了扱いになる。除外された事実はどこにも表示されない。
- **再現**: ▶ パネルの「▶ 全件実行」を 1 回押す → 完了後 `GET /api/ta2/tests` の status 集計が `{pass:122, fail:1, new:2}`。
- **証拠**: 落ちた 2 件 = `PW-0086 / TC-P005-BVA-008 / email: 未登録（not-registered@example.com）`、`PW-0087 / TC-P005-BVA-009 / email: 解約済み（withdrawn-user@example.com）`。`run_result.json` の `summary.total` も 123。`to_table_rows` が `automation: "自動化可" if actions and assertions else "自動化不可"` とし、検証手順を持たない行が `generate_spec` で落ちる。
- **推定原因ファイル**: `web/services/ta2_store.py:505-535`（`to_table_rows` の automation 判定）／`web/routes/ta2.py:340-390`（`total = len(gen["mapping"]) or len(ordered)` が除外前の件数）。除外件数を status に `skipped` として返すか、除外理由を一覧に出す必要がある。

### B-4【高】◈ パネルが「基準なし」を「差分なし」と偽って表示する

- **症状**: `GET /api/ta2/drift?domain=demomart` は `{"items":[],"reason":"比較の基準となる前回のクロールがありません","baseline_at":"","current_at":""}`。しかし画面は「前回のクロールとの差分はありません」と表示する。**比較できないのに「変更なし」と断言している**（契約 §7-7 の「基準なしなら理由を表示」に反する）。
- **再現**: `.rail [data-view="drift"]` をクリック → `#p-drift` の innerText = `サイトの変更 | 前回のクロールとの差分はありません | 再クロール | 前回のクロールとの差分はありません。`（`ta2-panel-drift.png`）。
- **推定原因ファイル**: `static/js/ta2/panels.js:241,245` は `data.reason` を優先して読むが、`TA2.state.drift` が配列（items のみ）で `reason` が捨てられているため常にフォールバック文言になる。`static/js/ta2/state.js`（drift 取得箇所）でペイロード全体を保持する必要がある。

### B-5【高】手順の `loc` がコード生成で無視される操作がある（編集しても効かない）

- **症状**: `op:"click_link_to"` および ラベル一致クリックでは、生成コードが `loc` を使わず `href` / `arg`（ラベル）で要素を探す。エディタの「ロケータ」欄を書き換えても実行結果が変わらない＝**B-2 の fix が仮に成功しても、クリック手順は修理できない**。
- **証拠**: PW-0009 の手順2の `loc` を `button[name="does_not_exist"]` に PUT して実行 → **PASS**。生成された `output/demomart/testcases/testcases.spec.ts`:
  ```js
  await clickLinkTo(page, "products.html", "DemoMart - 商品一覧");
  ```
  追加した click 手順の失敗ログも `waiting for getByText('存在しないボタン')` で、指定した `button[name="does_not_exist"]` を使っていない。
- **推定原因ファイル**: `web/services/ta2_store.py:425-460`（`_step_to_action`。`fill/clear/select` は `locator` を渡すが `click_link_to` は渡さない）＋ `src/generator/testcase_spec_generator.py` 側の `clickLinkTo` ヘルパ。

### B-6【中】`last.step` が常に null（赤い手順を特定できない）

- **症状**: 失敗した実行で `issue` は正しい手順（index 3）に付くのに、`last.step` は `null`。契約 §3.1 の「error 文中のロケータ文字列と steps[].loc の一致」で特定する設計だが、B-5 のとおり生成コードが `loc` を使わないため error 文に `loc` が現れず、原理的にマッチしない。
- **証拠**: PW-0127 実行後 `last = {"step": null, ...}` ／ `steps[3].issue.type = "missing"`。PW-0082（実失敗）も `step:null` かつ issue も 0 件。
- **推定原因ファイル**: `web/services/ta2_store.py`（`apply_run_result` の突合ロジック）。

### B-7【中】右ペインのワイヤーフレームがラベルではなく入力例を項目名として描く

- **症状**: P004 の「期待/いま」表示で、項目名が `amount` / `TARO YAMADA` / `1111 2222 3333 4444` / `123` / `12/28`。実画面のラベル（金額・カード名義・カード番号・…）ではなく placeholder 値。プロトタイプは `氏名 / メールアドレス / カード番号 / 有効期限 / CVC` と正しいラベルを描いている。
- **証拠**: `ta2-final.png` vs `proto.png`。
- **推定原因ファイル**: `static/js/ta2/viewer.js:82`（`m.label || k`）に渡る `elements_of()` の `label` が placeholder になっている＝`web/services/ta2_store.py` の `elements_of`。

### B-8【中・設計】gap が全画面 0 件で、「穴を見つける」機能が事実上死んでいる

- `GET /api/ta2/map` の全 7 画面が `gaps: []` / `coverage: 100`。`derive_initial` が `test_conditions` を全消費してテストを作るため、`gaps_of` の定義上ゼロになる。⌂ の「網羅 100%」は常に真になり指標として機能しない。§7-6 の gap→生成 経路は本データでは検証不能。

---

## 継ぎ目の確認（10a–10f）

| # | 結果 |
|---|---|
| **10a** `to_table_rows` の `case_id` vs `save_run_result` | **問題あり（想定どおり壊れている）**。`web/services/testcase_table_store.py:89` が `if not case_id.startswith("TC-"): continue`。TA2 のテスト名は `PW-0001 …` なので**毎回 `run_result.json` の `cases` が `{}`**（3 回の実行すべてで `cases_n=0`）。`summary` だけは正しく入る（`passed:122, failed:1, total:123`）。一方 `tests.json` は `apply_run_result` 経由で独立に更新されるため TA2 画面は正常。**影響**: 旧テストケース表（System 01 側）が TA2 実行の個別結果を一切受け取らない。無害ではなく「実行したのに結果が空」に見える。 |
| **10b** `/api/ta2/artifact` | **FAIL**。B-1 のとおり `kind=screenshot/trace/report` すべて 400（JSON エラー）。実ファイルは `output/demomart/testcases/test-results/testcases-PW-0127-…/test-failed-1.png` と `trace.zip`、`playwright-report/index.html` に存在する。証跡ゼロ件時の 404 経路（`trace` のみ観測）は正常。 |
| **10c** ハンドラ二重バインド | **PASS**。`#run-all-btn2` を 1 回クリック → ネットワークログ上 `POST /api/ta2/run` は **1 回**のみ。409 トーストなし。 |
| **10d** テナント（auth off） | **要注意**。`/api/ta2/tests` 系は `_out() = scoped_output_dir(OUTPUT_DIR)`（リクエストスコープ）、実行側 `run_dir()` は `web/services/qa/helpers._output_dir()` という**別の解決器**を使う。auth off の本環境では両者とも `output/demomart/…` に落ち、バックグラウンドスレッドの書き込み先とページの読み取り先は一致した（`output/demomart/ta2/tests.json` 更新を実測）。スレッドは `copy_current_request_context` でコンテキストを引き継ぐので直ちには壊れないが、**テナント有効時に 2 系統の出力先解決が食い違うリスクは未検証**。 |
| **10e** 削除の挙動 | 単体削除は正常（`DELETE` 200 → リロード後に消える、125 件へ戻る）。**全件削除は罠**: `web/routes/ta2.py:167-176` が `if not data.get("tests"): data = st.derive_initial(...); st.save(...)` を無条件で実行するため、**全部消すと次の GET で 125 件が自動復活し、削除は取り消せないどころか「消せない」**。ユーザーから見ると「削除したのに戻る」バグに見え、逆に手編集したテストを全消しした直後の派生も上書き保存される。空リストは「空という状態」として保持し、再派生は明示操作（例: 「初期テストを作り直す」ボタン）にすべき。 |
| **10f** プロトタイプとのレイアウト差分 | 骨格は一致（`ta2-final.png` / `proto.png`、いずれも 1440×900・`scrollHeight 900`）。`.rail [0,0,56,900]` `.list [56,0,280,900]` `#steps [336,56,400,844]` `#page [759,269,658,488]` が**完全一致**。背景 `rgb(246,247,249)`・フォントスタックも一致。差分は 4 点: ①一覧ヘッダに**プロトに無いサイト選択 `<select>` が増えており**、`.items` が 33px 下がる（proto `y174 h664` → app `y207 h631`）。②サイト名が `DemoMart` ではなく**生ドメイン `demomart`** 表示。③「直近10回」スパークラインが履歴 1 件のため 1 マスのみ（データ起因）。④画面グループ見出しが `P003 DemoMart - 商品一覧` とサイト名込みで冗長（proto は `P004 お支払い・決済`）。加えて B-7 のワイヤーフレーム項目名の差。 |

---

## 未検証

- **テナント有効時（`WEBSPEC2DOC_AUTH_MODE` が off 以外）の出力先解決**。10d のとおり 2 系統の `_output_dir` が併存しており、テナント配下 (`output/tenants/<t>/…`) での実行・証跡・tests.json の一致は未確認。
- **キャンセル（`/api/ta2/run/cancel`）と多重実行時の 409**。全件実行が 26 秒で終わるためキャンセル窓を作れず未実行。`_RUNNING_PROCS` への登録・kill 経路は未検証。
- **`issue.type = "expect"` の fix 適用**。最初の（環境不備下の）実行では `issue.fix` に `'string:    [31m"WebSpec2Doc"[39m'` という ANSI エスケープ混じりの壊れた値が入っていた。正常環境で expect 失敗を作れなかったため再現できていないが、**`Received string:` のパース時に ANSI カラーコードと `string:` 接頭辞を剥がしていない疑いが濃い**（`web/services/ta2_store.py` の issue 生成）。要追試。
- `R` キー / `⌘K` / `↑↓` のキーボード操作、初回ヘルプモーダル、`◈` の「再クロール」ボタン、`証跡をまとめて書き出す` / `JUnit XML`（`hidden` 属性が付いており押せない）、`失敗のみ再実行`。
- `firefox` / `webkit` ブラウザ指定での実行。
- 実行中のポーリング挙動は 2〜3 回しか観測できていない（全件 26 秒）。長時間実行時の `current_id` 追従は未検証。

---

## 再検証 (VERIFY-2)

対象: `feat/ta2-visual-editor` @ `adb0323` / 12:02〜12:16 JST。証跡は `.playwright-mcp/v2-final.png`・`.playwright-mcp/v2-b1-failshot.png`。
Playwright は `venv/bin/python`（sync API・headless・1440×900）。

### 判定一覧

| # | 対象 | 判定 | 証拠（1行） |
|---|---|---|---|
| 1 | 回帰テスト | **PASS** | `GATES_REQUESTED=1 venv/bin/pytest tests/test_ta2_store.py tests/test_ta2_api.py tests/test_testcase_table.py tests/test_testcase_docs.py tests/test_data_flow.py tests/test_mutation_verifier.py -q` → **152 passed in 1.44s**（失敗 0・エラー 0） |
| 2 | B-1 証跡 API | **PASS** | 直近実行の PW-0082 で `report` 200 / 21762B `text/html`、`screenshot` 200 / 20200B `image/png`、`trace` 200 / 170348B `application/zip`。未知 ID `PW-9999` は **404** `{"error":"この実行の証跡はありません"}`。UI で PW-0082 →「失敗時」タブ → `#fail-shot` の `naturalWidth=1280, naturalHeight=720`（フォールバック文言ではなく実画像）、console error **0** |
| 3 | B-2 fix 否定系 | **PASS** | `POST /api/ta2/tests/PW-0082/fix {"step":0}` → **200** `{"applied":false,"reason":"このステップには修正できる問題がありません"}`（400 汎用エラーは解消）。UI: 修正案のないテストで `#steps` に「修正案なし」が表示され `[data-fix]`（適用ボタン）は **0 個** |
| 3 | B-2/B-6 fix 肯定系（§7-4 端から端） | **PASS** | P004 に PW-0129 を作成 → `loc:'button[name="does_not_exist"]' / arg:'この内容で支払う'` の click 手順を PUT → 実行 → `status=fail`・`last.step=1`（B-6）・`steps[1].issue = {type:"missing", msg:"要素が見つからない", fix:"text=この内容で支払う", fix_stab:"mid"}` → `POST …/fix {"step":1}` → 200 `applied:true`・`steps[1].loc` が `text=この内容で支払う` に置換・`status=fixed` → 再実行 → **pass**。検証後 `DELETE` 200 で削除済み |
| 4 | B-3 全件実行 | **PASS** | ▶ 全件実行（API 経由）24 秒で `running:false, total:125, done:125, passed:124, failed:1`、`skipped: []`（キー存在）。`new` 残 0。**PW-0086 / PW-0087 とも `status=pass`・`history:[1]`・`last.at=2026-08-30 12:04:56`** で結果が付いた |
| 4 | 新規失敗の内訳 | 情報 | 唯一の失敗は **PW-0082**（`email: 上限値+1`）＝ `expectNotSubmitted` が `URL が http://127.0.0.1:8766/contact/send に変化` を検出。DemoMart 側が上限超えメールを受理して送信する挙動で、**当方コードの例外ではない**（実サイト挙動の正当な検出）。暗黙 `expect_no_error` 由来の新規失敗は **0 件** |
| 5 | B-4 ◈ パネル | **PASS** | `#p-drift` innerText = `サイトの変更 / 比較の基準となる前回のクロールがありません / 再クロール / 比較の基準となる前回のクロールがありません`。API の `reason` 文字列と**完全一致**（「差分はありません」の誤表示は解消）。バッジ `#bd-drift` = `0` |
| 6 | B-5 loc 反映 | **PASS** | PW-0009 手順2の `loc` を `button[name="does_not_exist"]` に PUT → 実行 → **fail**（`last.step=1`）。`loc` を `text=DemoMart - 商品一覧` に戻して再実行 → **pass**。生成コードも `page.locator("button[name=\"does_not_exist\"]").first().click()` と編集値を使用 |
| 7 | B-7 右ペイン | **PASS** | P004 の `#page` innerText = `… amount / card_name / TARO YAMADA / card_number / 1111 2222 3333 4444 / cvc / 123 / expiry / 12/28 …`。項目名は要素キー、入力例は `<span class="ph">` として別描画（`static/css/ta2.css:242` `.page .inp .ph{color:var(--tx3)}` の薄字）。`/api/ta2/tests` の `elements.P004` も `label` と `placeholder` が分離済み |
| 8 | B-8 gap | **PASS** | `/api/ta2/map` の gap 合計 **10 件**（P001:1 / P002:1 / P003:0 / P004:1 / P005:1 / P006:4 / P007:2、coverage 64〜100）。⌂ カードに `穴 1 件`…`穴 4 件` が 6 枚表示。`＋ 新しいテスト` → P001 で gap 一覧に「「おすすめを見る」を押す」を提示 → 生成 → 一覧 126→127 件（PW-0131）。検証後削除し 125 件に復帰 |
| 9 | §7-1 再検証 | **PASS** | 初期ロード console error **0**、4 レール（test / run / site / drift）巡回後も **0**。`document.documentElement.scrollHeight = 900`（1440×900・縦スクロールなし）。`grep -rn 準備中 templates/test-automation.html static/js/ta2 static/css/ta2.css` = **0 件** |
| 10 | サーバログ | **PASS** | 本セッション中の `/tmp/ws2d.log` の `Traceback` 出現数 **0**（B-1 由来の 12 件は消滅） |

**PASS 10 / FAIL 0**（B-1〜B-8 すべて解消。回帰なし）

### 残る観察（不具合ではないが記録する）

1. **証跡は「最新 1 回の実行」しか残らない。** Playwright が実行のたびに `output/demomart/testcases/test-results/` を掃除するため、全件実行の後に別テストを 1 件実行すると、直前に失敗したテストの `screenshot` / `trace` は 404 になる（`web/routes/ta2.py:604-624` `_artifact_target` は現存ファイルしか見ない）。UI は「この実行の証跡はありません」と正しくフォールバックするが、console に 404 が 2 件出る。仕様として許容するなら、失敗テストの「失敗時」タブでは 404 を握り潰す実装が望ましい。
2. **`last.step` は「ロケータが error 文に現れる失敗」でのみ埋まる。** PW-0082 のようにヘルパ関数（`expectNotSubmitted`）内で throw する検証失敗は `last.step` が `null` のまま（`web/services/ta2_store.py` の突合が error 文中のロケータ一致に依存）。B-6 の合格条件（missing 系）は満たすが、ver 系の赤い手順は依然特定できない。
3. **`issue.detail` に ANSI エスケープが残る。** PW-0129 の `issue.detail` に `ESC[2m  - waiting for locator(...)ESC[22m` 相当のシーケンスが含まれる。`fix` 値自体は `text=この内容で支払う` とクリーンなので実害は小さいが、UI に生表示されると制御文字が見える可能性がある（前回「未検証」だった項目の追試結果）。
4. **B-7 の項目名は英語キー。** `card_number` / `amount` / `cvc` は placeholder 値ではなくなった（＝B-7 の修正条件は達成）が、プロトタイプの `カード番号` のような日本語ラベルではない。`elements_of` の `_field_label` が report に人間可読ラベルを持たないためキーへフォールバックしている。表示品質としては次段の課題。
5. **10e（全件削除で自動復活）は今回未再検証。** 破壊的操作のため実行していない。
