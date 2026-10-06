# System 06 ドキュメント検証（インスペクション）実装契約

作業場所: /Users/fujimagariyuki/dev/active/webspec2doc-dv2（worktree）。Python は /Users/fujimagariyuki/dev/active/webspec2doc/venv/bin/python。
pytest / lint / make は実行しない。動作確認は python -c と Flask test_client で行う（`from web import create_app`、環境変数 FLASK_TESTING=1 WEBSPEC2DOC_ALLOW_LOCAL=1 WEBSPEC2DOC_AUTH_MODE=off、POST には headers={"Origin": "http://localhost"}）。git commit はしない。担当ファイル以外は編集しない。

## 部品
- reverse_doc の写し: `web.vendor.reverse_doc`（docs_ingest.readers / ambiguity / confidence / conflicts / questions / docdiff / models）。編集禁止。
  - `readers.read_document(path) -> DocumentIR(name, sha256, passages: tuple[Passage(text, locator)])`、`Locator.label()`、`DocumentError`（利用者向けの文）。暗号化 PDF は一律に拒否するため、呼ぶ前に必ず ingest.unlock_pdf を通す。
  - `ambiguity.ambiguous_words(text) -> tuple[str]`
- テナント: `web.tenancy.scoped_output_dir(base)`、`web.config.DATA_DIR`。

## データ（1 検査 = 1 JSON。`<base>/docverify/<iid>/inspection.json`、base = scoped_output_dir(DATA_DIR)）
```
{"id": "<12 桁 hex>", "name": str, "created_at": iso, "status": "planning|reviewing|fixing|closed",
 "goal": str, "exit_criteria": {"max_open_critical": 0, "max_open_warning": 5},
 "document": {"name", "format", "passages": int, "version": int} | null,
 "passages": [{"id": "P1", "text", "location"}],
 "findings": [{"id": "F1", "rule", "severity": "critical|warning|info", "viewpoint", "message",
               "location", "passage_id", "quote", "certainty": "事実|推定|要確認",
               "status": "candidate|adopted|rejected|fixed|verified", "answer": str|null, "origin": "auto|human"}],
 "versions": [{"version", "name", "uploaded_at", "passages": int}],
 "diff": {"added": [...], "removed": [...], "changed": [...]} | null}
```
iid は uuid4().hex[:12]。受け取った iid は `^[0-9a-f]{12}$` で照合し、違えば 404。

## サービス（web/services/docverify/）
- store.py: `new(name) -> dict` / `list_all() -> list[dict]`（新しい順、passages と findings は除く要約）/ `load(iid) -> dict`（無ければ KeyError）/ `save(insp) -> None`（一時ファイル＋os.replace）/ `doc_dir(iid) -> Path`
- ingest.py: `class IngestError(Exception)`（利用者向けの文。次の行動を 1 行）/ `unlock_pdf(path) -> bool` / `ingest(filename: str, data: bytes, work_dir: Path) -> tuple[dict, list[dict]]`（document と passages）。上限: 20MB、拡張子 .txt .md .docx .xlsx .pdf、docx/xlsx は zip の展開後の合計 100MB・エントリ 2,000 まで、PDF は 500 ページまで、断片 0 件は IngestError。
- checks.py: `candidates(passages) -> list[finding]`。規則: reverse_doc の曖昧語（warning・要確認）、Doc2AI Lint 5 規則の移植（REQ.AMBIGUOUS_TERM 適切に/速やかに/必要に応じて/可能な限り/など＝warning、REQ.MEASURABILITY 要求文に数字が無い＝info、REQ.MULTIPLE_REQUIREMENTS 義務表現 2 回以上＝warning、REQ.MISSING_UNIT 単位の無い数値＝info、REQ.MISSING_SUBJECT「は/が」無し＝info。要求文の判定は しなければならない|すること|shall|must|required|禁止する|必要がある）。同じ断片・同じ語の重複は 1 件にまとめる。status は candidate、origin は auto。
- questions.py: `build(findings) -> list[{"id","finding_id","location","question"}]`（certainty 要確認かつ status が rejected 以外）/ `to_csv(qs) -> str`（UTF-8 BOM、先頭が = + - @ の値は ' を前置）/ `to_xlsx(qs) -> bytes` / `import_answers(insp, csv_text) -> int`（No. と回答の列。回答が入った指摘は answer を入れ certainty を 事実 にする。反映件数を返す）
- diff.py: `compare(old_passages, new_passages) -> {"added","removed","changed"}`（本文の正規化一致で対応付け）/ `carry_findings(old_findings, old_passages, new_passages) -> list`（消えた断片の採用済み指摘は status を fixed に）
- match.py: `domains() -> list[str]`（scoped_output_dir(OUTPUT_DIR) 配下で report.json を持つドメイン。OUTPUT_DIR は web.config）/ `match(passages, domain) -> list[finding]`（文書中の「」で囲まれた語を項目名・ボタン名とみなし、report.json の screens[].buttons・forms[].fields・headings の文言に正規化一致しないものを viewpoint「実画面との食い違い」、severity warning、certainty 推定で返す。未巡回は ValueError）
- metrics.py: `summary(insp) -> {"by_status", "by_severity", "density": 断片あたりの採用指摘, "open_critical", "open_warning", "exit_ok": bool, "reasons": [str]}` / `to_xlsx(insp) -> bytes`（指摘一覧・集計の 2 シート）

