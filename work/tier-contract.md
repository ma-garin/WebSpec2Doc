# トレーサビリティ 3 画面 実装契約（2026-10-18・本線が決定。担当はこれに従い、変えない）

方針: 既存の検査（inspection）をプロジェクトとして流用。格は決定的ルールで推定（LLM 不使用）。規則③は前の版と比較。旧 R3 画面（setcheck）は廃止し置き換え。
見本（見た目の正）: static/mock/system06/sidebar/index.html の 1A / 2B / 3C（部品: scratchpad/v2/1A.html, 2B.html, 3C.html）。ピラミッド図は禁止。

## 保存（inspection.json に追加するキー `tier`。既存キーは触らない）
```
tier = {
  "documents": [{"id":"T"+8hex,"name","format","tier":1-4,"tier_source":"ai"|"human","confidence":0..1,
                 "reason":str,"uploaded_at","passages":[{id,text,location}],"prev_passages":[...]|None}],
  "approved": {"by","at"} | None,
  "findings": [Finding],              # approve 時に rules.run で生成
  "reports": {finding_id: {"reason","by","at"}},   # 誤検知の通報
  "conclusion": {"level":"pass"|"conditional"|"fail","auto":level,"confirmed_by","comment","confirmed_at"} | None
}
```
step（サーバが算出）: approved 無し→1 / approved 有り・conclusion 無し→2（findings 0 件でも 2）/ 画面 3 は UI が 2 の後に遷移 / conclusion 有り→"done"。

## エンジン `web/services/docverify/tierflow/`（__init__.py は空）
- `tiers.py`
  - `TIERS = ((1,"方針"),(2,"決まりごと"),(3,"仕様"),(4,"メモ"))`、`TIER_HINT = {1:"ビジョン・憲章",2:"規約・ガイドライン・用語集",3:"PRD・設計書・ADR",4:"議事録・台帳・メモ"}`
  - `estimate(name: str, passages: list[dict]) -> {"tier":int,"confidence":float,"reason":str}`（ファイル名と見出し・語彙の一致で決定的に。reason は日本語 1 文。confidence < 0.6 を「確認が要る」とする: `LOW = 0.6`）
- `rules.py`
  - `RULES = (("STATE","日付や状態を書いていない"),("TERMS","用語集どおりの言葉"),("PROTECTED_CHANGE","勝手に直してはいけない文書を直していない"),("CONFLICT","上の格と食い違っていない"),("REVERSE_REF","上の格が下の格を参照していない"),("DUPLICATE","同じことを 2 か所に書いていない"))`
  - `run(documents: list[dict]) -> list[Finding]`（各規則の例外は握りつぶさずログし、その規則だけ空にする）
  - Finding: `{"id":"F"+8hex(決定的: rule+doc+passage+quote のハッシュ),"rule","rule_label","severity":"high"|"mid"|"low","doc_id","passage_id","quote","start","end"(passage text 内の文字位置),"reason","fix","related_doc_id"|None,"related_quote"|None}`
  - 重さの既定: CONFLICT=high, REVERSE_REF=mid, PROTECTED_CHANGE=high, DUPLICATE=mid, TERMS=low, STATE=low
  - 再利用: CONFLICT は setcheck.contradiction_reason / pair.contradiction、DUPLICATE は setcheck.find_pairs、TERMS は 格2 で名前に「用語」を含む文書の表 or pair.terms
- `links.py`
  - `build(documents, findings, reports) -> {"nodes":[{"id","name","tier","status":"ok"|"warn"|"ng","issues":int}],"edges":[{"from":下位doc,"to":上位doc,"type":"follows"|"conflict"|"reverse_ref"|"duplicate","finding_ids":[]}]}`（通報済みの finding は数えない。follows は 下位→直上の格にある全文書を既定で結ぶ）
  - `conclude(findings, reports) -> "pass"|"conditional"|"fail"`（通報済みを除き high が 1 件でも fail、mid/low のみ conditional、0 件 pass）
  - `LEVEL_LABEL = {"pass":"合格","conditional":"条件付き","fail":"不合格"}`

