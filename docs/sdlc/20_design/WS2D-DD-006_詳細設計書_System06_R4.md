# WS2D-DD-006 詳細設計書 System 06「ドキュメント検証」R4

- 文書ID: WS2D-DD-006-R4 / 版数: 0.1（草案・未承認） / 作成日: 2026-10-15 / 作成者: 開発チーム / 承認者: 未承認（保守者が記入する）
- 準拠: IPA 共通フレーム（ソフトウェア詳細設計相当）。テスト観点は ISTQB CTFL のテストレベルで分け、受入基準（RD-006 の G/W/T）から導く
- 上位文書: WS2D-RD-006 要件定義書 11 章 R4・8.2 章、WS2D-DD-006 R1（書式・共通規約）
- 範囲: FR-06-034・035・043・044・054・074・076、FR-06-140〜149、FR-06-160〜162・165、NFR-06-21・22
- 参照: ISO/IEC 20246:2017（種別・役割・工程の参考）、ISO/IEC/IEEE 29148:2018（観点）、IPA『ソフトウェア開発データ白書 2018-2019』（参考範囲。docs/research/docverify/E5_review_metrics.md 4 章）

## 1. ファイル一覧

R4 は新規ファイルだけで実装した。既存の共有ファイルへの接続は wire（2 章末）に分けた。

| # | ファイル | 区分 | 依存 | 節 |
|---|---|---|---|---|
| G1 | `web/services/docverify/process.py` | 新規 | `metrics._safe`（xlsx の式注入対策） | 3 |
| G2 | `web/services/docverify/presets.py` | 新規 | `web.tenancy.scoped_output_dir` | 4 |
| G3 | `web/services/docverify/perm.py` | 新規 | `web.auth.auth_enabled`・`settings.current_user` | 5 |
| G4 | `web/routes/doc_verify_r4.py` | 新規 | G1〜G3・`store` | 6 |
| G5 | `templates/docverify/_r4.html` | 新規 | — | 7 |
| G6 | `static/js/docverify-r4.js` | 新規 | `window.DV`（docverify-core.js） | 7 |
| G7 | `static/css/docverify-r4.css` | 新規 | `static/tokens.css` の変数のみ | 7 |
| G8 | `tests/test_docverify_r4.py` | 新規 | G1〜G4 | 9 |

共通の規約は R1 1 章と同じ（関数 50 行未満・ファイル 400 行以内・引数を変更しない・利用者向けの文は本書 8 章の文）。

## 2. データ（検査 JSON への追加）

R4 の追加は検査 JSON の `r4` と最上位の `rev` に置く。どちらも無い v1・v2 の JSON はそのまま読める（NFR-06-17）。

| キー | 型 | 内容 | ID |
|---|---|---|---|
| `rev` | int | 版番号。更新のたびに +1。無ければ 0 | NFR-06-21 |
| `r4.review_type` | `informal`・`walkthrough`・`technical`・`inspection`・`management`・`audit` | 無ければ「未設定（旧形式）」 | FR-06-140 |
| `r4.independent` | bool | 個別レビューの独立 | FR-06-034 |
| `r4.exit_options` | `{require_all_verified, require_all_individual_done}` | 種別の既定を上書き | FR-06-143 |
| `r4.phase_log` | `[{phase, started_at, started_by, ended_at, ended_by}]` | 工程の実施記録 | FR-06-144 |
| `r4.effort` | `{prep: {名前: 分}, meeting_minutes}` | 工数 | FR-06-145 |
| `r4.pages`・`r4.doc_kind` | 数・`basic`/`detail`/null | 頁数（人が入れる）と比較する文書の種類 | FR-06-146・147 |
| `r4.preset_id` | str | 使っている観点プリセット | FR-06-160・165 |
| `r4.verdict` | `approved`・`conditional`・`rereview` | 判定 | FR-06-074 |
| `participants[].role` | 上記に `scribe`（記録者）を追加 | | FR-06-140 |
| `findings[].kind` | `missing`・`wrong`・`ambiguous`・`contradiction`・`violation` | 欠落・誤り・曖昧・矛盾・規約違反 | FR-06-035 |
| `approval.doc_version` | int | 承認したときの文書の版 | FR-06-054 |
| `document.sha256` | str | 取り込んだファイルのハッシュ（wire 3-変更4 で記録） | FR-06-074 |

