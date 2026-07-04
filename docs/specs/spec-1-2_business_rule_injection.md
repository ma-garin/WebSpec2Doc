# SPEC-1-2 業務ルールのテスト観点・境界値注入（Doc Fusion Phase 2）

| 項目 | 値 |
|---|---|
| WBS | 1-2（docs/0703-01_plan.md） |
| 優先度 / 見積 | P1 / 0.5sp |
| 依存 | 1-1（`DocumentedRule` と LLM 抽出） |
| 背景 | docs/11 §6-2 機能④（B3 境界値生成と直結） |

## 1. 目的と背景

画面の DOM からは maxlength・required 等の**実装済みバリデーション**しか読めない。SPEC-1-1 が文書から抽出する業務ルール（「振込限度額 100 万円/日」「税額 = 課税対象額 × 10%」）は DOM に現れないため、現行のテスト条件生成（`analyzer/test_conditions.py::derive_conditions`）では永遠にテストされない。本タスクは抽出済み `DocumentedRule` を対応画面・項目のテスト条件へ**文書由来 confidence（≤0.9）付きで注入**し、限度値ルールからは境界値 3 点（n-1 / n / n+1）を生成する。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `analyzer/test_conditions.py` — `TestCondition`（description・source・confidence・evidence・observed_result）、`derive_conditions_with_evidence`（DOM 由来 = `SOURCE_RULES`・confidence 1.0）、境界値の書式前例 `_length_conditions`（`最大長: {n-1}/{n}/{n+1}文字`）
- 済: `generator/json_reporter.py::_field_dict` — `test_conditions_detail` に description/source/confidence/evidence/observed_result を出力
- 済: `ingest/matcher.py::fuse` — 画面対応（`ScreenMatch`）と項目対応（`_field_score`・貪欲 1 対 1）。矛盾検出の前例 `_mismatches`（必須・桁数）
- 未: ルール→フィールド対応・`SOURCE_DOCUMENT`・`TestCondition` への文書 evidence 添付・report.json への注入経路

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: 限度値ルール（kind="limit"・expression から数値抽出可）が対応フィールドに境界値条件として注入される（Given: 「上限 1000000」ルールと対応フィールドを持つ FusionResult / When: report.json 生成 / Then: `test_conditions_detail` に `文書ルール境界値: 999999/1000000/1000001` 相当・source="document"）
- **AC-2**: 計算式ルール（kind="calculation"）は対応画面の項目に紐づかない場合、画面レベル条件として注入され、description にルール原文（quote）由来の表現を含む
- **AC-3**: 文書由来条件はすべて `source="document"`・`confidence ≤ 0.9`（= 元ルールの confidence を引き継ぐ）・`doc_evidence`（file・location・quote）付き
- **AC-4**: 同一フィールドで DOM 由来（source="rules"・confidence 1.0）と文書由来が併存し、既存の DOM 由来条件が 1 件も変化しない
- **AC-5**: ルールが 1 件も対応づかない実行では report.json にキー・値の差分が生じない（`doc_evidence` キーは文書由来条件にのみ付く — report_hash 互換）
- **AC-6**: 文書の限度値と実測の `max_value`/`maxlength` が矛盾する場合、`FieldGap(kind="mismatch")` が追加され doc_fusion.md に両根拠付きで載る

## 3. スコープ外

- 権限条件ルール（kind="permission"）の実行可能テスト化（ロール切替の実測ができないため、条件文注入のみで検証手段は提示しない）
- 計算式の**評価**（式をパースして期待値を計算することはしない — 根拠のない推定値になる。原文提示に留める）
- Web UI でのルール表示（SPEC-1-5）・Excel（spec.xlsx）への注入（report.json / html の後続反映は既存経路に任せる）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 変更 | `src/analyzer/test_conditions.py` | `SOURCE_DOCUMENT = "document"` 追加・`TestCondition` に `doc_evidence`（既定 None） |
| 新規 | `src/analyzer/rule_injector.py` | ルール→フィールド/画面対応・境界値展開・`TestCondition` 生成 |
| 変更 | `src/ingest/matcher.py` | `fuse` で limit ルール vs 実測属性の矛盾検出（`_mismatches` に並置） |
| 変更 | `src/main.py` | `_run_doc_fusion` の戻り値を `DocFusionOutcome` に変更し `save_outputs` へ `rule_conditions` を伝播 |
| 変更 | `src/generator/json_reporter.py` | `generate_json_report`/`_screen_dict`/`_form_dict`/`_field_dict` に `rule_conditions` を透過（**該当フィールドのみ追記**） |
| 変更 | `tests/test_test_conditions.py` ほか | 単体テスト追加（§6-1） |
| 変更 | `quality/feature_contracts.yml` | doc_fusion 契約に rule_injector・failure_modes（`rule_unmatched` / `rule_value_unparsable`）追記 |