## API（新 Blueprint `web/routes/doc_verify_tier.py`、`web/__init__.py` に登録）
全て JSON。エラーは `{"error": 日本語1文＋次の行動}`。成功は常に state を返す。
- `GET  /api/docverify/inspections/<iid>/tier` → state
- `POST /api/docverify/inspections/<iid>/tier/documents`（multipart、`file` 複数可）→ 201 state。同名の文書は置換し、旧 passages を prev_passages に。approved 後の追加は approved/findings/conclusion を消す（再承認）
- `PATCH /api/docverify/inspections/<iid>/tier/documents/<did>` `{"tier":1-4}` → tier_source="human"
- `DELETE /api/docverify/inspections/<iid>/tier/documents/<did>`
- `POST /api/docverify/inspections/<iid>/tier/approve` `{"by"}` → 0 件なら 400。rules.run を実行し findings 保存
- `POST /api/docverify/inspections/<iid>/tier/findings/<fid>/report` `{"reason"}`（reason 必須）
- `POST /api/docverify/inspections/<iid>/tier/confirm` `{"by","comment","level"(省略時 auto)}`
- `POST /api/docverify/inspections/<iid>/tier/reset` `{"to":1|2}`（1: approved/findings/conclusion を消す、2: conclusion だけ消す）
state = `{"step","documents":[passages と prev_passages を除く],"documents_text":{doc_id:[{id,text}]}(step>=2 のみ),"tiers":[{id,label,hint}],"low":0.6,"approved","findings","reports","rules":[{id,label}],"links"(step>=2),"auto_level"(step>=2),"level_label","conclusion"}`

## 画面
- 外枠 `templates/docverify/_tier.html`: `<section class="dv-view dvt" data-view="trace" hidden>`。中にプロジェクト選択（既存検査の select＋「新しく作る」= POST /api/docverify/r4/inspections {name, goal:"", review_type:"informal"}）、3 段ステッパー `#dvtSteps`、3 つの区画 `#dvtS1 #dvtS2 #dvtS3`（各 `{% include 'docverify/_tier_N.html' %}`）。
- 外枠 JS `static/js/docverify-tier.js`: `window.DVT = {iid, state, api(path, opts), refresh(), go(step), toast(msg, kind)}`。go は該当区画だけ表示しステッパー更新。refresh 後に `document.dispatchEvent(new CustomEvent('dvt:state'))`。iid は localStorage `dvt.iid`（try/catch）。`DV.on('trace', ...)` で表示時に refresh。
- 画面 N: `templates/docverify/_tier_N.html` ＋ `static/js/docverify-tier-N.js` ＋ `static/css/docverify-tier-N.css`（全セレクタ `.dvt-sN` で始める）。`dvt:state` を受けて描画。主ボタンは画面に 1 つ。
  - 1 = 見本 1A: ドロップ帯→集計→確認が要る文書のカード（格ボタン 4 つ）→自動で決まった文書を格ごとに畳む→主ボタン「この内容で承認」（approve → go(2)）
  - 2 = 見本 2B: 結論帯（auto_level と件数）→左 文書タブ（指摘のある文書に件数）・中央 本文（指摘箇所に重さ色の下線 start/end）・右 指摘カード（双方向連動）→「誤検知を通報」（理由必須）→主ボタン「つながりとレポートへ」（go(3)）・控えめに「登録からやり直す」（reset to=1）
  - 3 = 見本 3C: 結論と数字→左 文書の表（既定。状態アイコン、問題行を強調）・右 選んだ文書を基点に上流/下流 1 段の SVG 関係図（問題の線は赤、線を押すと原因）→主ボタン「レポートを確定」→確認ダイアログ（確定者・コメント）→確定後は「確定済み」表示、課題のある文書を強調・他は薄く。「検査からやり直す」（reset to=2）
- 結線（外枠担当）: `templates/doc_verify.html` の `{% include 'docverify/_r3.html' %}` を `_tier.html` に置換、CSS/JS の link/script を r3 → tier 系に置換、サイドの `#setcheck`/`data-go="setcheck"` → `trace`。`static/js/docverify-core.js` の SECTIONS `trace: ['trace']`、TITLES に `trace: 'トレーサビリティ'`、REVIEW_VIEWS から `setcheck` を除去（トレースはレビュー不要）。旧 r3 ファイルは消さない（参照を外すだけ）。

## 文言
利用者向けに実装語・パスを出さない。「（任意）」を書かない。エラーは次の行動を 1 文添える。PC 専用。