テナント単位のファイル（`<base>/docverify/`）: `_r4_presets.json`（複製したプリセット）・`_r4_reference.json`（参考範囲の上書き）・`_r4_audit.jsonl`（操作記録）。

wire: 既存ファイルへの変更（Blueprint 登録・include・script・既存ルートへの権限・store の版番号照合・ハッシュ記録）は `scratchpad/wire_R4.txt` に「ファイル / 正確な変更 / 位置」で記載した。

## 3. G1 `process.py`

| 公開 | 引数 → 戻り値 | 内容 | ID |
|---|---|---|---|
| `REVIEW_TYPES` | dict | 種別ごとの `label`・`required`（必須役割）・`phases`・`checklist`（入口でチェックリストを要るか）・`exit`（既定の出口基準） | FR-06-140 |
| `type_info(insp)` | → `{type, label, legacy, hint, required, phases}` | 種別が無ければ `legacy: True`・`label: 未設定（旧形式）`・`phases` は全工程 | FR-06-140 |
| `plan_errors(type, participants)` | → `list[str]` | 必須役割の不足と兼務（作成者×議長・作成者×承認者） | FR-06-140・141 |
| `next_phase(insp)` | → str \| None | 種別の工程列で次の工程 | FR-06-003 |
| `entry_errors(insp, target)` | → `list[str]` | 計画以外は文書の取り込み済み、個別レビューは必須役割とチェックリスト（種別が要るとき）、`closed` は `exit_errors` | FR-06-142 |
| `exit_options(insp)`・`exit_errors(insp)` | → dict・`list[str]` | 確認待ち（status=fixed）0 件・レビュアー全員の個別レビュー終了 | FR-06-143 |
| `advance(insp, target, actor, now)` | → 新しい insp | 前の記録を閉じ新しい記録を開く。`closed` は開始＝終了で 1 行、`status: closed` | FR-06-144 |
| `effort_errors`・`effort(insp)` | → `{prep, meeting_minutes, total_minutes}` | 合計 = 準備の和 + 会議時間（受入基準: 60×2+30=150） | FR-06-145 |
| `indicators(insp, override)` | → dict | 指摘密度＝採用（adopted・fixed・verified）÷頁、検査速度＝頁÷会議時間（時）、頁あたり工数＝工数合計（時）÷頁、重大度別件数、修正完了率＝(fixed+verified)÷採用。頁が無ければ `messages=[M_NO_PAGES]`、会議 0 なら速度だけ `M_NO_MEETING`。小数 2 桁の四捨五入 | FR-06-146 |
| `compare(density, kind, override)` | → dict \| None | 範囲・中央値・出典・適用限界・`note`（低い／高い／範囲内）・`affects_verdict: False`。上書きがあればその値で比べ出典を「組織の基準値」に | FR-06-147・148 |
| `visible_findings(insp, viewer)` | → list | 独立オン・工程が個別レビュー・本人が未終了なら、自動候補と本人の指摘だけ | FR-06-034 |
| `unchecked(items, checks)` | → list | 未確認のチェック項目 | FR-06-162 |
| `approval_state(insp)` | → `{approved, stale, message, verdict, verdict_label}` | 承認時の版より文書の版が新しければ `stale` | FR-06-054 |
| `answer_rows_csv`・`answer_rows_xlsx` | → `[(行番号, No., 回答)]` | 1 行目が見出し（「No.」「回答」必須）。行番号は表計算ソフトの表示と同じ | FR-06-043 |
| `apply_answers(insp, rows)` | → `(insp, 反映件数, skipped)` | 不明な No. と空の回答は反映せず `{row, reason}` で返す | FR-06-044 |
| `skipped_message(skipped)` | → str | 「反映できない行: 5 行目（不明な No. または空の回答）」 | FR-06-044 |
| `record_rows(insp)`・`record_xlsx(insp)` | → `[[項目, 値]]`・bytes | 種別・参加者と役割・各工程の日時と担当・所要時間・工数・対象版・SHA-256・判定。xlsx は「レビュー記録」「指摘一覧（種別列つき）」「規格の扱い」の 3 シート | FR-06-074・035・076 |
| `STANDARDS`・`STANDARDS_NOTE` | | 規格名・版・扱い。「認証済み」「規格に準拠」を使わない | FR-06-076 |

