# SPEC-1-4 文書の再生 — 古い仕様書の実測改訂版生成（Doc Fusion Phase 3）

| 項目 | 値 |
|---|---|
| WBS | 1-4 |
| 優先度 / 見積 | P2 / 1sp |
| 依存 | 1-3（要件・突合基盤が出揃った後。突合データ自体は Phase 1 の `FusionResult` で足りる） |
| 背景 | docs/11 §6-2 機能⑤（「復元」より心理的受容が高い「再生」） |

## 1. 目的と背景

現行の Doc Fusion はギャップを**指摘する**（doc_fusion.md）が、顧客が本当に欲しいのは指摘リストではなく「**直った文書**」である。本タスクは、参考文書の構造（画面・項目・文書上の記載順）を骨格として維持したまま、実測で確認できた値に更新した**新版仕様書**を生成する。全ての変更箇所に「実測により更新（旧: 全角 20 桁 → 実測: 40 桁）」形式の注釈を付け、変更ログを機械可読 JSON でも残す。

**現状の実装状態（実装前に必ず確認すること）:**

- 済: `ingest/matcher.py::fuse` — `FusionResult`（screen_matches・doc_only_screens・crawl_only_page_ids・field_gaps・official_names）。mismatch の detail 文字列に旧値・新値が既に含まれる（`_mismatches`）
- 済: `generator/fusion_reporter.py` — doc_fusion.md/json の出力体裁（サマリ→表→注記）
- 済: `generator/markdown_generator.py::generate_screens_markdown` — 実測のみからの画面一覧 md（骨格が「実測順」であり本タスクの「文書順」とは別物）
- 未: 文書順を骨格とした再構成・変更注釈モデル・refreshed_spec.md / refresh_log.json

**重要な設計判断（evidence-only 原則）**: 本タスクは **LLM を使わない決定的マージ**である。文書の自由文を LLM でリライトすると根拠のない文が混入するため、更新は「突合で対応づいた属性の置換」と「実測 evidence 付きの追記」に限定する。

## 2. 受け入れ条件（全て自動テストで検証すること）

- **AC-1**: mismatch のある項目は新版で**実測値が採用**され、行末注釈に「実測により更新（旧: {文書値} → 実測: {実測値}）」が付く（Given: 文書 max_length=20・実測 maxlength=40 の対応項目 / When: 新版生成 / Then: 新版の桁数欄は 40・注釈に旧値 20）
- **AC-2**: doc_only（実測で見つからない）画面・項目は**削除せず**「実測で確認できず（未確認 — 廃止/権限/未探索の可能性）」注記付きで残る（無いことにしない）
- **AC-3**: crawl_only（文書に無い）画面は「文書未記載の新規画面」章として末尾に追記され、各画面に実測 evidence（URL・タイトル）と検出フィールド一覧が付く
- **AC-4**: 全変更（updated / doc_only / new / unchanged 件数）が `refresh_log.json` に旧値・新値・文書 evidence・実測セレクタ付きで記録される
- **AC-5**: 参考文書なしの実行では refreshed_spec.md / refresh_log.json が生成されない（オプトイン — 既存出力集合が不変）
- **AC-6**: 文書と実測が一致している記載は**一字も書き換えず**転記される（unchanged 項目の name・型・備考が入力とバイト一致）
- **AC-7**: 文書由来の正式名称（official_name）が新版の画面見出しに使われ、実測タイトルは併記になる

## 3. スコープ外

- 文書の自由文（説明文・業務背景の段落）の書き換え（構造化されなかったテキストは新版に含めない。含める場合の LLM リライトは将来タスク）
- 元ファイル形式（xlsx/docx）での出力（Markdown＋JSON のみ。Excel 化は generator/csv_reporter・spec.xlsx の既存経路の将来拡張）
- 業務ルール（`DocumentedRule`）の真偽判定（実測で検証できないため、新版には「文書記載のまま・実測未検証」注記で転記する）
- 画面遷移図の再生（実測遷移は report.html に既にある）

## 4. 基本設計

### 4-1. 変更ファイル一覧

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 新規 | `src/generator/refresh_reporter.py` | 変更注釈モデル・新版 md / 変更ログ json の生成 |
| 変更 | `src/main.py` | `_run_doc_fusion` から `save_refresh_outputs` を呼ぶ（`--refresh-doc` フラグ・既定 OFF） |
| 変更 | `tests/` | 新規 `tests/test_refresh_reporter.py`（§6-1） |
| 変更 | `quality/feature_contracts.yml` | doc_fusion 契約に refresh_reporter・outputs（refreshed_spec.md）追記 |

