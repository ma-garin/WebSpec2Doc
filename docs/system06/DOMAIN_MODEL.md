# System06 ドメインモデル

実コード（`web/services/docassure/model.py` ほか）を読んで書いた事実だけを載せる。
共通型はすべて frozen dataclass か JSON 化できる dict。分析結果は `assurance.json` に保存する（`store.py`）。

## 出所（Provenance）と状態（Status）は別軸

| 軸 | 値 | 意味 |
|---|---|---|
| 出所 | OBSERVED | 原文にそのまま書かれている |
| 出所 | DERIVED | 決定論の変換で導いた（秒換算・分割） |
| 出所 | INFERRED | 推測で補った。事実ではない |
| 状態 | CANDIDATE | 検出しただけ。確定は人が行う |
| 状態 | CONFIRMED / REJECTED | 確定 / 却下 |
| 状態 | UNKNOWN / NOT_EVALUATED / BLOCKED | 未確認 / 評価不能 / 進めない |

- 出所は「値がどう得られたか」、状態は「結論の確度」。AI 推論を OBSERVED にしない規律。
- ルール結果は PASS / FAIL / NOT_APPLICABLE / NOT_EVALUATED の 4 値。
- 重大度は critical / high / medium / low / info の 5 段。
- 検出元は deterministic / ai / hybrid / human（定数。hybrid は現状の検出器では使っていない）。

## Entity 一覧

| Entity | 実体 | 定義場所 |
|---|---|---|
| Document | dict（id・name・type・hash） | `pipeline.analyze` |
| Section | dict（見出し・行範囲・hash） | `requirement_engine.sections` |
| RequirementUnit | frozen dataclass | `model.py` |
| Location | frozen dataclass | `model.py` |
| Field | frozen dataclass | `model.py` |
| Finding | frozen dataclass | `model.py` |
| Score | frozen dataclass | `model.py` |
| Conflict | dict | `conflict.py` |
| Decision | dict | `store.add_decision` |
| Trace node / edge | dict | `trace_graph.py` |
| Readiness | dict | `readiness.gate` |

## RequirementUnit

| フィールド | 内容 |
|---|---|
| requirement_id | 原文の ID（REQ-001 等）。無ければ `RU-<doc>-<連番>` |
| document_id | 所属文書 |
| location | 原文への戻り先（下記） |
| raw_text | 原文 |
| fields | 項目名 → Field。語が無い項目は入れない |
| kind | functional / nfr / business_rule / security_rule / constraint |
| parent_id / split | 分割で生じた単位は元の ID と True |
| fingerprint | 意味指紋。位置が変わっても同じ（差分・baseline が使う） |

- fields の項目: actor / trigger / condition / action / object / expected_result / exception / constraint / timing / quantity / state / priority / acceptance_criteria。
- 抽出器が実際に作る項目は actor・trigger・condition・action・object・expected_result・exception・constraint・timing・quantity・priority と、導出値 timing_seconds。state・acceptance_criteria は model のコメントにあるが、`requirement_engine.py` の抽出では作っていない（参照のみ）。
- kind は正規表現で判定（認証語→security_rule、数値＋応答等→nfr、不可・歳以上等→business_rule、他→functional）。constraint は判定されない。

## Location

| フィールド | 内容 |
|---|---|
| document_id | 文書 ID |
| section | 見出しパス（例 `3 > 3.2`） |
| line_start / line_end | 1 始まり。0 は不明 |
| snippet | 120 字以内 |
| snippet_hash | snippet 元文の sha1 先頭 12 桁。改変検出に使う |

- 全文は複製しない。`finding_dict_valid` は rule_id・document_id・snippet_hash が無い指摘を無効とする。

## Finding

| フィールド | 内容 |
|---|---|
| finding_id | `<rule_id>:<requirement_id または L行番号>:<n>` |
| rule_id / rule_version | 検出したルール |
| result | FAIL（指摘）が基本 |
| severity / title / why_matters / reason / how_to_fix | 説明 5 点 |
| location / requirement_id | 戻り先 |
| source | deterministic / ai |
| status | 既定 CANDIDATE |
| confidence / confidence_basis / counter_evidence | 確度・根拠・反証 |

- 人の判断後は status が ACCEPTED / REJECTED / RESOLVED / WAIVED に変わる（`decisions.py`）。
- 期限切れ waiver は CANDIDATE に戻り `waiver_expired: true` が付く。

## Score

- 項目: name・value・coverage（0〜1）・explanation・included・not_evaluated。
- value が None は評価不能。指摘 0 件を 100 点にしない。詳細は `QUALITY_MODEL.md`。

## Conflict

- 項目: conflict_id（`CF-` + sha1 10 桁）・topic・kind・evidence・status・truth・hints・severity・confidence・question。
- 検出時は status=UNRESOLVED、truth=UNKNOWN 固定。どちらが正しいかは決めない。
- kind は numeric / permission / temporal / semantic_candidate。重大度は順に high / high / medium / medium。
- hints（newer_version・higher_authority・majority）はヒントで正誤の判定ではない。

## Decision（人の判断）

- 項目: target・decision・reason・expiry・by・source（`human`）・at。
- decision の値: accepted / rejected / waived / resolved / conflict_decided。
- 同じ target は後勝ち。再分析しても残る。`source=human` 以外は適用されない。

## 保存物

| ファイル | 内容 |
|---|---|
| `assurance.json` | 分析結果・decisions・source_texts・previous_requirements・review |
| 他のサイドカー | policy・baseline・feedback（`_sidecar.py` 経由） |

- 保存は一時ファイル＋置換で原子的。decisions の追記は排他ロック付き。
- 検査 ID の形式検証とテナント境界は docverify の `doc_dir` が担う。

関連: [RULE_ENGINE.md](RULE_ENGINE.md) / [TRACEABILITY.md](TRACEABILITY.md) / [QUALITY_MODEL.md](QUALITY_MODEL.md)