種別の既定（ISO/IEC 20246 を参考にした暫定値。要判断-1）:

| 種別 | 必須役割 | 工程 | 入口でチェックリスト | 既定の出口基準 |
|---|---|---|---|---|
| 非公式 | 作成者 | 計画→個別→判定 | 不要 | なし |
| ウォークスルー | 作成者・レビュアー | 計画→個別→検討→判定 | 不要 | なし |
| 技術レビュー | 作成者・議長・レビュアー | 全 6 工程 | 要 | 全確認済み |
| インスペクション | 作成者・議長・記録者・レビュアー | 全 6 工程 | 要 | 全確認済み・全員終了 |
| マネジメントレビュー | 議長・レビュアー・承認者 | 計画→個別→検討→判定 | 不要 | なし |
| 監査 | 議長・レビュアー・承認者 | 全 6 工程 | 要 | 全確認済み・全員終了 |

参考範囲（E5 4 章。合否に使わない）: 基本設計 0.12〜0.76 件/頁（中央 0.28・図7-3-5）、詳細設計 0.07〜0.42 件/頁（中央 0.16・図7-3-10）。

## 4. G2 `presets.py`

| 公開 | 内容 | ID |
|---|---|---|
| `BUILTIN` | 既定 4 件: `req-29148`（要求仕様書・29148 の 7 特性。settings の既定と同じ項目 ID）・`basic-design`（基本設計書）・`screen-design`（画面設計書）・`dod-ai`（AI 時代の完了条件 4 項目。書籍付録 C.2 の構造を参照し文面は自作） | FR-06-160 |
| `list_presets()`・`get(pid)` | 既定＋テナントの複製 | FR-06-160 |
| `duplicate(pid, name)` | `c-` で始まる ID の複製を保存。元は変えない | FR-06-161 |
| `update(pid, name, items)` | 複製だけ編集できる。既定は `PermissionError(M_BUILTIN)` | FR-06-161 |
| `delete(pid, in_use)` | 使用中は `PermissionError(M_IN_USE)`。既定は削除できない | FR-06-165 |
| `load_reference()`・`save_reference(body)` | `{basic|detail: {low, high}}`。0 以上・下限≦上限 | FR-06-148 |

## 5. G3 `perm.py`

| 公開 | 内容 | ID |
|---|---|---|
| `MATRIX` | 要件定義書 8.2 の表をそのまま写した操作→役割の集合（`tenant_admin` を含む） | NFR-06-22 |
| `_context()` | `(利用者名, テナント管理者か, 認証が有効か)`。管理者は `g.auth_user["role"] == "admin"`（選択中テナントでの役割。auth.require_admin と同じ判定） | NFR-06-22 |
| `roles_of(insp, user, is_admin)`・`can(op, roles, auth_on)` | 参加者の役割＋管理者。認証オフは全許可 | NFR-06-22 |
| `check(op, insp)`・`denied_message(op)` | 拒否なら「〇〇の権限がありません（行えるのは△△です）。…」 | NFR-06-22・16 |
| `require(op)` | ルート用 decorator。URL の `iid` でレビューの役割を見る。拒否は 403 `{error, code: "forbidden"}` | NFR-06-22 |
| `rev_of`・`check_rev(insp, rev, required)`・`bump`・`Conflict` | 版番号の照合。違えば `M_CONFLICT`。R4 の API は `rev` 必須、既存の画面向けは `required=False`（後方互換） | NFR-06-21 |
| `locked(dir)` | `fcntl.flock` による検査単位の排他。照合から保存までを囲む | NFR-06-21 |
| `record(op, target, detail, actor)`・`verify_log()` | 1 行＝`{seq, at, actor, op, target, detail, prev, hash}`。`hash = SHA-256(hash 以外の JSON)`、`prev` は前の行の hash。検算で最初に食い違った行を返す | FR-06-149 |

## 6. G4 `routes/doc_verify_r4.py`（Blueprint `doc_verify_r4`）

