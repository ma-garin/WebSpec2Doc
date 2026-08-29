# テスト設計仕様書 T05 参考資料アップロード・doc_fusion

## 1. 対象と前提

| 項目 | 値 |
|---|---|
| 被試験 API | `POST /api/reference-docs`（form: `domain` + `files`）, `GET /api/doc-fusion?domain=` |
| 実装 | `web/routes/crawl.py` `upload_reference_docs` / `api_doc_fusion`、`web/validation.py` `_valid_domain`/`_safe_reference_doc_paths`、`src/ingest/loader.py` `SUPPORTED_SUFFIXES`/`_LEGACY_SUFFIXES` |
| 定数（コード実測） | `_MAX_REFERENCE_DOC_BYTES = 20*1024*1024 = 20971520`（`len(data) > 上限` で 400）、`SUPPORTED_SUFFIXES = .xlsx .xlsm .docx .pptx .pdf .md .txt .feature .yaml .yml .json`、`_LEGACY_SUFFIXES = .xls .doc .ppt`、`DOMAIN_RE = ^[A-Za-z0-9._:\[\]-]{1,253}$`（かつ `".." not in domain` かつ非空） |
| モックサイト | `http://127.0.0.1:9105`（事前に auto クロールし `output/127.0.0.1:9105/` を生成） |
| 保存先 | `output/{domain}/reference_docs/`（アップロード時は拡張子 allowlist とサイズのみ検査。中身のパースはしない） |
| 前提条件 | 本体8765 稼働・認証オフ。`Path(filename).name` でディレクトリ部を剥がし、拡張子 allowlist で安全性担保する設計（`secure_filename` は非ASCIIを落とすため不使用） |
| LLM | 実 LLM 未接続。fusion 実体（no_match / hallucinated_quote / llm_schema_reject 等）は設計＋コード確認ベース、実行は「未実行」 |

## 2. テスト条件一覧

| 条件ID | テスト条件 | 契約 failure_mode | 25010 特性 | ツアー/手法 | リスク |
|---|---|---|---|---|---|
| T05-D01 | SUPPORTED_SUFFIXES 各拡張子の小ファイルが 200 ok で `reference_docs/` に保存される | （正常系） | 機能適合性 | 契約ベース・等価分割 | High |
| T05-D02 | 複数ファイル同時アップロードが全件 saved に載る | （正常系） | 機能適合性 | 等価分割 | Medium |
| T05-D03 | 旧バイナリ `.doc`/`.xls`/`.ppt` が 400 と「旧バイナリ形式」で拒否 | legacy_binary_format / upload_rejected | セキュリティ・機能適合性 | 契約ベース・境界（allowlist端） | High |
| T05-D04 | 非対応 `.exe`/`.zip`/`.svg` が 400 で拒否 | unsupported_format / upload_rejected | セキュリティ | 契約ベース・等価分割 | High |
| T05-D05 | サイズ上限 `20971520` ちょうどは 200、`+1` は 400 | upload_rejected | 機能適合性 | 境界値 | Medium |
| T05-D06 | パストラバーサル（`../../`, `..%2f`, 絶対パス, `..\`）で `reference_docs/` 外へ書かれない | path_traversal_attempt | セキュリティ（機密性・完全性） | OWASP ASVS V12・Saboteur | Critical |
| T05-D07 | 不正 `domain`（空・`../`混入・スラッシュ）が「不正なドメインです」400 | upload_rejected / path_traversal_attempt | セキュリティ | 契約ベース・攻撃入力 | High |
| T05-D08 | `files` 未指定が「ファイルが指定されていません」400 | missing_file | 機能適合性 | 契約ベース | Medium |
| T05-D09 | 候補/fusion 出力（`doc_fusion.json`）不在で `/api/doc-fusion` が 404 を返す | candidates_file_missing_or_corrupt | 信頼性・機能適合性 | 契約ベース・異常系 | Medium |
| T05-D10 | `/api/doc-fusion` の不正 domain が 404（情報を返さない） | path_traversal_attempt | セキュリティ | 攻撃入力 | Medium |
| T05-D11 | 形式的に妥当だが未クロールの domain へのアップロード挙動（副作用: ディレクトリ生成の有無） | upload_rejected | セキュリティ（認可） | 探索的・Back Alley | Medium |
| T05-D12 | LLM 抽出系 failure_modes（no_match / hallucinated_quote / llm_schema_reject / rule_unmatched / rule_value_unparsable / requirement_unmatched / duplicate_requirement_id） | 同左 | 機能適合性 | コード確認（実行不可） | High |

## 3. 網羅性の根拠（外部基準と契約 failure_modes 対応）

照合した外部基準: **`quality/feature_contracts.yml`（feature `doc_fusion` failure_modes）** / **OWASP ASVS 4.0 V12（File and Resources）・Top 10 A01/A03** / **ISO/IEC 25010（機能適合性・セキュリティ・信頼性）** / **境界値分析・等価分割（ISTQB）**。

| 契約 failure_mode（doc_fusion） | 担当条件ID | 実行可否 |
|---|---|---|
| unsupported_format | T05-D04 | 実行 |
| missing_file | T05-D08 | 実行 |
| legacy_binary_format | T05-D03 | 実行 |
| upload_rejected | T05-D03/D04/D05/D07/D11 | 実行 |
| path_traversal_attempt | T05-D06/D07/D10 | 実行 |
| candidates_file_missing_or_corrupt | T05-D09 | 実行 |
| no_match | T05-D12 | 未実行（実LLM未接続） |
| llm_schema_reject | T05-D12 | 未実行（実LLM未接続） |
| hallucinated_quote | T05-D12 | 未実行（実LLM未接続） |
| rule_unmatched | T05-D12 | 未実行（実LLM未接続） |
| rule_value_unparsable | T05-D12 | 未実行（実LLM未接続） |
| requirement_unmatched | T05-D12 | 未実行（実LLM未接続） |
| duplicate_requirement_id | T05-D12 | 未実行（実LLM未接続） |

## 4. 意図的に除外した条件と理由

- **fusion 本体の突合精度（no_match / hallucinated_quote 等）の実挙動**: 実 LLM 未接続のため実行不能。コード（`src/ingest/matcher.py`, `filter_hallucinations`, `src/ingest/loader.py`）の存在確認とデータ経路の静的確認に留める。計画（`01-test-plan.md` §2.2「実 LLM 接続は範囲外」）に整合。
- **doc_fusion.json が破損している場合（corrupt）の 500 分岐**: `api_doc_fusion` の `except json.JSONDecodeError → 500` はコード確認済み。破損ファイルを自トラック外の永続領域に恒久生成するのを避け、実行は 404（不在）分岐のみとした。500 分岐は「コード確認済み・未実行」。
- **他トラック領域**: 8765 停止・他ポート・他 output への操作は禁止事項に従い実施しない。