### 4-2. データモデル

```python
# src/analyzer/test_conditions.py（既存 TestCondition に末尾追加 — 後方互換）
SOURCE_DOCUMENT = "document"

@dataclass(frozen=True)
class TestCondition:
    description: str
    source: str                  # "rules" / "llm" / "document"
    confidence: float
    evidence: SourceEvidence | None
    observed_result: str = ""
    doc_evidence: DocumentEvidence | None = None  # 新規: 文書由来条件の根拠

# src/main.py（_run_doc_fusion の戻り値）
@dataclass(frozen=True)
class DocFusionOutcome:
    official_names: dict[str, str] = field(default_factory=dict)
    # (page_id, field.name) → 注入する文書由来条件。field.name 空はページレベル条件
    rule_conditions: dict[tuple[str, str], tuple[TestCondition, ...]] = field(default_factory=dict)
```

### 4-3. 処理フロー

```text
main.run
  ├─ _run_doc_fusion(analyzed_pages, reference_docs, output_dir)
  │    ├─ fuse(pages, bundle)                       # 既存 + limit 矛盾検出
  │    └─ build_rule_conditions(result, bundle, pages)  # 新: rule_injector
  └─ save_outputs(..., official_names=..., rule_conditions=...)
       └─ generate_json_report → _field_dict で test_conditions_detail 末尾に追記
```

## 5. 詳細設計

### 5-1. 関数シグネチャ

```python
# src/analyzer/rule_injector.py
def build_rule_conditions(
    result: FusionResult,
    bundle: DocumentBundle,
    pages: list[AnalyzedPage],
) -> dict[tuple[str, str], tuple[TestCondition, ...]]:
    """抽出ルールを画面対応（result.screen_matches）に沿って各フィールドへ割り当てる。
    画面対応: rule.screen_name と ScreenMatch.screen.name / screen_id の一致（正規化比較）。
    項目対応: rule.field_name と FieldData.name / aria_label / placeholder の類似
    （ingest.matcher._name_similarity と同じ SequenceMatcher・しきい値 0.6）。
    項目対応が無い calculation/limit ルールは (page_id, "") のページレベル条件にする。
    どの画面にも対応しないルールは注入しない（rule_unmatched を警告ログ）。"""

def boundary_conditions_from_limit(rule: DocumentedRule) -> tuple[str, ...]:
    """expression から数値を抽出し（tables.parse_max_length を流用）、
    "文書ルール境界値({expression}): {n-1}/{n}/{n+1}" を返す。
    数値が取れない場合は空 tuple（推定しない — rule_value_unparsable を警告ログ）。"""

def condition_from_rule(rule: DocumentedRule, descriptions: tuple[str, ...]) -> tuple[TestCondition, ...]:
    """source=SOURCE_DOCUMENT・confidence=rule.confidence・evidence=None・
    doc_evidence=rule.evidence の TestCondition 群を返す。evidence 無しルールは生成しない。"""

# src/ingest/matcher.py（fuse 内部から呼ぶ・_mismatches と同列）
def _rule_mismatches(
    page_id: str, rules: list[DocumentedRule], crawled: list[FieldData]
) -> list[FieldGap]:
    """limit ルールの数値と実測 maxlength/max_value の不一致を FieldGap(mismatch) にする。
    detail 例: "限度値が矛盾: 文書では 1000000（<quote>）、実測 max=999999"。"""

# src/generator/json_reporter.py（キーワード引数・既定 None で後方互換）
def generate_json_report(..., rule_conditions: dict[tuple[str, str], tuple] | None = None) -> dict: ...
```

`_field_dict` では既存の `attach_observed_validation(derive_conditions_with_evidence(field), ...)` の結果に、`rule_conditions.get((page_id, field.name), ())` を**末尾連結**する。dict 化の際 `doc_evidence` は `document_evidence_to_dict`（`ingest/models.py`）で変換し、**None のときはキー自体を出さない**。

### 5-2. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| ルールがどの画面にも対応しない | 注入せず継続 | 警告ログ「注入先画面なし: RULE-xxx」＋ doc_fusion.md の documented_rules に注入状況列（unmatched） |
| expression から数値抽出不能 | 境界値化せず description のみの条件を 1 件注入 | 条件文に「（数値化不能・原文参照）」を含める |
| rule.evidence が None | 条件を生成しない（evidence-only 原則） | 警告ログ「根拠のないルールを除外」 |
| ページレベル条件の重複（同一ルールが複数フィールドに一致） | 類似度最高の 1 フィールドのみに注入（貪欲 1 対 1 — `_match_fields` と同方針） | なし |