更新系の順序: 権限 → 排他 → 再読込 → 版番号の照合 → 変更 → `rev + 1` → 保存 → R4 の状態一式（`view`）を返す。

| メソッド・パス（`/api/docverify/r4` 以下） | 権限 | 成功 | 失敗 | ID |
|---|---|---|---|---|
| GET `/meta` | — | 種別・役割・指摘の種別・判定・規格・参考範囲 | — | FR-06-076 |
| POST `/inspections` `{name, goal, review_type}` | — | 201 | 400 種別なし | FR-06-140 |
| GET `/inspections/<iid>` | — | `view` | 404 | — |
| PUT `/inspections/<iid>/plan` `{rev, review_type, participants, independent, exit_options}` | plan_edit | 200 | 400（`errors` に全理由）・409 | FR-06-140・141・143 |
| POST `/inspections/<iid>/advance` `{rev, phase?}` | plan_edit | 200 | 409（`errors`。判定へは現行の未対応件数の理由も足す） | FR-06-142〜144 |
| PUT `/inspections/<iid>/effort` `{rev, prep, meeting_minutes, pages, doc_kind}` | plan_edit | 200 | 400 | FR-06-145・146 |
| POST `/inspections/<iid>/findings/<fid>/kind` `{rev, kind}` | finding_edit | 200・操作記録 | 400・404 | FR-06-035・149 |
| POST `/inspections/<iid>/verdict` `{rev, verdict, approver, decided_at}` | approve | 200・操作記録 | 400（名前・日時は人の入力が必須）・403 | FR-06-054・074・149 |
| POST `/inspections/<iid>/answers`（multipart `file`・`rev`） | finding_edit | `applied`・`skipped`・`message` | 400 | FR-06-043・044 |
| POST `/inspections/<iid>/preset` `{rev, preset_id}` | plan_edit | 200 | 404 | FR-06-160 |
| GET `/inspections/<iid>/record.xlsx` | — | xlsx | 500（利用者向けの文） | FR-06-074 |
| GET `/presets` | — | 一覧 | — | FR-06-160 |
| POST `/presets/<pid>/copy`・PUT/DELETE `/presets/<pid>` | tenant_settings | 201・200 | 404・409（既定・使用中）・400 | FR-06-161・165 |
| GET/PUT `/reference` | PUT は tenant_settings | 範囲・上書き・限界 | 400・403 | FR-06-148 |
| GET `/audit/verify` | audit_view | `{ok, line, count, message}` | 403 | FR-06-149 |

## 7. 画面（G5〜G7）

`_r4.html` は 4 つの部品（`#dvR4-plan`・`#dvR4-triage`・`#dvR4-questions`・`#dvR4-gate`）を隠し容器 `#dvR4Parts` に持つ。`docverify-r4.js` は `DV.on(view)` で該当の `.dv-view[data-view=…]` の末尾へ部品を移し、`GET /inspections/<iid>` の結果で描く。

| 画面 | 部品の内容 |
|---|---|
| 計画 | 旧形式の案内・種別・必須役割・参加者表（記録者を含む 5 役）・独立と出口基準のチェック・プリセット（使う・複製・削除）・入口基準の未達理由・前進・工程の記録表・準備時間（参加者ごと）・会議時間・頁数・文書の種類・指標と参考範囲（出典・適用限界） |
| 指摘の検討 | 指摘ごとの種別の選択。独立で隠しているときは案内 1 行 |
| 質問票 | 回答の CSV／xlsx の取り込みと反映できない行 |
| 判定と記録 | 承認失効の警告（role=alert）・判定・承認者・日時（人が入れる）・未確認のチェック項目・レビュー記録・出力・操作記録の検算・参照した規格 |

更新は必ず `rev` を送り、409（conflict）のときは帯に文を出して最新を読み直す。値はすべて `DV.esc` を通す（NFR-06-19）。CSS は tokens の変数だけを使う。

## 8. 利用者向けの文（NFR-06-16）

