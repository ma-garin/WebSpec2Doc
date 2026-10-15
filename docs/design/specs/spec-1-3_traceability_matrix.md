# SPEC-1-3 RFP 要件トレーサビリティマトリクス（Doc Fusion Phase 3）

| 項目 | 値 |
|---|---|
| WBS | 1-3 |
| 優先度 / 見積 | P2 / 1sp |
| 依存 | 1-1（LLM 抽出基盤・`DocumentBundle` 拡張の作法） |
| 背景 | docs/11 §6-2 機能③（要件カバレッジマトリクス — 受入テストの基盤） |

## 1. 目的と背景

RFP・要件一覧に書かれた要件が「どの画面で実装され、どのテストケースで検証されるか」を追跡できる成果物が無い。本タスクは参考文書から `DocumentedRequirement` を抽出し、実測画面（`ScreenMatch` の機構）とテストケース（report.json の test_conditions / playwright_candidates.json）へマッピングした**要件トレーサビリティマトリクス**を出力する。対応先が見つからない要件は「**未実装疑い**」として、文書 evidence と免責注記付きで提示する。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `web/services/traceability.py::build_matrix` — **実測画面を行とする**カバレッジ表（`RequirementLink`: 画面 URL × playwright candidates × meta.json の tests）。文書由来の要件は扱っていない。`web/routes/traceability.py` に `/traceability/matrix` API と `partials/view-traceability.html` 既存
- 済: `ingest/tables.py::structure_table` — 列名シノニムによる表解釈（画面一覧・項目定義の 2 種のみ）。`looks_like_header` に要件系シノニムは未登録
- 済: `ingest/matcher.py::_match_screens` — スコア降順貪欲法の画面対応（URL 一致 > 名称類似 0.6）
- 未: 要件モデル・要件表の構造化・要件→画面→テストの連鎖・未実装疑いの出力

**重複禁止**: 既存 `web/services/traceability.py` は「画面 = 要件とみなす」暫定実装。本タスクはこれを**置き換えず**、文書要件がある場合の追加データ源として接続する（§5-3）。

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: 要件表（要件ID・要件名列を持つ xlsx/md 表）から `DocumentedRequirement` が evidence 付きで抽出される（Given: 要件表を含む md / When: `load_reference_documents` / Then: `bundle.requirements` に req_id・title・DocumentEvidence）
- **AC-2**: 自由文 RFP からも LLM で要件が抽出される（SPEC-1-1 のスキーマに requirements 配列を追加。幻覚フィルタ・confidence ≤0.9 は SPEC-1-1 と同一機構）
- **AC-3**: 各要件が対応画面（page_id・score・method）へマッピングされ、`requirement_trace.json` に載る（対応判定は要件文と画面タイトル・見出し・official_name の類似 — `_match_screens` と同アルゴリズム）
- **AC-4**: 対応画面のテストケース ID（report.json の test_conditions_detail 由来の条件と、存在すれば playwright_candidates.json の candidate id）が要件行に紐づく
- **AC-5**: 対応画面が見つからない要件は `status="unimplemented_suspect"` として出力され、traceability_matrix.md に「文書の鮮度に依存する疑いであり断定ではない」旨の注記が付く
- **AC-6**: 要件が 1 件も無い参考文書では `requirement_trace.json` / `traceability_matrix.md` を生成しない（オプトイン — 既存出力ファイル集合が不変）
- **AC-7**: `/traceability/matrix` API は `requirement_trace.json` 存在時のみ応答に `document_requirements` キーを追加し、無い場合は現行応答と完全一致

## 3. スコープ外

- view-traceability.html への要件行の描画（テンプレート変更を伴う UI 表示は SPEC-1-5 以降。本タスクは API の追加キーまで — テンプレート・JS を変更しないため verify-ui 不要の範囲に収める）
- 要件の階層（親子要件・派生要件）の表現（フラットな 1 要件 = 1 行のみ）
- テスト**実行結果**（PASS/FAIL）との突合（テストケースの存在までを追跡する）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 変更 | `src/ingest/models.py` | `DocumentedRequirement` 追加・`DocumentBundle.requirements`（既定 `()`） |
| 変更 | `src/ingest/tables.py` | `REQUIREMENT_KEYS` シノニム・`structure_requirement_table`・`looks_like_header` への登録 |
| 変更 | `src/ingest/llm_extractor.py` | 抽出スキーマに `requirements` 配列追加（SPEC-1-1 の幻覚フィルタを通す） |
| 変更 | `src/ingest/loader.py` | 要件表・LLM 由来要件の収集と `DocumentBundle.requirements` への統合 |
| 新規 | `src/ingest/req_tracer.py` | 要件→画面→テストケースの連鎖構築 |
| 新規 | `src/generator/trace_reporter.py` | `requirement_trace.json` / `traceability_matrix.md` の出力 |
| 変更 | `src/main.py` | `_run_doc_fusion` 内で requirements 非空時のみ trace 出力 |
| 変更 | `web/routes/traceability.py` | `requirement_trace.json` 存在時に応答へ `document_requirements` を追加 |
| 変更 | `tests/test_doc_fusion.py` ほか | 単体テスト追加（§6-1）・新規 `tests/test_req_tracer.py` |
| 変更 | `quality/feature_contracts.yml` | doc_fusion 契約に req_tracer/trace_reporter・failure_modes（`requirement_unmatched`）追記 |

