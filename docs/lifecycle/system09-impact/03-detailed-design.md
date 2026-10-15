# 詳細設計書 — System 09 影響度分析（商用版）

> 上位: `02-basic-design.md` ／ 下位: `04-implementation.md`
> ここに書いた関数名・引数・戻り値・表・API は実装の契約。実装担当は変えない（変える場合は本書を先に直す）。

**日付**: 2026-10-15 ／ **状態**: ドラフト

## DD-001 データベース（web/services/impact/db.py）

- 場所: `scoped_output_dir(config.DATA_DIR) / "impact" / "impact.db"`。`connect() -> sqlite3.Connection`（row_factory=Row、`PRAGMA foreign_keys=ON`、`journal_mode=WAL`、timeout 10 秒）。初回接続で `migrate(conn)` がスキーマを作る（`schema_version` 表で版管理）
- 時刻は UTC ISO8601 文字列。ID は特記なき限り `uuid4().hex[:12]`

```sql
systems(id PK, name, description, policy TEXT CHECK(policy IN('none','local','external')) DEFAULT 'none',
        p1_min INT DEFAULT 8, p2_min INT DEFAULT 4, depth_default INT DEFAULT 2,
        degraded_recall REAL, degraded_precision REAL, created_by, created_at, updated_at)
members(system_id FK, actor, role CHECK(role IN('admin','analyst','approver','viewer')), PRIMARY KEY(system_id, actor))
documents(id PK, system_id FK, name, kind CHECK(kind IN('requirement','design','screen','testcase','other')),
          size INT, item_count INT, sha256, created_by, created_at, UNIQUE(system_id, name))
items(id PK, system_id FK, document_id FK, code, text, location, section, ord INT)   -- code = 文書略号-連番（例 SCR-0007）
baselines(id PK, system_id FK, name, note, created_by, created_at, UNIQUE(system_id, name))
baseline_items(baseline_id FK, item_id, document_name, kind, code, text, location, section, ord)  -- 固定コピー
links(id PK, system_id FK, a_item FK, b_item FK, origin CHECK(origin IN('manual','suggested')), created_by, created_at,
      UNIQUE(system_id, a_item, b_item))            -- a_item < b_item に正規化
link_suggestions(id PK, system_id FK, a_item, b_item, score REAL, reason, state CHECK(state IN('open','accepted','rejected')), decided_by, decided_at)
change_requests(id PK, system_id FK, code, title, reason, status, base_baseline FK NULL, target_baseline FK NULL,
                change_text, depth INT, created_by, created_at, updated_at, UNIQUE(system_id, code))  -- code = CR-001
changes(id PK, cr_id FK, code, kind CHECK(kind IN('add','modify','delete','text')), location, before, after, wording_only INT)
impacts(id PK, cr_id FK, change_ids TEXT /*JSON*/, item_id, item_code, document_name, doc_kind, location, section, text,
        depth INT, evidence TEXT /*JSON: [{type, detail, score}]*/, confidence REAL,
        impact_level INT, impact_reason, likelihood INT, likelihood_reason, risk INT, priority INT,
        override_impact INT NULL, override_likelihood INT NULL, override_reason, override_by, override_at,
        state CHECK(state IN('open','required','not_required')) DEFAULT 'open', resolve_reason, resolved_by, resolved_at,
        tests TEXT /*JSON: [item_code]*/, test_gap INT, test_idea, method CHECK(method IN('llm','rule')))
jobs(id PK, cr_id FK, status CHECK(status IN('queued','running','done','failed','cancelled','interrupted')),
     stage, progress INT, message, cancel INT DEFAULT 0, started_at, finished_at, engine TEXT /*JSON*/)
actuals(id PK, cr_id FK, item_id, item_code, note, recorded_by, recorded_at)      -- 改修後レビュー
approvals(id PK, cr_id FK, decision CHECK(decision IN('approved','returned')), reason, actor, at)
audit(id INTEGER PK AUTOINCREMENT, system_id, cr_id, actor, action, target, before TEXT, after TEXT, at)
-- audit への UPDATE / DELETE は TRIGGER で RAISE(ABORT, 'audit is append-only')
```

## DD-002 リポジトリ（web/services/impact/repo/）

