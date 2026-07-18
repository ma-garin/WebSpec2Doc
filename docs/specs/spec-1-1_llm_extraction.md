# SPEC-1-1 PDF/Word 自由文からの LLM 意味抽出（Doc Fusion Phase 2）

| 項目 | 値 |
|---|---|
| WBS | 1-1 |
| 優先度 / 見積 | P1 / 1sp |
| 依存 | なし（Doc Fusion Phase 1 = PR #32 の上に載る） |
| 背景 | docs/11 §6-2 機能④の前段・§6-6 Phase 2 |

## 1. 目的と背景

Doc Fusion Phase 1（実装済み）は表構造（Excel・Markdown 表・docx 表）から `DocumentedScreen` / `DocumentedField` を機械抽出できるが、PDF・pptx・txt・docx 本文の**自由文**からは画面名候補の正規表現抽出（`screens_from_lines`）しかできない。RFP や基本設計書の本文に書かれた「振込限度額は 1 日 100 万円まで」「税額 = 課税対象額 × 10%」のような**業務ルール**、および文中の画面・項目記述を LLM Structured Outputs で構造化し、突合（`fuse`）とテスト観点注入（SPEC-1-2）の入力にする。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `src/ingest/loader.py::load_reference_documents` — 拡張子振り分け・`DocumentBundle` 統合。PDF/pptx/txt は `screens_from_lines` による画面名候補のみ（`src/ingest/text_reader.py` docstring に「深い意味抽出は Phase 2 の LLM 抽出で扱う」と明記済み）
- 済: `src/llm/openai_client.py::request_structured_json` — Structured Outputs（strict）呼び出しと `LLMResponseError`
- 済: `src/llm/provider.py` — `LLMProvider` Protocol（`RulesProvider` / `OpenAIProvider`）。スキーマ検証失敗→棄却→フォールバックのパターンは `OpenAIProvider.generate_viewpoints` に前例あり
- 済: confidence 算定の前例 — `src/llm/viewpoint_generator.py::llm_viewpoint_confidence`（基礎 0.7 + 検証ボーナス 0.2 = 最大 0.9）
- 未: `DocumentedRule` モデル・LLM 抽出器・幻覚フィルタ・`DocumentBundle.rules`

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: PDF 自由文から画面・項目・業務ルールが抽出される（Given: 業務ルール文を含む PDF 由来の行リスト / When: LLM 抽出（フェイク応答注入）で `load_reference_documents` / Then: `DocumentBundle.rules` に `DocumentedRule` が入り、screens/fields にも LLM 由来分が追加される）
- **AC-2**: 全 LLM 抽出項目に `DocumentEvidence`（file・location・quote）が付く。**quote が原文行に見つからない出力は破棄**され、警告ログに破棄理由が残る（幻覚フィルタ）
- **AC-3**: LLM 由来の抽出は `source="llm"`・`confidence ≤ 0.9`（quote 完全一致で 0.9、正規化一致のみなら 0.7）。Phase 1 の表由来は `source="table"`・confidence 1.0 のまま
- **AC-4**: OPENAI_API_KEY なし（`RulesProvider`）では LLM 抽出をスキップし、**Phase 1 と完全に同一の DocumentBundle** で完走する
- **AC-5**: LLM 応答のスキーマ違反・通信例外（`LLMResponseError` 等）は捕捉され、Phase 1 結果のみで処理継続（例外を外に漏らさない）
- **AC-6**: LLM 未使用時、`doc_fusion.json` の既存スキーマにキーが増えない（`documented_rules` は rules 非空時のみ出力 — オプトイン）
- **AC-7**: 抽出ルールが `doc_fusion.json` の `documented_rules` に evidence・confidence 付きで出力される

## 3. スコープ外