※ `ingest/` は変更しない。必要な突合情報は `FusionResult`・`DocumentBundle`・`list[AnalyzedPage]` に全て揃っている。

### 4-2. データモデル

```python
# src/generator/refresh_reporter.py
REFRESH_MD_NAME = "refreshed_spec.md"
REFRESH_LOG_NAME = "refresh_log.json"

@dataclass(frozen=True)
class RefreshEntry:
    """新版生成時の 1 変更（変更ログの行）。"""

    kind: str                 # "updated" / "doc_only" / "new" / "unchanged"
    screen_name: str          # 文書上の画面名（new は実測タイトル）
    subject: str              # 対象（項目名・"画面" 等）
    attribute: str = ""       # 変わった属性（"必須区分" / "桁数" / ""）
    old_value: str = ""       # 文書記載値（new は ""）
    new_value: str = ""       # 実測値（doc_only は ""）
    doc_evidence: DocumentEvidence | None = None
    crawl_selector: str = ""  # 実測根拠（SourceEvidence.selector）
```

### 4-3. 処理フロー

```text
save_refresh_outputs(result: FusionResult, bundle: DocumentBundle,
                     pages: list[AnalyzedPage], output_dir: Path)
  ├─ 画面ループ: bundle.screens の文書順（骨格を維持）
  │    ├─ matched   → 見出し「{screen.name}（実測: {page_title} / {url}）」
  │    │              項目表: doc_fields を文書順に、mismatch は実測値で置換＋注釈
  │    │              crawl_only 項目は表末尾に「文書未記載」注釈で追記
  │    └─ doc_only  → 見出し＋「実測で確認できず」注記（項目は文書記載のまま転記）
  ├─ 新規章: result.crawl_only_page_ids の画面（実測 evidence 付き）
  ├─ 変更ログ集計 → refresh_log.json
  └─ 冒頭サマリ: 生成日時・元文書名・updated/doc_only/new/unchanged 件数
```

## 5. 詳細設計

### 5-1. 関数シグネチャ

```python
# src/generator/refresh_reporter.py
def build_refresh_entries(
    result: FusionResult,
    bundle: DocumentBundle,
    pages: list[AnalyzedPage],
) -> tuple[RefreshEntry, ...]:
    """FusionResult.field_gaps を変更エントリへ変換する。
    - kind="mismatch" の FieldGap → RefreshEntry(kind="updated")。旧値・新値は
      doc_field（max_length/required）と対応 FieldData（maxlength/required）から取り直す
      （detail 文字列のパースはしない — 文字列依存は壊れやすい）。
    - kind="doc_only" → RefreshEntry(kind="doc_only")
    - kind="crawl_only" → RefreshEntry(kind="new")
    - ギャップに現れない対応済み項目 → RefreshEntry(kind="unchanged")"""

def render_refreshed_markdown(
    entries: tuple[RefreshEntry, ...],
    result: FusionResult,
    bundle: DocumentBundle,
    pages: list[AnalyzedPage],
) -> str:
    """文書順の骨格で新版 md を組み立てる。注釈書式は固定:
    「※実測により更新（旧: {old} → 実測: {new}）」/「※実測で確認できず」/「※文書未記載（実測で検出）」"""

def save_refresh_outputs(
    result: FusionResult, bundle: DocumentBundle,
    pages: list[AnalyzedPage], output_dir: Path,
) -> None:
    """bundle.screens が空なら何も書かない。json は fusion_reporter と同じ
    ensure_ascii=False・indent=2。"""
```

mismatch から旧値・新値を取り直すため、`FieldGap` には `doc_field`（`DocumentedField`）が既に載っている。実測側は `page_id`＋`crawl_selector` から `pages` の `FieldData` を逆引きする（`ingest/matcher.py::_crawled_fields` と同じ走査）。

### 5-2. エラー処理表

| 事象 | 振る舞い | ユーザー可視 |
|---|---|---|
| crawl_selector から FieldData を逆引きできない | 属性置換せず注釈「実測値の特定に失敗（doc_fusion.md 参照）」で文書値のまま残す | 注釈＋警告ログ |
| 文書に画面が 1 件も無い（fields のみ等） | 新版を生成しない（骨格が作れない） | ログ「画面情報が無いため文書再生をスキップ」 |
| 同名画面が文書内に重複 | 文書順で全て出力し、見出しに (2) を付番 | md 上の付番 |
| 出力先に旧 refreshed_spec.md が存在 | 上書き（スナップショット管理はしない — doc_fusion.md と同挙動） | なし |

### 5-3. 既存コードとの接続点