全関数は第 1 引数に `conn`。入力不正は `ImpactError(message, status)`（利用者向け日本語＋次の行動。status は 400/403/404/409）。監査が要る操作は内部で `audit.write(conn, system_id, cr_id, actor, action, target, before, after)` を呼ぶ。

| モジュール | 関数（戻り値は dict / list[dict]） |
|---|---|
| errors.py | `class ImpactError(Exception): message, status` |
| systems.py | `create(conn, name, description, actor)`（作成者を admin で members に入れる）／`get(conn, sid)`／`list_for(conn, actor)`（メンバーの対象のみ。各件に role・counts）／`update(conn, sid, fields, actor)`（name, description, policy, p1_min, p2_min, depth_default。p1_min ≤ p2_min は 400）／`delete(conn, sid, actor)`／`set_member(conn, sid, target_actor, role, actor)`／`remove_member(...)`／`role_of(conn, sid, actor) -> str|None` |
| documents.py | `add(conn, sid, filename, data, actor, work_dir) -> doc`（ingest → items。同名は置換）／`list(conn, sid)`／`set_kind(conn, sid, doc_id, kind, actor)`／`remove(conn, sid, doc_id, actor)`／`items(conn, sid, doc_id=None, q=None, limit=200, offset=0)`／`guess_kind(name) -> kind` |
| baselines.py | `create(conn, sid, name, note, actor)`／`list(conn, sid)`／`items(conn, bid)`／`diff(conn, bid_old, bid_new) -> {added, modified:[{old,new}], removed}` |
| links.py | `add(conn, sid, a_item, b_item, actor, origin='manual')`／`remove(conn, sid, link_id, actor)`／`neighbors(conn, sid, item_id) -> list[item]`／`suggest(conn, sid, embedder) -> int`（候補を作る件数）／`suggestions(conn, sid, state='open')`／`decide(conn, sid, sug_id, accept: bool, actor)` |
| crs.py | `create(conn, sid, title, reason, change_text, base_baseline, target_baseline, depth, actor)`／`get(conn, sid, code)`（changes・impacts 集計つき）／`list(conn, sid, status=None)`／`transition(conn, sid, code, to, actor, reason='')`（DD-007）／`update(conn, sid, code, fields, actor)`（起票・差し戻し時のみ） |
| impacts.py | `list(conn, cr_id, priority=None, state=None)`／`get(conn, impact_id)`／`resolve(conn, impact_id, state, reason, actor)`／`override(conn, impact_id, impact_level, likelihood, reason, actor)`（再計算）／`summary(conn, cr_id) -> {total, p1, p2, p3, open, test_gap, retest}` |
| approvals.py | `decide(conn, sid, code, decision, reason, actor)`（approver のみ・起票者/解消者本人不可・returned は理由必須） |
| actuals.py | `record(conn, sid, code, item_code, note, actor)`／`review(conn, sid, code) -> {hit, missed:[...], false_alarm, recall}`／`trend(conn, sid)` |
| audit.py | `write(...)`／`query(conn, sid, since=None, until=None, actor=None, cr_code=None, limit=500)` |

## DD-003 役割と可否（web/services/impact/roles.py）

`can(role, action) -> bool`。`require(conn, sid, actor, action)` は不可なら ImpactError(…, 403)、メンバー外は 404（存在を明かさない）。

| action | admin | analyst | approver | viewer |
|---|---|---|---|---|
| view | ○ | ○ | ○ | ○ |
| edit_system / members / policy | ○ | × | × | × |
| documents / baselines / links | ○ | ○ | × | × |
| cr_write / analyze / resolve / override / actuals | ○ | ○ | × | × |
| approve | ○ | × | ○ | × |
| audit_view | ○ | × | ○ | × |

認証オフ（effective_auth_mode()=="off"）では actor は "local"、全対象システムで admin として扱う。

## DD-004 エンジン（web/services/impact/engine/）