- 抽出ルールのテスト観点・境界値への注入（SPEC-1-2）
- 要件（requirement）の抽出とトレーサビリティ（SPEC-1-3）
- 図・スキャン画像 PDF の OCR（テキスト抽出できない PDF は Phase 1 同様「行なし」として扱う）
- Web UI からの LLM 抽出の ON/OFF（SPEC-1-5。本タスクは CLI フラグと環境変数まで）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 変更 | `src/ingest/models.py` | `DocumentedRule` 追加・`DocumentBundle.rules`（既定 `()`）・`DocumentedScreen`/`DocumentedField` に `source`/`confidence`（既定値付き = 後方互換） |
| 新規 | `src/ingest/llm_extractor.py` | 抽出スキーマ・プロンプト・幻覚フィルタ・位置逆引き |
| 変更 | `src/ingest/loader.py` | 自由文形式（pdf/pptx/txt/docx 本文）の行を LLM 抽出へ渡す・結果マージ（`_dedup_screens` 流用） |
| 変更 | `src/llm/provider.py` | Protocol に `extract_document_semantics` 追加。`RulesProvider`= 空応答、`OpenAIProvider`= Structured Outputs 呼び出し |
| 変更 | `src/generator/fusion_reporter.py` | `documented_rules` の出力（**rules 非空時のみキー追加**） |
| 変更 | `src/main.py` | `--doc-llm` フラグ追加（既定 OFF）。`_run_doc_fusion` から loader へ伝播 |
| 変更 | `tests/test_doc_fusion.py` ほか | 単体テスト追加（§6-1） |
| 変更 | `quality/feature_contracts.yml` | doc_fusion 契約に llm_extractor・failure_modes（`llm_schema_reject` / `hallucinated_quote`）追記 |

### 4-2. データモデル

```python
# src/ingest/models.py に追加
@dataclass(frozen=True)
class DocumentedRule:
    """文書に記載された業務ルール（計算式・限度値・権限条件など）。"""

    rule_id: str                 # 例: "RULE-001"（抽出順に採番）
    kind: str                    # "calculation" / "limit" / "permission" / "other"
    description: str             # ルールの平文説明（日本語）
    screen_name: str = ""        # 文書内で確認できた画面参照（確認不能なら ""）
    field_name: str = ""         # 同・項目参照
    expression: str = ""         # 計算式・限度値の原文表現（例: "100万円/日"）
    source: str = "llm"          # "llm"（Phase 2 では LLM 抽出のみ）
    confidence: float = 0.7      # LLM 由来は必ず 0.9 以下
    evidence: DocumentEvidence | None = None  # 必須運用（None のルールは出力前に破棄）

# DocumentBundle に追加（既定値付き = 後方互換）
    rules: tuple[DocumentedRule, ...] = ()
```

### 4-3. 処理フロー

```text
load_reference_documents(paths, use_llm=False, api_key="")
  ├─ _load_one(path)                     # 既存: 表・見出しのルールベース抽出（変更なし）
  ├─ [use_llm かつ自由文形式] _free_text_lines(path)   # 新: (location, text) 行リスト
  │    └─ provider.extract_document_semantics(lines, file)  # LLMProvider 経由
  │         └─ filter_hallucinations(raw, lines, file)      # quote 実在検証・位置逆引き
  ├─ LLM 由来 screens を _dedup_screens で既存とマージ（表由来を優先）
  └─ DocumentBundle(screens, fields, rules, source_files)
```

## 5. 詳細設計

### 5-1. 抽出スキーマ（Structured Outputs strict）

```python
# src/ingest/llm_extractor.py
EXTRACTION_SCHEMA_NAME = "document_semantics"
EXTRACTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "screens": {"type": "array", "items": {  # name, url_hint, quote
            "type": "object",
            "properties": {"name": {"type": "string"}, "url_hint": {"type": "string"},
                           "quote": {"type": "string"}},
            "required": ["name", "url_hint", "quote"], "additionalProperties": False}},
        "fields": {"type": "array", "items": {   # name, screen_name, required 等 + quote
            "type": "object",
            "properties": {"name": {"type": "string"}, "screen_name": {"type": "string"},
                           "field_type": {"type": "string"},
                           "required": {"type": ["boolean", "null"]},
                           "max_length": {"type": ["integer", "null"]},
                           "quote": {"type": "string"}},
            "required": ["name", "screen_name", "field_type", "required", "max_length", "quote"],
            "additionalProperties": False}},
        "rules": {"type": "array", "items": {
            "type": "object",
            "properties": {"kind": {"type": "string", "enum": ["calculation", "limit", "permission", "other"]},
                           "description": {"type": "string"}, "screen_name": {"type": "string"},
                           "field_name": {"type": "string"}, "expression": {"type": "string"},
                           "quote": {"type": "string"}},
            "required": ["kind", "description", "screen_name", "field_name", "expression", "quote"],
            "additionalProperties": False}},
    },
    "required": ["screens", "fields", "rules"], "additionalProperties": False,
}
```

