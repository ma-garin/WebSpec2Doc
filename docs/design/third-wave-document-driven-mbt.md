# 第3弾 — 文書駆動MBT・手動手順書・テストデータ・実測バリデーション設計

- 状態: 実装合意済み
- 合意日: 2026-07-17
- 対象: P1-1 / P1-2 / P1-5 / P1-4

## 1. 目的

既存のAutoRun（URL駆動）を維持したまま、参考文書の要件を起点にテストモデル・
テストパス・自動/手動テスト成果物を生成する「文書駆動」を追加する。OpenAI未設定でも、
文書取り込みからパス生成、成果物生成、実行承認までをルールベースで完結させる。

## 2. スコープ

1. Doc Fusion / `req_tracer` の既存成果物をMBTモデルへ結合する。
2. ISTQB CT-MBTの語彙で頂点網羅・エッジ網羅・到達目標を選択できるようにする。
3. networkxで決定的なテストパスを生成する。
4. パスからPlaywright候補、手動テスト手順書（Markdown / Excel）を生成する。
5. 実測したフォーム制約から根拠付きテストデータ（JSON / CSV）を生成する。
6. テストデータを入力のみしてクライアント側挙動を観測し、送信せずJSONへ記録する。
7. AutoRunにURL駆動 / 文書駆動のモード切替と文書駆動設定を追加する。

## 3. 非スコープ

- LLMによる要件・期待結果の断定。LLMは既存の任意補完を超えて必須にしない。
- GraphWalker / AltWalkerの同梱。
- フォーム送信、保存、決済、削除など副作用を持つ操作。
- 文書だけから実在しない画面・項目・遷移を補うこと。

## 4. 正式用語

- **URL駆動**: URLの実測を起点にする既存AutoRun。
- **文書駆動**: 参考文書の要件を起点に、実測済み画面と突合してテストを設計するAutoRunモード。
- **テスト選択基準**: 頂点網羅 / エッジ網羅 / 到達目標。
- **実測バリデーション**: フォームへ値を入力するが送信せず、ブラウザで観測できた制約だけを記録する工程。

## 5. 合意済みの公開境界（TDD seam）

### S1: MBTエンジン

- 入力: `screen_transition_graph.json`、`requirement_trace.json`、選択基準、任意の到達目標。
- 出力: ノード・エッジ・要件対応・決定的なテストパス・網羅率を持つJSON互換データ。
- 契約: 同一入力は同一順序。未到達ノードを捏造せず明示する。上限超過は切り詰め理由を残す。

### S2: 成果物生成

- 入力: MBT出力、`report.json`、`playwright_candidates.json`。
- 出力: `document_mbt.json`、`manual_test_procedures.md/.xlsx`、`test_data.json/.csv`。
- 契約: 各行に要件ID・画面ID・evidence種別を残す。期待結果は「生成・レビュー必須」と明記する。

### S3: 実測バリデーション

- 入力: reportの実測ロケータ、根拠付きテストデータ、保存済みセッション（任意）。
- 出力: `validation_observations.json`。
- 契約: 許可操作は `goto` / `fill` / `press` を伴わないblur相当のみ。submit/click/Enterは生成・実行しない。
  network interceptorでPOST/PUT/PATCH/DELETEを常時遮断する。SPAのフォーム準備完了までは読取通信を許可し、
  値を入力する直前からGETを含む全HTTP送信とWebSocketのクライアント送信を遮断する。遮断件数は
  全送信と破壊的メソッドに分けて出力する。

### S4: AutoRun API

- `POST /api/autorun/start` が `mode`、`reference_docs`、`selection_criterion`、`target_page_id`、
  `observe_validation` を受ける。
- 文書駆動は参考文書を1件以上必須とし、既存のテナント配下パス検証を通ったファイルだけを利用する。
- status APIの `step_data.document_mbt` と `outputs` から生成件数・成果物へ到達できる。

### S5: UIフロー

- AutoRun左ペイン上部に「URLから実測」「文書から設計」を置く。
- 文書駆動では対象URL、参考文書、テスト選択基準、到達目標、実測バリデーション設定を表示する。
- 実行承認前に要件数・対応画面数・パス数・推定網羅率を表示する。
- URL駆動の既存初期状態・操作・API payloadは変えない。

## 6. データモデル

### DocumentMbtModel

- `selection_criterion`: `vertex_coverage | edge_coverage | reached_target`
- `nodes`: page_id / title / url / requirement_ids / evidence
- `edges`: from / to / trace_id
- `paths`: path_id / node_ids / edge_ids / requirement_ids / candidate_ids / review_required
- `coverage`: covered / total / rate / unreachable_node_ids
- `source_files`: 参考文書のファイル名のみ（絶対パスを外部出力しない）

### TestDataCase

- `case_id`、`page_id`、`field_name`、`locator`、`category`
- `value`、`expected_client_behavior`、`source_constraint`、`evidence`
- category: `boundary | equivalence | required | format | option`

### ValidationObservation

- `case_id`、`page_id`、`field_name`、`observed_value`
- `accepted`、`validation_message`、`input_length`、`blocked_request_count`
- `claim_scope`: 常に `client_observed_without_submit`

## 7. パス生成規約

- 頂点網羅: entry nodeから各到達可能ノードへの最短パスを生成する。
- エッジ網羅: entry nodeから各edge始点への最短パスに対象edgeを連結する。
- 到達目標: entry nodeから指定page_idへの最短パスを1件生成する。
- entry nodeが無い循環グラフは辞書順先頭ノードをentryとして扱い、理由をsummaryへ残す。
- パスは `(長さ, node_ids)` で安定ソートし、最大100件とする。

## 8. テストデータ規約

- maxlength=N: N-1 / N / N+1文字の日本語。
- minlength=N: N-1 / N / N+1文字（0未満は生成しない）。
- required: 空文字と型別正常値。
- email: 正常形式 / 不正形式。number: min/maxの内外点。
- options: 先頭・末尾の実測選択肢。選択肢外の値は送信しない。
- 制約が実測できない項目には推測データを生成しない。

## 9. 期待画面状態

- 初期表示は従来どおり「URLから実測」で、既存フォームの高さ・開始導線を変えない。
- 「文書から設計」を選ぶと、参考文書アップロードと選択基準が同じ左ペイン内に展開する。
- 到達目標を選んだ場合だけpage_id入力を表示する。
- 実測バリデーションの横に「入力のみ・送信しません」を常時表示する。
- 完了時の成果物欄へMBTモデル、手順書、テストデータ、観測結果を追加する。

## 10. テスト計画

1. S1: worked exampleで頂点/エッジ/到達目標のパスと網羅率を固定する。
2. S2: JSON/CSV/Markdown/Excelを公開関数経由で生成し、要件/evidence/review表示を確認する。
3. S3: 外部境界の偽ページを使い、送信操作・破壊的リクエストが0であることを確認する。
4. S4: APIで不正パス拒否、文書必須、テナント分離、status/output契約を確認する。
5. S5: 1366x768 / 1920x1080でモード切替、条件表示、開始payload、承認要約をE2E確認する。
6. `make test` → `make verify-ui` → スクリーンショット目視 → `./scripts/verify.sh`。

## 11. 実装順序

1. S1 MBTエンジン
2. S2 テストデータ・手順書
3. S3 実測バリデーション
4. S4 AutoRun配線
5. S5 UI配線
