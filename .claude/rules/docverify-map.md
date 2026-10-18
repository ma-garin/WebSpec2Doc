---
paths:
  - "templates/doc_verify.html"
  - "templates/docverify/**"
  - "static/js/docverify*.js"
  - "static/css/docverify*.css"
  - "web/routes/doc_verify*.py"
  - "web/services/docverify/**"
  - "tests/test_docverify_*.py"
  - "docs/design/docverify/**"
  - "docs/research/docverify/**"
  - "docs/process/docverify-contract.md"
  - "quality/docverify_eval/**"
  - "scripts/docverify_eval.py"
---
# System 06 ドキュメント検証（docverify）の地図

2026-10-18 main（9039483）の 73 ファイルを全行読んで作成。ファイル単位の詳細は
`docs/design/docverify/codemap.md`（853 行。必要な節だけ grep で読む）。

## 製品
- 要件定義書・設計書を取り込み、ISO/IEC/IEEE 29148 の品質特性で曖昧さ・抜け・検証不能を**規則（決定的）**で洗い出し、指摘と質問票を作る。工程は IEEE 1028 のインスペクション
- LLM は説明・書き換え案の二段目（R2）。採否と承認は人。`approval` は人だけが埋める
- 結果は「合格/不合格/判定不能」の 3 値以上。網羅性は常に「未検証」と表示する設計

## 画面（1 ページ SPA）
- 殻 `templates/doc_verify.html`（ルート `web/routes/doc_verify.py:66`、`dv_ver` を `?v=` に付与）
- `DV.show(view)` が `.dv-view[data-view]` の hidden を切替え、`DV.on(view, fn)` の関数を実行（配列登録＝同じ画面に複数ファイルのハンドラが重なる）。hash と sessionStorage `dv-review` で復元（保存済みレビューがあると起動時に自動で開く）
- JS 読込順（順序依存）: core → global → review → r2 → r3 → r4 → r5。core が `window.DV`（api/banner/toast/modal/busy/scoreBar）を作る
- global.js: home / mine / reviews / findings / checklists / metrics / settings。review.js: レビュー内 7 画面（plan/read/triage/questions/followup/screen/gate、殻は `_review.html`）
- r2.js は review/triage/settings に MutationObserver で注入。r3.js は setcheck（`_r3.html`）。r4.js は `#dvR4Parts` の部品を plan/triage/questions/gate に差し込む。r5.js は DV 非依存の #accuracy
- 新画面の追加は 3 点セット: サイドバー `data-nav`、core の `TITLES`（要レビューなら `REVIEW_VIEWS`）、partial と `DV.on`

## ホーム（data-view="home"）
- HTML `templates/docverify/_global.html` 先頭。DOM: `#dvgHomeStats` `#dvgHomeQuality` `#dvgHomeTodo` `#dvgHomeTable`
- 描画 `docverify-global.js` の `loadHome`/`renderHome`。`GET /api/docverify/home` 1 本（mine 画面も同じ API を再度呼ぶ）
- 算出 `web/services/docverify/home.py`: `me/mine/active/counts/quality/next_actions/next_scope`
- 失敗時は 3 枠が「読み込めませんでした」、Stats は空のまま
- `counts.open_findings/open_critical` は終了レビューを含み、`active[].open` は進行中のみ（数字が食い違いうる）
- 承認済み案 `docs/design/docverify/home-v1.html/.png`: 取り込み導線（ドロップ・種類・観点・見本・外部送信なし）→ 統計 4 枚 → 特性別スコアと次にやること → レビュー表。実装との差: ドロップ領域・select・見本ボタン・統計アイコンが無い、手順 5 つ
- テスト: R1 結合 3 件・単体 7 件のみ。home.py の他の分岐と画面の挙動は無検証

## API（Blueprint 5 つ、`web/__init__.py` 145〜149 行で登録）
- R1 `doc_verify.py`: 検査の CRUD・取り込み・指摘・質問票・照合・終了・報告・ホーム・設定。応答 `{inspection, summary}`
- R2 `_r2`: AI 説明（同意トークン＝プロセス内メモリ）と監査。R3 `_r3`: 複数文書・矛盾・追跡表（`_state`）。R4 `_r4`: 工程・権限・楽観ロック・プリセット（`view`、rev 必須で無いと 409）。R5 `_r5`: GET /accuracy
- エラーは全て `{error}`（R4 は `code`/`errors` 付きあり）
- 認可が 3 系統: R1・R4 は `perm.require`（役割×操作の表、認証オフは全許可）、R2 は `is_admin`/`is_approver`、R3・R5 は無し
- **R1 の更新系は権限も rev も無く、R4 の権限と楽観ロックを迂回できる**。PATCH phase=closed は終了条件を検査しない

## データ
- 1 レビュー = `<DATA_DIR>/docverify/<iid 12 桁 hex>/inspection.json`（テナント別、tmp+os.replace）。主キー passages/findings/participants/versions/r4/set_check/approval/rev
- 同階層のテナント設定: `_settings.json` `_checklists.json` `_r3_settings.json` `_r4_presets.json` `_r4_reference.json` `_r4_audit.jsonl`（ハッシュ連鎖）`_audit.jsonl`（R2）`_llm_settings.json`
- 指摘 status: candidate → adopted → fixed → verified／rejected。severity critical/major/minor（v1 の warning/info は読替え）
- 工程: plan → individual → triage → rework → followup → closed（`process.py`、種別 6 つで省略あり）
- `store.save(insp, expected_rev=)` のときだけ flock + rev+1。expected_rev なしの保存は後勝ち
- 取り込み: ingest.py（20MB・zip 100MB/2000 件・PDF 500 頁・DOCTYPE/ENTITY 拒否）→ ingest_r3.py（表の行断片化・暗号化 Office 拒否）→ `checks.candidates`（適合率 0.7 未満の規則は accuracy で無効化）

## 改修で踏みやすい点
- 重複定義: `PHASE`(global)/`PHASES`(core)、計画保存（review PATCH と r4 PUT /plan）、承認欄（`#dvr-apn` と `#dvR4Approver`）、`.dvg-*` CSS の二重定義、`_read/_write`（settings/presets）、`_ADOPTED`（metrics/process）
- review.js の PATCH で rev が進み、r4 の更新が 409 になりうる。画面を触るときは review.js と r4.js の両方のハンドラが走る前提で確かめる
- CSS は 3 系統が混在（旧 `.dv-table/.dv-btn`、見本 v2 `.dvr-view`、R1 トークン `.dv-*`）。`#047857` などハードコード色あり
- 規則 ID は checks・`accuracy.LABELS/MEMBERS`・`scripts/docverify_eval.py` の RULES で手同期。評価セットを触ったら eval を再生成（R5 テストが sha256 を照合）
- テストは固定文言（M-01〜M-41）・規則 ID・R4/R5 のテンプレート内容の grep に完全一致で依存。文言変更でテストが落ちる
- `trace.to_xlsx` に式インジェクション対策 `_safe` が無い。`questions.import_answers` は引数を破壊的に更新
- LLM の timeout/cancel は待つのをやめるだけで HTTP は止まらない
