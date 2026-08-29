# テスト設計仕様書 T05 参考資料アップロード・doc_fusion

## 1. 対象と前提

- SUT: `http://127.0.0.1:8765`（02-test-environment.md の通り）。モックは割当 port **9105**（出力先 `output/127.0.0.1:9105/`）。
- 対象機能: `POST /api/reference-docs`（web/routes/crawl.py:268 upload_reference_docs）、`GET /api/doc-fusion`（同:311）、`POST /run` の `reference_docs`（web/validation.py:60 `_safe_reference_doc_paths`）、doc_fusion パイプライン（src/main.py:1155 `_run_doc_fusion` → loader/matcher/fusion_reporter/req_tracer/refresh_reporter）、UI（wizard.js reference-doc-input / doc-fusion.js）。
- コードで確定した設計値:
  - `SUPPORTED_SUFFIXES`（src/ingest/loader.py:34）= `.xlsx .xlsm .docx .pptx .pdf .md .txt .feature .yaml .yml .json`
  - `_LEGACY_SUFFIXES`（loader.py:47）= `.xls .doc .ppt`
  - `_MAX_REFERENCE_DOC_BYTES`（crawl.py:27）= 20MB = 20,971,520 バイト。判定は `len(data) > MAX`（=ちょうど 20MB は許可）
  - ファイル名は `Path(filename).name` でディレクトリ部除去、拡張子 allowlist のみで検証（crawl.py:284-286）。secure_filename 不使用（非ASCII保持のため・コメント明記）
  - ドメイン検証 `_valid_domain`（web/validation.py:30）: `..` 拒否 + `DOMAIN_RE = ^[A-Za-z0-9._:\[\]-]{1,253}$`（web/config.py:52）
  - `_safe_reference_doc_paths`: resolve 後 `output/{domain}/reference_docs/` 配下の実在ファイルのみ通す。不正は黙って除外
  - LLM: doc_fusion の LLM 抽出は CLI `--doc-llm` 指定時のみ（src/main.py:706）。**web の /run コマンド組立（crawl.py generate()）は `--doc-llm` を渡さない**ため、UI 経由の doc_fusion は LLM を呼ばない（コード根拠）。鍵は `OPENAI_API_KEY` 環境変数のみ参照（main.py:1182）
- 前提状態: `output/` に既存ディレクトリ残存（削除禁止）。`output/127.0.0.1:9105/` は本トラックが専有。

## 2. テスト条件一覧