### 5-2. 関数シグネチャ

```python
# src/ingest/llm_extractor.py
def extract_semantics(
    lines: list[tuple[str, str]],   # (location, text) — read_pdf_lines 等の戻り値
    source_file: str,
    provider: "LLMProvider",
) -> tuple[list[DocumentedScreen], list[DocumentedField], list[DocumentedRule]]:
    """自由文行から LLM で画面・項目・ルールを抽出する。失敗・キーなしは空 3-tuple。"""

def filter_hallucinations(
    payload: dict[str, Any], lines: list[tuple[str, str]], source_file: str,
) -> tuple[list[DocumentedScreen], list[DocumentedField], list[DocumentedRule]]:
    """quote を原文行から逆引きし、見つからない項目を破棄する。
    location は LLM 出力を信用せず、quote が最初に見つかった行の location を採用する。
    照合は _normalize_quote（空白・全半角正規化）で行い、完全一致 conf=0.9 / 正規化一致 conf=0.7。"""

def _normalize_quote(text: str) -> str: ...

# src/llm/provider.py — Protocol へ追加（RulesProvider は空応答を返す = フォールバック）
def extract_document_semantics(
    self, lines: list[tuple[str, str]], source_file: str
) -> dict[str, Any]:
    """{"screens": [], "fields": [], "rules": []} 形式の生応答を返す。"""

# src/ingest/loader.py — 署名拡張（キーワード引数・既定値で後方互換）
def load_reference_documents(
    paths: list[Path], use_llm: bool = False, api_key: str = ""
) -> DocumentBundle: ...
```

プロンプトは `viewpoint_generator.build_viewpoint_prompt` に倣い日本語で構築し、「**文書に書かれていないことを推測で補完しない。各項目に原文の quote を必ず含める**」を明記する。モデルは `llm/screen_classifier.py::_LLM_MODEL`（gpt-4o-mini）を既定とする。

### 5-3. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| API キーなし（RulesProvider） | LLM 抽出をスキップ（空応答） | ログ「LLM 抽出は無効（Phase 1 抽出のみで継続）」 |
| `LLMResponseError`・通信例外 | 捕捉し空 3-tuple 返却・処理続行 | 警告ログ「LLM 抽出応答を棄却しました（理由: …）」 |
| quote が原文にない | 該当項目のみ破棄 | 警告ログ「幻覚の疑いで破棄: <name> / <quote 先頭 40 字>」 |
| screen_name が抽出画面・表由来画面のどちらにも不在 | 項目は残し screen_name="" に落とす | note に「画面参照を文書内で確認できず」 |
| PDF からテキスト行ゼロ | LLM を呼ばない | ログ「テキストが抽出できないため LLM 抽出をスキップ」 |

### 5-4. 既存コードとの接続点

- `ingest/loader.py::_load_one` — pdf/pptx/txt/docx 分岐の直後に LLM 抽出を追加（`text_reader.py::read_pdf_lines` / `read_plain_text_lines`・`office_reader.py::read_pptx_lines` の戻り値をそのまま渡す）
- `ingest/loader.py::_dedup_screens` — LLM 由来画面のマージに流用（表由来優先）
- `llm/provider.py::OpenAIProvider` — `request_structured_json`（`llm/openai_client.py`）＋棄却→フォールバックの既存パターンを踏襲
- `generator/fusion_reporter.py::fusion_to_dict` — `official_name` と同じオプトイン方式で `documented_rules` を追加（`models.document_evidence_to_dict` を流用）
- `main.py::_run_doc_fusion`（644 行付近）— `--doc-llm` と `os.environ.get("OPENAI_API_KEY", "")` を loader へ伝播