### 4-2. データモデル

```python
# src/ingest/models.py に追加
@dataclass(frozen=True)
class DocumentedRequirement:
    """文書に記載された要件（RFP・要件一覧の 1 行または 1 文）。"""

    req_id: str                  # 文書の要件ID。無ければ "REQ-{連番}" を採番
    title: str
    description: str = ""
    category: str = ""           # 機能 / 非機能 等（文書記載のまま。無ければ ""）
    source: str = "table"        # "table" / "llm"
    confidence: float = 1.0      # LLM 由来は ≤0.9（SPEC-1-1 と同一規約）
    evidence: DocumentEvidence | None = None

# src/ingest/req_tracer.py
@dataclass(frozen=True)
class RequirementTrace:
    """1 要件の追跡結果。"""

    requirement: DocumentedRequirement
    status: str                       # "covered" / "screen_only" / "unimplemented_suspect"
    page_id: str = ""                 # 対応画面（未対応は ""）
    page_url: str = ""
    match_score: float = 0.0
    match_method: str = ""            # "name" / "official_name"
    test_condition_count: int = 0     # 対応画面の test_conditions_detail 件数
    candidate_ids: tuple[str, ...] = ()  # playwright_candidates.json の id
```

### 4-3. 処理フロー

```text
_run_doc_fusion（main.py）
  ├─ load_reference_documents → bundle（requirements 含む）
  ├─ fuse(pages, bundle) → FusionResult（既存）
  ├─ [requirements 非空] trace_requirements(bundle, result, pages, output_dir)
  │    ├─ 要件→画面: title+description と 画面タイトル/見出し/official_name の類似（貪欲 1 対 1 ではなく多対 1 可）
  │    ├─ 画面→テスト: pages の各フィールド条件件数 + output_dir/playwright_candidates.json（存在時のみ）
  │    └─ status 判定: 画面なし→unimplemented_suspect / 画面のみ→screen_only / テストあり→covered
  └─ save_trace_outputs(traces, output_dir) → requirement_trace.json / traceability_matrix.md
```

## 5. 詳細設計

### 5-1. 関数シグネチャ

```python
# src/ingest/tables.py
REQUIREMENT_ID_KEYS = ("要件id", "要件no", "要求id", "req", "reqid", "要件番号")
REQUIREMENT_NAME_KEYS = ("要件名", "要件", "要求事項", "要求", "requirement", "機能要件")

def structure_requirement_table(table: ExtractedTable) -> list[DocumentedRequirement]:
    """要件名列を持つ表を要件一覧として解釈する。項目定義・画面一覧と競合した場合は
    structure_table の判定を優先し、要件名列がありかつ項目名列が無い表のみ対象とする。"""

# src/ingest/req_tracer.py
def trace_requirements(
    bundle: DocumentBundle,
    result: FusionResult,
    pages: list[AnalyzedPage],
    candidates: list[dict],          # playwright_candidates.json の candidates（無ければ []）
) -> tuple[RequirementTrace, ...]:
    """要件ごとに対応画面とテストケースを解決する。類似判定は
    ingest.matcher._name_similarity・しきい値 _SCREEN_NAME_THRESHOLD(0.6) を再利用。
    official_names（result.official_names）に一致した場合は method="official_name"・スコア加点なしの生値。"""

# src/generator/trace_reporter.py
TRACE_JSON_NAME = "requirement_trace.json"
TRACE_MD_NAME = "traceability_matrix.md"

def trace_to_dict(traces: tuple[RequirementTrace, ...], bundle: DocumentBundle) -> dict: ...
def save_trace_outputs(
    traces: tuple[RequirementTrace, ...], bundle: DocumentBundle, output_dir: Path
) -> None:
    """traces が空なら何も書かない（オプトイン）。md はサマリ（要件数・covered 率・
    未実装疑い数）→ マトリクス表（要件ID/要件名/対応画面/テスト/状態/文書出所）→
    未実装疑い一覧（免責注記付き）の順で fusion_reporter._render_markdown の体裁に合わせる。"""
```

