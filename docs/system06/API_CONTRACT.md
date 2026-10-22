# System06 API 契約

出典: `web/routes/doc_assure.py`・`web/routes/doc_assure_extra.py`（機械的に拾った）。両 blueprint は `web/__init__.py` で登録される。
共通: 基底パスは `/api/docassure/inspections/<iid>`。`iid` は 12 桁の小文字 16 進。テナント境界は docverify の store が担う。

## 共通のエラー形式

`{"error": "<利用者向け文>", "code": "<code>"}`。権限不足（`perm.require`）の本文は docverify.perm 側で、この表には含めない。

| code | 状態 | 意味 |
|---|---|---|
| not_found | 404 | iid が不正か検査が無い（要件 ID 不明にも使う） |
| not_analyzed | 404 | 分析が未実行 |
| no_previous | 404 | 比較できる前の版が無い |

## エンドポイント

権限 op は `docverify.perm` の表。「なし」は op の指定が無い（検査が開ける利用者向け）。

| 方法 | パス（基底の後） | 権限 op |
|---|---|---|
| POST | /analyze | import_doc |
| GET | /requirements | なし |
| GET | /issues | なし |
| GET | /conflicts | なし |
| GET | /scores | なし |
| GET | /readiness | なし |
| GET | /trace | なし |
| GET | /analyzers | なし |
| POST | /decisions | finding_edit |
| GET | /diff | なし |
| POST | /review | finding_edit |
| GET | /report.md / .csv / .json | なし |
| GET | /tests | なし |
| GET | /impact | なし |
| POST | /alignment | なし |
| GET | /rewrite/<rid> | なし |
| GET | /regression | なし |
| POST | /baseline | finding_edit |
| GET | /baseline/compare | なし |
| POST | /feedback | finding_edit |
| GET | /feedback/stats | なし |
| GET | /policy | なし |
| PUT | /policy | plan_edit |

注意: `/issues` は応答のキーが `findings`。`/requirements` は testability も返す。
注意: POST /alignment・GET /tests・/impact は op の指定が無い（`wired=false` の JSON を返すだけ）。

## 入力と出力

### POST /analyze
- 入力: `documents`（任意。`id`・`name`・`type`・`text` の配列）、`profile`（pack 名、既定 default）。
- `documents` が無ければ検査の passages を 1 文書（id `D1`）にして分析する。
- 上限: 20 文書・合計 2,000,000 字。id 64 字・name 200 字。
- 出力: 分析結果全体（`source_texts` を除く）。主要キーは documents・requirements・findings・rule_results・testability・scores・conflicts・readiness・trace・analyzers・mode・errors・timings・counts・saved_at。
- エラー: bad_document 400、no_document 400、too_large 413、error 500。
- 既存の decisions は引き継いで適用する。監査ログに記録する。

### GET 各セクション
- 出力: `{<セクション名>: ..., mode, readiness}`。requirements のみ `testability` を追加。
- エラー: not_found、not_analyzed。

### POST /decisions
- 入力: `decision`（accepted / rejected / waived / resolved / conflict_decided）、`target`（finding_id または conflict_id、200 字）、`reason`（2,000 字）、`expiry`（waived は必須）。
- 出力: 201 `{ok, decision}`。記録後に全体を再分析して保存する。
- エラー: bad_decision・too_long・no_target・waiver_incomplete（すべて 400）。
- 注意: 画面の finding 用 waiver は期限必須。expiry の形式検証はルート側に無い（`SECURITY_REVIEW.md` が指摘）。期限が読めない値は再分析時に無効扱い。

### POST /review
- 入力: `confirm_send`（bool）。
- 出力: `mode`（AI / DEGRADED）・findings・unsupported・dismissed・provider・sends・cache_hits・failures。
- エラー: 送信先が openai で `confirm_send` が true でないと 409 `consent_required`（`destination` 付き）。
- 詳細は [AI_REVIEW.md](AI_REVIEW.md)。

### GET /diff・/impact・/regression
- 前の版（再分析前の requirements）との比較。前版が無ければ 404 no_previous。
- /diff は `{diff: [...]}`（意味差分。位置のみの変更は MOVED）。/impact は System09 向け JSON。/regression は条件・異常系の欠落候補。

### GET /report.<fmt>
- fmt は md・csv・json。それ以外は 400 bad_format。添付ファイル `document-assurance.<fmt>` として返す。

### POST /alignment
- 入力: `observed`（観測結果の配列、2,000 件まで）。出力: `{alignment, wired: false}`。エラー: bad_observed 400。

### GET /tests
- 出力: `{candidates, wired: false}`。NOT_TESTABLE の要件は候補でなく `required_clarification` を返す。

### GET /rewrite/<rid>
- 要件 ID の書き換え提案（原文は変更しない）。要件が無ければ 404 not_found。

### POST /baseline・GET /baseline/compare
- POST は現在の指摘を baseline に登録。201 `{ok, count}`。
- compare は登録済み baseline と現在の差分分類。未登録は 404 no_baseline。

### POST /feedback・GET /feedback/stats
- 入力: `kind`（useful / false_positive / not_applicable）、`finding_id`（200 字）。
- エラー: bad_kind・bad_finding_id（400）、finding_not_found（404）。201 `{ok, feedback}`。
- stats は要件数・指摘数を渡した集計。ルールは自動変更しない。

### GET・PUT /policy
- 保存できるキー: required_terms・ambiguous_terms・project_terms・disabled_rules（各 200 件以内、各語 100 字以内）。
- 未知のキー・型違いは 400 bad_policy。
- 注意: 保存のみで分析には反映されない（[RULE_ENGINE.md](RULE_ENGINE.md) 参照）。

関連: [USER_FLOW.md](USER_FLOW.md) / [SECURITY_REVIEW.md](SECURITY_REVIEW.md) / [README.md](README.md)