- `ingest/matcher.py::FusionResult`・`FieldGap.doc_field`・`ScreenMatch` — 入力データ（matcher は変更しない）
- `ingest/models.py::document_evidence_to_dict` — refresh_log.json の evidence 変換
- `generator/fusion_reporter.py::save_fusion_outputs` — 呼び出し位置の隣（`main.py::_run_doc_fusion`）と md 体裁・JSON 書式の前例
- `analyzer/html_analyzer.py::AnalyzedPage`・`crawler/page_crawler.py::FieldData` — 実測側の属性参照（required・maxlength・field_type・evidence.selector）
- `main.py::parse_args` — `--refresh-doc`（`--reference-doc` と併用必須。単独指定は警告して無視）

## 6. テスト仕様

### 6-1. 単体テスト（新規 tests/test_refresh_reporter.py）

| テスト名 | 入力 | 期待値 | AC |
|---|---|---|---|
| test_mismatch_updated_with_annotation | max_length 20 vs 40 の突合結果 | 新版の値 40・注釈に「旧: 20」 | AC-1 |
| test_doc_only_kept_as_unconfirmed | doc_only 画面 1 件 | 削除されず「実測で確認できず」注記 | AC-2 |
| test_crawl_only_appended_as_new | crawl_only page 1 件 | 「文書未記載の新規画面」章・URL 付き | AC-3 |
| test_refresh_log_records_all | updated/doc_only/new 混在 | refresh_log.json に kind 別件数・両 evidence | AC-4 |
| test_no_reference_no_output | bundle.screens=() | 出力ファイルなし | AC-5 |
| test_unchanged_verbatim | 完全一致の項目 | name・型・備考がバイト一致で転記 | AC-6 |
| test_official_name_as_heading | official_names に対応あり | 見出し=文書名・実測タイトル併記 | AC-7 |
| test_selector_lookup_failure_safe | 実在しない crawl_selector の gap | 文書値のまま・「特定に失敗」注釈・例外なし | 5-2 |

入力は `tests/test_doc_fusion.py` の既存フィクスチャ（DocumentBundle・AnalyzedPage の組み立てヘルパ）を再利用する。

### 6-2. 結合テスト

- 参考文書（項目定義 md）→ `fuse` → `save_refresh_outputs` の通し（tmp_path）。生成 md を再度 `ingest/text_reader.py::read_markdown` で読み戻し、**表として構造化可能**であること（新版が次回の参考文書として再投入できる = 再生サイクルの成立）

### 6-3. 回帰確認

- 既存ユニット全件・`tests/test_doc_fusion.py` 19 件が無変更で PASS
- `--refresh-doc` 未指定時の出力ファイル集合が現行と一致（AC-5）

## 7. 完了チェックリスト（DoD）

- [ ] AC-1〜7 のテストが全て存在し PASS
- [ ] CONVENTIONS §3 の全ゲート通過（black/ruff/mypy/bandit/pytest/quality_harness）
- [ ] feature_contracts.yml 更新（refresh_reporter・outputs 追記）
- [ ] 実行パス確認: CLI で `--reference-doc <古い項目定義> --refresh-doc` を実行し、refreshed_spec.md の注釈 3 種（更新/未確認/新規）を目視確認

## 8. このタスク固有の罠

- **FieldGap.detail のパースで旧値・新値を得ようとしない**。detail は人間向け日本語文字列で、`_mismatches` の文言変更（他タスク由来）で静かに壊れる。必ず `doc_field` の属性と実測 `FieldData` から構造的に取り直す
- 「実測により更新」は**対応づいた（matched）項目にのみ**許される。doc_only 項目を「実測に無い＝削除」と解釈してはならない — 未探索・権限・条件表示の可能性があり、削除は evidence-only 原則違反（AC-2 はこの防波堤）
- `bundle.fields` の文書順は `load_reference_documents` が複数ファイルを連結した順。**画面ごとの項目帰属は `matcher._fields_for_screen` と同じ規則**（screen_name/screen_id 一致、単一画面文書のみ無帰属を許容）を使い、独自の帰属ロジックを発明しない
- 新版 md の表ヘッダは `ingest/tables.py` のシノニム（項目名・型・必須・桁数・備考）に**意図的に一致させる**こと。ここを独自ヘッダにすると §6-2 の「読み戻し」が成立せず、再生サイクルが切れる
- generator 層から `ingest.matcher` の**関数**を呼ぶのは依存方向として可（解析層→出力層の逆 import が禁止なのであって、出力層が下位データを読むのは正常）。ただし `_crawled_fields` は private のため、同等の 2 行走査を refresh_reporter 内に書く方が結合が浅い
