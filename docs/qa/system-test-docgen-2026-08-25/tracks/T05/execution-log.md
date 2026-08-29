# テスト実行ログ T05

実施日時: 2026-08-25 00:14–00:16 JST / 実施者: 第三者検証（T05 担当） / 環境: `02-test-environment.md`（本体8765・モック9105・認証オフ）

事前準備: `POST /run`（urls=http://127.0.0.1:9105/, depth=1, max_pages=3, crawl_mode=auto）で `output/127.0.0.1:9105/`（screens=3）を生成。

| ケースID | 結果 | 実測値・観測 | 証跡 | 備考 |
|---|---|---|---|---|
| T05-C001 | PASS | HTTP200 `{ok:true,saved:[ref.md]}`。`reference_docs/ref.md`(62B) 実在 | evidence/normal_and_format.log | |
| T05-C002 | PASS | HTTP200 saved 2件（ref.txt/ref.pdf） | evidence/normal_and_format.log | |
| T05-C003 | PASS | HTTP200 saved ref.docx | evidence/normal_and_format.log | 中身パースはupload時に行われない（拡張子検査のみ） |
| T05-C004 | PASS | HTTP200 saved ref.xlsx | evidence/normal_and_format.log | |
| T05-C005 | PASS | HTTP200 saved 3件（.feature/.json/.yaml） | evidence/normal_and_format.log | |
| T05-C010 | PASS | HTTP400 `旧バイナリ形式（.doc）は未対応…: legacy.doc`。保存なし | evidence/normal_and_format.log | legacy_binary_format |
| T05-C011 | PASS | HTTP400 `旧バイナリ形式（.xls）` | evidence/normal_and_format.log | |
| T05-C012 | PASS | HTTP400 `旧バイナリ形式（.ppt）` | evidence/normal_and_format.log | `.ppt` も `_LEGACY_SUFFIXES` に含む |
| T05-C020 | PASS | HTTP400 `未対応の文書形式です: bad.exe（対応形式: …）` | evidence/normal_and_format.log | unsupported_format。対応形式一覧をエラーに列挙 |
| T05-C021 | PASS | HTTP400 `未対応の文書形式です: bad.zip` | evidence/normal_and_format.log | |
| T05-C022 | PASS | HTTP400 `未対応の文書形式です: bad.svg` | evidence/normal_and_format.log | SVG(XSSベクタ) も拒否される |
| T05-C030 | PASS | HTTP200 saved exact20mb.md（20971520B）。`len>上限` 判定のため上限値ちょうどは許可 | evidence/size_boundary.log | 境界=`_MAX_REFERENCE_DOC_BYTES` |
| T05-C031 | PASS | HTTP400 `ファイルサイズが上限（20MB）を超えています: over20mb.md`（20971521B） | evidence/size_boundary.log | +1B で拒否。境界正しい |
| T05-C040 | PASS | HTTP200 だが保存名は `evil.md`。`reference_docs/` 外へ書かれず。realpath=`…/reference_docs/evil.md` | evidence/path_traversal.log, post_traversal_files.txt | ★主要防御 HOLD |
| T05-C041 | PASS(注) | HTTP200、保存名 `..%2f..%2fpasswd.md`（%2f 非デコード・リテラル）。realpath は reference_docs 内 | evidence/path_traversal.log | 外へ漏れない。ファイル名は非正規（T05-I02） |
| T05-C042 | PASS | HTTP200、保存名 `abs_evil.md`（絶対パスのディレクトリ部剥がれ）。外へ書かれず | evidence/path_traversal.log | |
| T05-C043 | PASS(注) | HTTP200、保存名 `..\..\win.md`（POSIX ではリテラル、区切りでない）。外へ書かれず | evidence/path_traversal.log | POSIX安全。Windows移植時は潜在traversal（T05-I02） |
| T05-C050 | PASS | HTTP400 `不正なドメインです` | evidence/domain_and_missing.log | |
| T05-C051 | PASS | HTTP400 `不正なドメインです`（`".." not in domain` で弾く） | evidence/domain_and_missing.log | |
| T05-C052 | PASS | HTTP400 `不正なドメインです`（DOMAIN_RE 不一致） | evidence/domain_and_missing.log | |
| T05-C053 | PASS(観測) | HTTP200。未クロールでも `output/192.0.2.55:1/reference_docs/ref.md` を新規生成 | evidence/domain_and_missing.log, ls出力 | 認可なしで任意host名ディレクトリ生成可（T05-I01） |
| T05-C060 | PASS | HTTP400 `ファイルが指定されていません` | evidence/domain_and_missing.log | missing_file |
| T05-C070 | PASS | HTTP404 `doc_fusion.json not found`。`doc_fusion.json` 不在を確認 | evidence/doc_fusion.log | candidates_file_missing_or_corrupt の不在分岐 |
| T05-C071 | PASS | HTTP404 `not found`（不正domainで情報を返さない） | evidence/doc_fusion.log | |
| T05-C080 | 未実行 | 実LLM未接続。`src/ingest/matcher.py`/`loader.load_reference_documents`/`filter_hallucinations` の存在をコード確認 | design.md §3/§4 | no_match/hallucinated_quote/llm_schema_reject/rule_unmatched/rule_value_unparsable/requirement_unmatched/duplicate_requirement_id は理由「実LLM未接続」で未実行 |

## 集計

PASS 23 / FAIL 0 / BLOCKED 0 / 未実行 1（T05-C080＝LLM抽出系 7 failure_modes、理由: 実LLM未接続。コード存在は確認済み）

補足: doc_fusion.json 破損時の 500 分岐（`api_doc_fusion` の `except json.JSONDecodeError`）はコード確認済み・未実行（永続領域に破損ファイルを作らないため）。