| モジュール | 関数 |
|---|---|
| text.py | `norm(s)`（NFKC・空白圧縮）／`tokens(s) -> list[str]`（現行 analyze.tokens を移す）／`ngrams(s, n=2) -> Counter`／`cosine(a: Counter, b: Counter) -> float` |
| changes.py | `from_baselines(diff) -> list[change]`／`from_text(text) -> list[change]`／`is_wording_only(before, after) -> bool`（数字・否定語・条件語〈以上/以下/未満/超/必須/任意/可/不可/のみ/ない〉の集合が同じなら True） |
| embed.py | `class Embedder: available: bool; mode: 'embedding'|'ngram'; vectors(texts) -> list`／`similar(query, corpus_vectors, top_k) -> [(idx, score)]`。`make_embedder(policy) -> Embedder`（policy=='none' または接続先・モデル無しなら ngram） |
| llm_judge.py | `judge(changes, candidates, policy) -> list[{key, related, level, why, test}] | None`（現行 llm.py を移し policy を見る。'none' なら None。'local' は接続先がローカルの時のみ）／`estimate(candidates) -> {count, chars}` |
| candidates.py | `collect(conn, cr, changes, depth, embedder) -> list[cand]`。cand = {item, change_ids, depth, evidence:[{type:'link'|'semantic'|'keyword', detail, score}]}。①changes の所在項目から links を depth 段まで BFS（段数を記録）②各変更の before+after で embedder.similar（top 30、score ≥ 0.25）③語の一致（現行の主題語＋差分語＋言い換え）。同一項目は統合し evidence を連結 |
| risk.py | `impact_level(text, doc_kind, evidence, llm_level=None) -> (level, reason)`／`likelihood(change_kind, wording_only, depth, has_test) -> (value, reason)`（BD の式）／`priority(risk, p1_min, p2_min) -> 1|2|3` |
| tests.py | `select(conn, sid, item_id) -> list[item_code]`（つながった testcase 種別の項目）／`idea(change, item) -> str` |
| run.py | `analyze(conn, sid, cr_code, actor, progress_cb, cancelled_cb) -> {engine:{mode, reason, recall?, precision?}, counts}`。段階: changes → candidates → llm → risk → save。既存の impacts は item_id＋change_ids をキーに state・resolve・override を引き継ぐ |

## DD-005 ジョブ（web/services/impact/jobs.py）

`start(sid, cr_code, actor, tenant_ctx) -> job_id`（同じ CR で running があれば 409）。スレッド内で新しい conn を開き run.analyze を呼ぶ。進捗は `jobs` 表へ（stage, progress 0〜100）。`cancel(job_id)` は cancel=1。`status(job_id)`。`recover(conn)` はアプリ起動時（Blueprint 登録時に 1 回）running/queued を interrupted にし、CR を分析前の状態（起票）に戻す。テナントの保存先はスレッド開始前に解決した db パスを渡す（request 文脈に依存しない）。

## DD-006 API（web/routes/impact_api.py ほか。接頭辞 /api/impact/v2）

応答は JSON。エラーは `{"error": 日本語＋次の行動}` と status。actor は DD-003 の規則。

| メソッド パス | 内容 | action |
|---|---|---|
| GET /systems ・ POST /systems | 一覧・作成 | view・（ログイン済み） |
| GET/PATCH/DELETE /systems/<sid> | 取得（my_role・counts）・設定変更・削除 | view・edit_system |
| GET/PUT/DELETE /systems/<sid>/members[/<actor>] | メンバー | members |
| GET/POST /systems/<sid>/documents ・ PATCH/DELETE …/<doc_id> | 文書 | view・documents |
| GET /systems/<sid>/items?doc=&q=&offset= | 項目の検索 | view |
| GET/POST /systems/<sid>/baselines ・ GET /systems/<sid>/baselines/diff?old=&new= | ベースライン・差分 | view・baselines |
| GET/POST /systems/<sid>/links ・ DELETE …/<id> ・ POST /systems/<sid>/links/suggest ・ GET …/suggestions ・ POST …/suggestions/<id> {accept} | つながり | view・links |
| GET/POST /systems/<sid>/crs ・ GET/PATCH /systems/<sid>/crs/<code> | 変更要求 | view・cr_write |
| POST /systems/<sid>/crs/<code>/transition {to, reason} | 状態遷移 | cr_write（approved/returned は approve） |
| POST /systems/<sid>/crs/<code>/estimate | 送信の見積 {count, chars, policy} | analyze |
| POST /systems/<sid>/crs/<code>/analyze {confirm_send} | ジョブ開始 → {job} | analyze |
| GET /jobs/<job_id> ・ POST /jobs/<job_id>/cancel | 進捗・中止 | view・analyze |
| GET /systems/<sid>/crs/<code>/impacts?priority=&state= ・ GET /impacts/<id> | 影響 | view |
| POST /impacts/<id>/resolve {state, reason} ・ POST /impacts/<id>/override {impact_level, likelihood, reason} | 解消・修正 | resolve・override |
| GET /systems/<sid>/crs/<code>/graph | 関係図 {nodes, edges} | view |
| POST /systems/<sid>/crs/<code>/approval {decision, reason} | 承認・差し戻し | approve |
| GET/POST /systems/<sid>/crs/<code>/actuals ・ GET …/review | 改修後レビュー | view・actuals |
| GET /systems/<sid>/crs/<code>/report.xlsx | レポート | view |
| GET /systems/<sid>/audit?since=&until=&actor=&cr= ・ GET …/audit.csv | 監査 | audit_view |
| POST /sample | 見本の対象システムを作る | （ログイン済み） |
| POST /migrate | 現行データの移行 | （ログイン済み・1 回のみ） |