## API（web/routes/doc_verify.py。Blueprint 名 doc_verify、変数 bp。既存ファイルを置き換え、sys.path 方式と外部リンク（reverse_doc_url / doc2ai_url）を撤去）
- GET /docverify → render_template("doc_verify.html")
- GET /api/docverify/inspections → {"inspections": [...]}
- POST /api/docverify/inspections JSON {"name","goal"} → 201 {"inspection"}
- GET /api/docverify/inspections/<iid> → {"inspection", "summary"}
- POST /api/docverify/inspections/<iid>/document（multipart file）→ 取り込み。初回は candidates、2 回目以降は diff.compare＋carry_findings＋新しい断片の candidates。status を reviewing に。→ {"inspection","summary"}。IngestError は 400 {"error"}
- POST /api/docverify/inspections/<iid>/findings/<fid> JSON {"status"} → {"inspection","summary"}（遷移は自由。不正値は 400）
- POST /api/docverify/inspections/<iid>/findings JSON {"passage_id","severity","viewpoint","message"} → 人の指摘を追加（origin human、status adopted、certainty 事実）
- GET /api/docverify/inspections/<iid>/questions.csv | questions.xlsx
- POST /api/docverify/inspections/<iid>/answers（multipart file, CSV）→ {"applied", "inspection","summary"}
- GET /api/docverify/domains → {"domains"}
- POST /api/docverify/inspections/<iid>/match JSON {"domain"} → 候補を追加（同じ viewpoint の既存候補は置換）
- POST /api/docverify/inspections/<iid>/close → exit_ok なら status closed、違えば 409 {"error","reasons"}
- GET /api/docverify/inspections/<iid>/report.xlsx
エラーはすべて JSON {"error": 利用者向けの文}。例外はログに残す。

## 画面（templates/doc_verify.html を置き換え。1 ファイル、CSS と JS は中に書く）
- 骨格: `{% with active=... %}` で sidebar を自前で書くが、トップバーは `{% set topbar_crumb = ... %}{% set topbar_title = ... %}{% include 'partials/topbar.html' %}` を使う（ユーザーメニューを出す）。CSS は tokens.css・app.css・app-components.css・css/components.css・css/user-menu.css・css/ta2.css、JS は js/user-menu.js（templates/healing.html と同じ）。
- サイドメニュー: 「検査一覧」「検査」（検査を開いているときだけ、名前を下に表示）。システム切替は既存の .sys-switcher。
- 検査一覧: 一覧（名前・文書・状態・未対応の重大/警告・更新）、「新しい検査」（名前と目的の入力だけ）。0 件の表示。
- 検査（主画面）: 上に文書の帯（名前・形式・断片数・版）と「文書を取り込む／新しい版を取り込む」。左に指摘の表（重大度・指摘・場所・観点・確度・状態）。候補の行には「採用」「却下」のボタンだけ。右に選んだ指摘の根拠の原文と、人の指摘の追加（重大度と観点は選択式、文は 1 行）。
- タブ（主画面の上部）: 指摘／質問票（一覧・CSV/Excel 出力・回答 CSV の取り込み）／版の差分（追加・削除・変更の件数と一覧）／実画面との照合（巡回済みサイトを選ぶ→照合。未巡回なら「まず System 01 で対象サイトを巡回してください」）／終了判定（集計・理由・「検査を終える」・Excel 出力）
- 状態: 読込中・取り込み中（ボタン無効・二重送信防止）・失敗（赤い帯、API の error をそのまま）・0 件（「確認した範囲では指摘はありません。N 断片を確認しました」）。
- API の値は必ずエスケープ（textContent か esc()）。実装語・パスを画面に出さない。「（任意）」を書かない。PC 専用、`html,body{overflow:hidden}` の内側スクロール（ta2.css 方式）で、表と詳細は内側でスクロールして最下部まで届くこと。識別色は #BE185D / #FCE7F3 / #9D174D。