### 5-3. 既存コードとの接続点

- `analyzer/test_conditions.py::SOURCE_RULES` / `SOURCE_LLM` — 定数の並びに `SOURCE_DOCUMENT` を追加
- `ingest/matcher.py::_name_similarity`・`_FIELD_NAME_THRESHOLD` — 項目対応の類似判定を再利用（独自実装しない）
- `ingest/tables.py::parse_max_length` — expression の数値抽出（"100万円" は 100 を返す点に注意 — §8）
- `generator/json_reporter.py:148` 付近 `test_conditions_detail` — 注入位置
- `main.py:318` 付近 `_run_doc_fusion` 呼び出しと `save_outputs(..., official_names=...)` — `DocFusionOutcome` への差し替え

## 6. テスト仕様

### 6-1. 単体テスト（新規 tests/test_rule_injector.py）

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_limit_rule_injected_as_boundary | limit ルール（"1000000"）＋対応フィールド | 条件に "999999/1000000/1000001"・source="document" | AC-1 |
| test_calculation_rule_page_level | field_name 空の calculation ルール | (page_id, "") キーに条件・description に quote | AC-2 |
| test_injected_confidence_capped | confidence 0.9 のルール | 条件 confidence == 0.9・doc_evidence 付き | AC-3 |
| test_dom_conditions_unchanged | 注入あり実行の report dict | 既存 source="rules" 条件が件数・内容とも不変 | AC-4 |
| test_no_rules_no_schema_change | rule_conditions=None | report.json が現行実装と bit 一致（doc_evidence キーなし） | AC-5 |
| test_limit_mismatch_gap | 文書 1000000 vs 実測 maxlength=7 相当 | FieldGap(kind="mismatch")・detail に両値 | AC-6 |
| test_unmatched_rule_logged | 対応画面なしのルール | 注入 0 件・caplog に "注入先画面なし" | 5-2 |
| test_unparsable_expression | expression="別表参照" | 境界値なし・description のみの条件 1 件 | 5-2 |

### 6-2. 結合テスト

- `load_reference_documents`（フェイク LLM で limit ルール）→ `fuse` → `build_rule_conditions` → `generate_json_report` の通しで、report.json の該当フィールドに文書由来条件が現れ、他フィールドが不変であること（tmp_path・実ファイル I/O）

### 6-3. 回帰確認

- 既存ユニット全件 PASS。特に `tests/test_doc_fusion.py` 19 件と json_reporter 系（`TestCondition` へのフィールド追加は既定値で吸収）
- `docs/demo/sample_output/report.json` 相当の既存入力で report_hash が不変（AC-5）

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜6 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] feature_contracts.yml 更新（rule_injector・failure_modes 追記）
- [ ] 実行パス確認: CLI で限度値ルール入り参考文書を指定してクロールし、report.json の test_conditions_detail に source="document" 条件が載ること・doc_fusion.md に矛盾が載ることを目視確認

## 8. このタスク固有の罠

- **`parse_max_length` は「100万円」から 100 を返す**（最初の数字列のみ）。単位語（万・千・億）を伴う場合の換算を `boundary_conditions_from_limit` 側で行うか、換算不能として「数値化不能」扱いに倒すかを決めること。**推測で 1000000 に補完してはならない**（根拠は expression の原文提示で担保する）
- `TestCondition` は frozen dataclass で既存テスト・`dataclasses.replace`（`attach_observed_validation`）が多用している。**`doc_evidence` は必ず既定値付き末尾追加**。途中挿入は位置引数の生成箇所を全滅させる
- `report_hash` は screens 部の canonical JSON から計算される（`json_reporter.py:47`）。文書由来条件を**無条件で空 doc_evidence: null 付き出力にするとハッシュが全ユーザーで変わる**。キーは値がある時のみ出す（前例: `official_name`）
- analyzer 層から `ingest.models.DocumentEvidence` を import するのは可（`ingest.matcher` が analyzer を import している相互関係が既にある）が、**rule_injector から generator を import しない**（層の依存方向: CONVENTIONS §1-1）
- ページレベル条件（field.name=""）は `_field_dict` では出力できない。`_screen_dict` の画面直下に `document_conditions` キーとして**値がある時のみ**追加する（フォームなし画面でもルールを落とさないため）