### 5-2. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| 要件に対応画面なし | status="unimplemented_suspect" で出力（隠さない） | md の専用節＋「文書の鮮度に依存」注記 |
| playwright_candidates.json 不在/破損 | candidate_ids=() で継続（JSON エラーは捕捉） | 警告ログ「テスト候補ファイルなし（条件件数のみで追跡）」 |
| req_id 重複 | 後勝ちにせず両方出力し警告 | md の該当行に「ID重複」注記 |
| LLM 抽出要件の quote 不在 | SPEC-1-1 の幻覚フィルタで破棄 | 警告ログ（SPEC-1-1 と共通） |

### 5-3. 既存コードとの接続点

- `ingest/matcher.py::_name_similarity`・`_SCREEN_NAME_THRESHOLD` — 要件→画面の類似判定（独自しきい値を発明しない）
- `ingest/loader.py::_from_tables` — 要件表の収集は同メソッド内で `structure_requirement_table` を併走させる
- `main.py::_run_doc_fusion`（644 行付近） — trace 出力の呼び出し追加。candidates は `output_dir / "playwright_candidates.json"` から読む（`web/routes/traceability.py::_load_json_file` と同じ寛容な読み方）
- `web/routes/traceability.py::api_traceability_matrix` — 既存応答 dict に `document_requirements`（`trace_to_dict` の中身）を**ファイル存在時のみ**追加。`web/services/traceability.py::build_matrix` は変更しない
- `generator/fusion_reporter.py::_render_markdown` — md の表体裁・免責注記文の前例

## 6. テスト仕様

### 6-1. 単体テスト（tests/test_req_tracer.py・tests/test_doc_fusion.py 追記）

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_requirement_table_extracted | 要件ID・要件名列の md 表 | DocumentedRequirement 2 件・evidence の location=行番号 | AC-1 |
| test_llm_requirement_filtered | quote 不在の要件を含むフェイク応答 | 実在 quote の要件のみ・confidence ≤0.9 | AC-2 |
| test_requirement_mapped_to_screen | 「商品検索ができること」×タイトル「商品検索」ページ | trace.page_id 一致・score ≥0.6 | AC-3 |
| test_test_ids_linked | candidates に該当 URL の step | candidate_ids に id・status="covered" | AC-4 |
| test_unmatched_requirement_suspect | どの画面にも似ない要件 | status="unimplemented_suspect"・md に免責注記 | AC-5 |
| test_no_requirements_no_output | requirements=() の bundle | requirement_trace.json が生成されない | AC-6 |
| test_api_additive_key | trace ファイルあり/なしの 2 ケース | あり: document_requirements キー / なし: 現行応答と一致 | AC-7 |
| test_field_table_not_misread_as_requirements | 項目名＋必須列の表 | requirements 0 件（既存 fields 解釈のまま） | 5-1 |

### 6-2. 結合テスト

- md 要件表＋デモページ相当の AnalyzedPage 群 → `load_reference_documents` → `fuse` → `trace_requirements` → `save_trace_outputs` の通し（tmp_path）。md の表に covered / unimplemented_suspect の両方が現れること
- Flask test client で `/traceability/matrix?domain=...`（`tests/` の既存 route テストの流儀）

### 6-3. 回帰確認

- 既存 `tests/test_doc_fusion.py` 19 件・traceability 系既存テストが無変更で PASS
- 参考文書なし実行で出力ディレクトリのファイル集合が現行と一致（AC-6）

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜7 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] feature_contracts.yml 更新（req_tracer/trace_reporter・failure_modes 追記）
- [ ] 実行パス確認: CLI で要件表付き参考文書を指定してクロールし、traceability_matrix.md の未実装疑い節と `/traceability/matrix` の追加キーを目視確認

## 8. このタスク固有の罠

- **既存 `web/services/traceability.py` と名前空間が衝突する**。`RequirementLink`（web 側）と `RequirementTrace`（src 側）は別物として共存させる。web 側 dataclass を src から import したり、その逆をしてはならない（web→src の一方向のみ可 — CONVENTIONS §1-1）
- `looks_like_header` に要件シノニムを追加すると、**Markdown の任意の表がテーブルとして拾われやすくなり Phase 1 の抽出結果が変わり得る**。`looks_like_header` への追加は REQUIREMENT_ID_KEYS + REQUIREMENT_NAME_KEYS の同時一致（2 列以上）で効く設計を保ち、既存テストの抽出件数が変わらないことを回帰で確認する
- 「未実装疑い」は**断定表現にしない**。文書が古い場合は「実装済みだが文書が別名」も普通にあるため、md では必ず score 上位の近似候補（しきい値未満でも上位 1 件）を「近い画面」として併記し、判断材料を残す
- playwright_candidates.json は AutoRun 実行後にしか存在しない。**無いことを異常にしない**（candidate_ids 空で covered→screen_only に落とすだけ）
- `/traceability/matrix` の応答に無条件でキーを足すと、既存 UI（static/js/traceability.js）の描画は壊れないが**スナップショット的に応答を検証している既存テストが落ちる**可能性がある。追加は必ずファイル存在時のみ（オプトイン原則は API 応答にも適用する）