| 条件ID | テスト条件 | 契約 failure_mode | 25010 特性 | ツアー/手法 | リスク |
|---|---|---|---|---|---|
| T05-D01 | 対応形式（11 種）のアップロード正常系と saved 応答 | (happy_path) | 機能適合性 | 契約ベース/EP | High |
| T05-D02 | 旧バイナリ形式 .doc/.xls/.ppt の拒否とエラー文言 | legacy_binary_format | 機能適合性 | 契約ベース | Med |
| T05-D03 | 非対応拡張子（.exe/.html/なし）の拒否 | unsupported_format | セキュリティ | ネガティブ | High |
| T05-D04 | サイズ境界（0B / 20MB / 20MB+1B） | upload_rejected | 信頼性 | 境界値分析 | High |
| T05-D05 | ファイル未指定・不正 domain（空・../・任意ドメイン） | upload_rejected | セキュリティ | ネガティブ | High |
| T05-D06 | ファイル名によるパストラバーサル（../ ..\\ 絶対パス NUL 超長 NFC/NFD 二重） | path_traversal_attempt | セキュリティ | 攻撃者ツアー | Critical |
| T05-D07 | 拡張子偽装（.docx 中身テキスト）のアップロードと実行時挙動 | candidates_file_missing_or_corrupt | 信頼性 | ネガティブ | High |
| T05-D08 | /run reference_docs の safe path 判定（正・../・他ドメイン・不存在・絶対パス） | path_traversal_attempt / missing_file | セキュリティ | 契約ベース | Critical |
| T05-D09 | 参考資料付き実行での成果物生成（doc_fusion.json/md, report.json official_name・document_conditions, requirement_trace.json, traceability_matrix.md） | (happy_path/evidence) | 機能適合性 | 契約ベース | High |
| T05-D10 | 無関係資料での挙動（対応 0 件・gap 報告） | no_match | 機能適合性 | ネガティブ | Med |
| T05-D11 | 実在しない画面/項目のルールの扱い | rule_unmatched | 機能適合性 | 契約ベース | Med |
| T05-D12 | 解析不能な値（最大長=「多め」）の扱い | rule_value_unparsable | 信頼性 | ネガティブ | Med |
| T05-D13 | 対応付かない要件 REQ-999 の扱い | requirement_unmatched | 機能適合性 | 契約ベース | Med |
| T05-D14 | 同一要件 ID 二重記載の検出 | duplicate_requirement_id | 機能適合性 | 契約ベース | Med |
| T05-D15 | doc_fusion.json 全引用文の原文照合 | hallucinated_quote | 機能適合性 | evidence 監査 | High |
| T05-D16 | LLM 呼び出し有無・鍵未設定時挙動・外部送信の有無（国防要件） | llm_schema_reject | セキュリティ | コードトレース+実測 | Critical |
| T05-D17 | --refresh-doc 単独指定（--reference-doc なし） | refresh_flag_without_reference_doc | 信頼性 | 契約ベース | Low |
| T05-D18 | refresh 正常系（refreshed_spec.md / refresh_log.json） | (happy_path) | 機能適合性 | 契約ベース | Med |
| T05-D19 | 画面対応 0 件時の refresh スキップ | refresh_no_screens_skip | 信頼性 | ネガティブ | Low |
| T05-D20 | refresh の selector 逆引き失敗時の縮退 | refresh_selector_lookup_failed | 信頼性 | コードトレース | Low |
| T05-D21 | /api/doc-fusion の未実行ドメイン・不正ドメイン・破損 JSON 応答 | candidates_file_missing_or_corrupt | 信頼性 | ネガティブ | Med |
| T05-D22 | UI: 複数選択・一覧表示・削除・拒否理由の表示 | upload_rejected | 使用性 | UI ツアー | Med |
| T05-D23 | アップロード途中失敗時の部分保存（アトミック性） | upload_rejected | 信頼性 | ネガティブ | Med |
| T05-D24 | missing_file: 保存後にファイルを退避した状態での /run | missing_file | 信頼性 | ネガティブ | Med |

## 3. 網羅性の根拠

- 外部基準: **ISO/IEC 25010**（機能適合性・セキュリティ・信頼性・使用性に条件を割付）、**ISTQB CTFL** テスト技法（同値分割 EP・境界値分析 BVA・ネガティブテスト）、**OWASP ASVS 4.0 §12（File and Resources）**: 12.1 サイズ上限（D04）、12.2 型検証（D02/D03/D07）、12.3 パストラバーサル・ファイル名検証（D05/D06/D08）。
- 契約 failure_modes 16 件との対応（全件トレース）: unsupported_format→D03 / missing_file→D08,D24 / legacy_binary_format→D02 / no_match→D10 / llm_schema_reject→D16 / hallucinated_quote→D15 / rule_unmatched→D11 / rule_value_unparsable→D12 / upload_rejected→D04,D05,D22,D23 / path_traversal_attempt→D06,D08 / requirement_unmatched→D13 / duplicate_requirement_id→D14 / candidates_file_missing_or_corrupt→D07,D21 / refresh_selector_lookup_failed→D20 / refresh_no_screens_skip→D19 / refresh_flag_without_reference_doc→D17。

## 4. 意図的に除外した条件と理由

- 破損 JSON を `output/127.0.0.1:9105/doc_fusion.json` へ直接書き込む試験（D21 の 500 経路）: 制約 7（書き込みは自トラック配下のみ）に抵触するため実書き込みは行わず、コードトレース（crawl.py:318-321 が OSError/JSONDecodeError を 500 で返す）のみで評価。
- 20MB 超の multipart を UI（Playwright）から送る試験: API 直と同一経路（fetch /api/reference-docs）であり重複。API 側で実施。
- テナント有効時の `_out()` スコープ切替: 8765 は AUTH_MODE=off 起動でありテナント文脈が発生しない（02 環境定義）。T08（マルチテナント系トラック）の管轄。
- Windows 上での `..\` パス区切り解釈: SUT は darwin 上で動作（02 環境定義）。POSIX では `\` は区切りでないことを前提に観測結果を記録する。
