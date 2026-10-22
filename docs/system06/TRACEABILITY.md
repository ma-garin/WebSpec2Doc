# System06 トレーサビリティ

対象: `trace_graph.py`・`coverage.py`・`pipeline.py` の trace 段。LLM は使わない。

## ノード型

| 型 | 作られ方 |
|---|---|
| Document | 文書ごと（`DOC:<id>`） |
| Section | 要件の見出しパスがあるとき（`SEC:<doc>:<path>`） |
| Requirement | kind が business_rule 以外の要件（`REQ:<id>`） |
| BusinessRule | kind が business_rule の要件 |
| Screen | 要件原文の「〜画面」（`SCR:<名前>`） |
| API | 原文の `GET /path` 形式、または `/api/...`（`API:<path>`） |
| Test | `build(tests=...)` に渡したテスト（`TEST:<id>`） |
| Evidence | `build(evidence=...)` に渡した証跡（`EVD:<id>`） |

## 辺（edge）

| kind | 向き | 出所 | 根拠 |
|---|---|---|---|
| contains | 文書・節 → 要件 | OBSERVED | 見出し構造 |
| mentions | 要件 → Screen/API | OBSERVED | 原文にその語 |
| references | 要件 → 要件 | EXPLICIT | 原文に他要件の ID |
| relates | 別文書の要件どうし | INFERRED | 語の重なり dice が 0.35 以上 |
| verifies | Test → 要件 | EXPLICIT または INFERRED | テストの要件 ID、無ければ dice 0.35 以上 |
| exercises | Test → API | OBSERVED | テスト文中の API |
| evidences | Evidence → Test | EXPLICIT | 証跡の test_id |

- 辺は必ず provenance・confidence・basis を持つ。INFERRED の basis に「推測。明示リンクではない」と書く。
- 出所は EXPLICIT / OBSERVED / DERIVED / INFERRED。DERIVED の辺は現状作られない。
- 同じ文書内の要件どうしの relates は作らない。ID 参照がある組は relates を重ねない。
- `filter_by_provenance`・`neighborhood` で絞り込み・近傍取得ができる。

## 孤立（orphans）

すべて status=CANDIDATE。「見つからなかった」であって欠陥・未作成の断定ではない。

| kind | 条件 |
|---|---|
| requirement_without_design | Screen/API への mentions が無い |
| requirement_without_test | 自分を検証する verifies が無い |
| api_without_requirement | その API に mentions する要件が無い |
| test_without_requirement | 検証先の要件が無い |

## Coverage（段）

`coverage.compute(graph, execution=None)` が段ごとに別の指標を返す。各指標は count・total・ratio。

| 段 | 数え方 |
|---|---|
| requirement | Requirement と BusinessRule の数 |
| design | Screen/API を mentions する要件 |
| test_designed | verifies 辺を持つ要件 |
| execution | 実行結果のあるテストを持つ要件 |
| passed | 実行したテストがすべて合格の要件 |
| verified | 全テストが実行済み、合格、かつ明示リンクあり |

- 補助指標 test_designed_explicit は EXPLICIT の verifies を持つ要件のみ。
- ratio は total が 0 なら None。0% にしない。
- 「テスト案がある」は「実行済み」ではない。

## 実行 Evidence 未取込の扱い

- `execution` が無いとき execution・passed・verified は None、status は NOT_EVALUATED。0% にしない。
- 実行結果の取込口（API・画面）は実装が無い。`compute` に dict を渡す関数口だけがある。
- `pipeline.analyze` は `trace_graph.build(units_by_doc)` を tests・evidence なしで呼ぶ。結果:
  - Test・Evidence ノードは作られない。
  - test_designed は 0 件になり、全要件が requirement_without_test の候補になる。
  - execution・passed・verified は常に NOT_EVALUATED。
- Traceability スコアの not_evaluated 欄に「テスト実行 Evidence は未取込」と出る。

## Traceability スコア

- 文書が 2 本以上かつ trace 段が成功したときだけ数値化する。単一文書は None（評価不能）。
- 要件ごとに最強の辺を採る。references・mentions・verifies は 1.0、relates（推論）は 0.5。contains は数えない。
- スコア = 100 × 平均。比率は `trace.linked_ratio` に入り、準備状態ゲートの trace coverage に使われる。
- 注意: mentions は要件→Screen/API の辺で、設計文書の本文との照合ではない。

## UI と API

- API: `GET /api/docassure/inspections/<iid>/trace`（graph と coverage を返す）。
- 画面: 「Trace」タブ。
- テスト候補 `GET .../tests` は System02 向け JSON を返すだけで送信しない（`wired=false`）。

関連: [QUALITY_MODEL.md](QUALITY_MODEL.md) / [API_CONTRACT.md](API_CONTRACT.md) / [README.md](README.md)