| ID | 文 |
|---|---|
| R4-01 | 他の人が先に更新しました。最新を読み込んでから操作してください。 |
| R4-02 | 画面の情報が古い可能性があります。再読み込みしてから操作してください。 |
| R4-03 | 〇〇の権限がありません（行えるのは△△です）。必要なら議長かテナント管理者に依頼してください。 |
| R4-04 | レビューの種別が未設定です（旧形式）。計画の画面で種別を選ぶと、必須の役割と基準が決まります。 |
| R4-05 | 〈種別〉では〈役割〉が必須です。参加者に追加してください。 |
| R4-06 | 作成者と〈議長／承認者〉は兼務できません（名前）。別の人を選んでください。 |
| R4-07 | 文書を取り込んでください。 |
| R4-08 | 修正済みで確認待ちの指摘が n 件あります。修正版の確認で確認済みにしてください。 |
| R4-09 | 個別レビューを終えていない人がいます（名前）。全員が終えてから進めてください。 |
| R4-10 | 頁数が無いため算出できません。指標の欄に文書の頁数を入れてください。 |
| R4-11 | 承認後に文書が変わりました。承認は失効しています。再レビューしてください。 |
| R4-12 | 反映できない行: n 行目（不明な No. または空の回答） |
| R4-13 | このプリセットを使っているレビューがあるため削除できません。レビューの観点を別のプリセットに変えてから削除してください。 |
| R4-14 | 操作記録に改ざんの疑いがあります（n 行目）。テナント管理者に連絡してください。 |
| R4-15 | 他組織のプロジェクトの分布で、業種・規模・数え方の違いを含みます。合否の判定には使いません。 |

## 9. テスト観点（`tests/test_docverify_r4.py`。25 件）

R4 の Blueprint だけを載せた Flask アプリで API を叩く（web/__init__.py への登録は wire のため）。権限は `perm._context` を差し替えて役割を与える。

| テスト | 受入基準 |
|---|---|
| `test_create_requires_type`・`test_inspection_requires_moderator_and_scribe`・`test_legacy_without_type_opens` | FR-06-140 |
| `test_author_cannot_be_moderator` | FR-06-141（保存されず rev も変わらない） |
| `test_entry_needs_document` | FR-06-142 |
| `test_exit_requires_all_verified` | FR-06-143 |
| `test_phase_log_two_steps` | FR-06-144 |
| `test_effort_total` | FR-06-145（150 分） |
| `test_indicators_density_and_speed` | FR-06-146（0.30 件/頁・20 頁/時・頁なしの文） |
| `test_reference_low_does_not_change_verdict` | FR-06-147 |
| `test_reference_override` | FR-06-148 |
| `test_audit_tamper_detected` | FR-06-149（10 行中 5 行目の書き換え） |
| `test_preset_select_screen`・`test_preset_copy_keeps_original`・`test_unchecked_items`・`test_preset_in_use_cannot_delete` | FR-06-160・161・162・165 |
| `test_independent_individual_review` | FR-06-034 |
| `test_finding_kind_in_list_and_report` | FR-06-035 |
| `test_answers_xlsx_same_as_csv`・`test_answers_unknown_row_reported` | FR-06-043・044 |
| `test_approval_stale_after_new_version` | FR-06-054 |
| `test_record_has_all_items` | FR-06-074 |
| `test_no_certification_claims` | FR-06-076（API・xlsx・テンプレート・JS） |
| `test_optimistic_lock` | NFR-06-21 |
| `test_reviewer_forbidden` | NFR-06-22（承認・参考範囲の設定・プリセット削除が 403、文に実装語なし） |

未検証（本書の範囲で実行していないもの）: 画面の実機確認（Playwright MCP・全状態）、wire 適用後の既存ルートの権限と版番号照合、`check_clipping.py`。

## 10. 要判断

1. 種別ごとの必須役割・工程・既定の出口基準（3 章の表）は ISO/IEC 20246 を参考にした暫定値。
2. 頁の定義（要確認-13）が未決のため、頁数は人が入れる値（`r4.pages`）とした。
3. 検査速度の分母は会議時間、工数の合計は「準備の和＋会議時間」（会議時間を人数倍しない）。受入基準の数値に合わせた。
4. 既存の画面は `rev` を送らないため、既存ルートの版番号照合は `rev` があるときだけ行う（後方互換）。R4 の API は必須。
5. 「AI 時代の完了条件 4 項目」の文面は書籍付録 C.2 の構造を確かめずに自作した（原本は未確認）。