## 6. テスト仕様

### 6-1. 単体テスト（tests/test_doc_fusion.py または新規 tests/test_llm_extractor.py）

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_extract_rules_from_pdf_lines | フェイク provider（限度値ルール応答） | DocumentedRule(kind="limit", evidence.location=該当行) | AC-1 |
| test_hallucinated_quote_discarded | 原文に無い quote を含む応答 | 該当項目のみ破棄・警告ログに項目名 | AC-2 |
| test_llm_confidence_capped | 完全一致 quote / 正規化一致 quote | confidence 0.9 / 0.7（>0.9 が存在しない） | AC-3 |
| test_no_api_key_same_as_phase1 | use_llm=False と RulesProvider の両方 | Phase 1 の DocumentBundle と完全一致 | AC-4 |
| test_llm_error_falls_back | evaluate 中に LLMResponseError を投げるフェイク | 例外を出さず表由来のみの bundle | AC-5 |
| test_fusion_json_no_rules_key_when_empty | rules=() の bundle | doc_fusion.json に documented_rules キーなし | AC-6 |
| test_fusion_json_rules_with_evidence | rules 1 件の bundle | documented_rules に file/location/quote/confidence | AC-7 |
| test_unknown_screen_ref_blanked | 実在しない screen_name を持つルール応答 | screen_name=""・note に「確認できず」 | 5-3 |

フェイク provider は `tests/test_doc_fusion.py` 内に `_FakeSemanticsProvider` として定義し、`extract_document_semantics` の応答を注入可能にする（`_FakeRecorderPage` の流儀に倣う）。

### 6-2. 結合テスト

- 実 PDF（tmp_path に pypdf ではなくテキスト固定の .txt で代替可 — CI にフォント依存を持ち込まない）→ `load_reference_documents(use_llm=True)` → `fuse` → `save_fusion_outputs` の通し。LLM はフェイク注入
- CLI: `--reference-doc sample.txt --doc-llm`（キーなし環境）で exit 0・doc_fusion.md 生成を確認

### 6-3. 回帰確認

- 既存 `tests/test_doc_fusion.py` 19 件が無変更で PASS（`DocumentBundle` 生成箇所は rules 既定値で吸収）
- 既存ユニット全件 PASS・`doc_fusion.json` の Phase 1 スキーマ差分なし（AC-6）

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜7 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] feature_contracts.yml 更新（doc_fusion に `src/ingest/llm_extractor.py`・failure_modes 追記）
- [ ] 実行パス確認: CLI で `--reference-doc <自由文 txt> --doc-llm` を実行し、doc_fusion.json の documented_rules と警告ログ（キーなし時のスキップ）を目視確認。実 API での確認ができない場合は「未確認」と報告

## 8. このタスク固有の罠

- **Structured Outputs strict は Optional フィールドを許さない**。全プロパティを required に列挙し、欠けてよい値は `"type": ["boolean", "null"]` のように null 許容で表現する（`VIEWPOINT_JSON_SCHEMA` は全 required の前例）。required から外すと API が 400 を返す
- **LLM が返す location を信用しない**。位置は必ず quote の逆引きで自前計算する。逆引き前に正規化（空白圧縮・全半角統一）しないと、PDF 抽出特有の空白揺れで正当な quote まで破棄する（幻覚フィルタの過剰検出）
- `DocumentBundle` は frozen dataclass。既存テストが位置引数で生成している場合、`rules` は**必ず既定値付き末尾フィールド**として追加する（途中に挿むと全生成箇所が壊れる）
- `_load_one` は `(screens, fields)` の 2-tuple を返す契約。戻り値の型を変えると loader 内の全分岐に波及するため、rules は別の収集経路（`_free_text_lines` → `extract_semantics`）で集めて `load_reference_documents` 側でマージする
- LLM 呼び出しは `LLMProvider` Protocol 経由が掟（CONVENTIONS §1-1）。`llm_extractor.py` から `request_structured_json` を直叩きしない（`OpenAIProvider.extract_document_semantics` に置く）