旧 API（/api/impact/jobs…）は移行完了まで残し、画面からは使わない。

## DD-007 変更要求の状態遷移

| 現在 | 次に行ける状態 | 条件 |
|---|---|---|
| draft（起票） | analyzing | 分析開始時に自動 |
| analyzing（分析中） | draft（失敗・中止・中断）・review（レビュー待ち） | review へは要確認 0 件・分析済み |
| review | approved・returned | approver の決定 |
| returned（差し戻し） | analyzing・review | review へは要確認 0 件 |
| approved | implemented | |
| implemented | verified | |
| draft・returned | rejected（却下） | 理由必須 |

画面の表示名: 起票／分析中／レビュー待ち／承認済み／差し戻し／却下／実装済み／検証済み（REQ-F-014 の 8 状態）。

## DD-008 画面（templates/impact_analysis.html、static/js/impact/{api,app,system,cr,graph}.js、static/css/impact.css）

- 骨格は System 01（app-shell・sidebar-primary-action・app-nav・sidebar-toggle・topbar・dash-hero・dashboard-section-head・dashboard-empty・onboard-steps）。部品の色は impact.css の変数
- サイドバー: 新しい対象システム（主ボタン）／対象システム一覧／（対象を開いている時）概要・文書・ベースライン・つながり・変更要求・設定・メンバー・監査／（CR を開いている時）変更内容・影響・関係図・マトリクス・テスト・承認・改修後レビュー／ガイド。全て /impact 内で完結
- 影響の画面: 左に一覧（優先度・項目・影響度・状態・テスト）、右に詳細パネル（変更前後と影響項目の本文の並列、根拠の種別と本文、リスク値の式、解消フォーム、修正フォーム）
- 関係図: 列 0 = 変更箇所、列 1..3 = 段数。点の色 = 優先度、線 = 根拠種別（実線つながり／点線意味検索／破線 LLM・語）。点を押すと詳細パネル
- 状態: 通常・処理中（ジョブの段階と進捗バー・中止ボタン）・失敗（理由＋次の行動）・0 件（手順と主ボタン）・確認（モーダル。削除・送信・承認・差し戻し）
- 役割で操作を出し分け（my_role）。API の 403 も画面で日本語表示

## DD-009 レポート（web/services/impact/report.py）

`build_xlsx(conn, sid, code) -> bytes`。シート: 概要（CR の項目・状態・件数・エンジン）／影響（ID・優先度・リスク式・項目・根拠・状態・解消理由）／テスト（影響項目 × 選定テスト・テストの抜け）／承認（決定・理由・承認者・日時）／監査（この CR の記録）。

## DD-010 移行（web/services/impact/migrate.py）

`run(conn, actor) -> {systems, crs, impacts}`。旧 store.list_all() の各 job を 1 CR に。文書は documents へ再取り込み、影響は impacts へ（review.status accepted→required・rejected→not_required、note→resolve_reason）。冪等（同じ旧 job id は 2 回取り込まない。audit に記録）。

## DD-011 評価（tests/fixtures/impact_eval/、scripts/impact_eval.py）

- fixtures: 文書 6 本（要件・設計・画面×2・テストケース・旧版）＋ `cases.json`（変更 20 件: {title, change_text or baseline pair, expected_items:[code]}）
- `impact_eval.py --mode rule|full` が各ケースを一時 DB で分析し、再現率・適合率・候補率（候補数/項目数）を出力。rule の結果を systems.degraded_recall/precision の既定値として使う