---

# v2 追補（2026-10-06 23:30 保守者承認。見本: scratchpad/mock/docverify-v2.html。v1 の画面・API と食い違う所は v2 を正とする）

## 用語と画面（サイドメニュー）
- 全体: ホーム（home）／自分の担当（mine）／レビュー一覧（reviews）／指摘一覧（findings）
- レビューの中（レビューを開いているときだけ表示。見出しはレビュー名）: 計画（plan）／文書を読む（read）／指摘の検討（triage）／質問票（questions）／修正版の確認（followup）／実画面との照合（screen）／判定と記録（gate）
- 管理: 観点チェックリスト（checklists）／メトリクス（metrics）／設定（settings）
- 「検査（inspection）」は画面上「レビュー」と呼ぶ。データの id はそのまま。

## データ追加（inspection.json）
- "phase": "plan|individual|triage|rework|followup|closed"（画面上部の工程表示。status は互換のため残す）
- "participants": [{"name", "role": "author|moderator|reviewer|approver", "done": bool}]、"due": "YYYY-MM-DD"
- "checklist_id": str|null（観点チェックリスト）、"checks": {"<item_id>": true}
- findings 追加属性: "checklist_item": str|null、"raised_by": str（自動は "自動候補"）、"disposition": str|null（作成者の対応結果）、"severity" は "critical|major|minor"（画面: 重大/主要/軽微。v1 の warning→major、info→minor に読み替え）
- "approval": {"approver": null, "decided_at": null}（承認欄は人だけが埋める。AI・自動処理は埋めない）

## 共通データ（<base>/docverify/_settings.json, _checklists.json）
- settings: {"severities": [...], "types": [...], "exit_criteria": {...}, "me": "利用者名"（認証オフ時は "ゲスト"。認証オン時は g.auth_user の名前）}
- checklists: [{"id", "name", "items": [{"id", "text"}]}]。初期値に「要求仕様書（ISO/IEC/IEEE 29148 の品質特性: 必要・曖昧でない・完全・一貫・実現可能・検証可能・追跡可能）」を 1 つ入れる。

## API 追加
- GET /api/docverify/home → {"mine": [...自分の担当（レビュー名・役割・工程・期限）], "active": [...進行中レビュー], "counts": {...}}
- GET /api/docverify/findings?status=&severity=&review= → 全レビュー横断の指摘一覧（review_id, review_name 付き）
- PATCH /api/docverify/inspections/<iid> JSON（name, goal, due, participants, checklist_id, exit_criteria, phase）→ 計画の保存と工程の前進
- POST /api/docverify/inspections/<iid>/findings/<fid> JSON に severity, checklist_item, disposition, status を受ける
- POST /api/docverify/inspections/<iid>/participants/me/done → 自分の個別レビューを終える
- GET/PUT /api/docverify/checklists、GET/PUT /api/docverify/settings
- GET /api/docverify/metrics → レビュー別・観点別・重大度別の件数、断片あたりの指摘密度、修正完了率
- POST /api/docverify/inspections/<iid>/approve は作らない（承認は人が判定と記録の画面で記入する欄。サーバは approver に入れられた名前と日時を保存するだけ: PATCH の "approval"）

## 画面の土台（templates/doc_verify.html。本線が作る）
- 各画面は `<section class="dv-view" data-view="<key>" hidden>` を持つ partial を include する:
  templates/docverify/_global.html（home, mine, reviews, findings, checklists, metrics, settings）
  templates/docverify/_review.html（plan, read, triage, questions, followup, screen, gate）
- JS: static/js/docverify-core.js（本線: ルータ・API 呼び出し・esc・エラー帯）、static/js/docverify-global.js、static/js/docverify-review.js
- core が公開するもの: `window.DV = {api(path, opts) -> Promise<json>（失敗時は帯を出して reject）, esc(s), show(view), state: {review: null|inspection, summary}, openReview(iid), toast(msg), on(view, fn)}`。`DV.on(view, fn)` は画面を開くたびに fn() を呼ぶ。
- CSS: static/css/docverify.css（本線が v2 見本の CSS を移す。各担当は追記してよいが、既存の規則を消さない）
