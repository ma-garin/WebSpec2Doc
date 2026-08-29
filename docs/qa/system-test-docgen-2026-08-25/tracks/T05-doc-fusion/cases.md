# テストケース仕様書 T05
DOM=127.0.0.1:9105 / FX=evidence/fixtures / 実行スクリプトは scripts/ 配下。

| ケースID | 条件ID | 名称 | 前提条件 | 手順 | 期待結果 | 自動化 | スクリプト |
|---|---|---|---|---|---|---|---|
| T05-C001 | D01 | .md 正常アップロード | モック9105稼働 | POST /api/reference-docs domain=DOM files=ref_good.md | 200 ok=true, saved[].path が output/DOM/reference_docs/ 配下、ファイル実在 | auto | scripts/t05_upload_api.py |
| T05-C002 | D01 | .txt 正常 | 同上 | note.txt を送付 | 200 保存 | auto | 同上 |
| T05-C003 | D01 | .xlsx 正常（実 xlsx） | 同上 | book.xlsx | 200 保存 | auto | 同上 |
| T05-C004 | D01 | .yaml 正常 | 同上 | data.yaml | 200 保存 | auto | 同上 |
| T05-C005 | D01 | .json 正常 | 同上 | data.json | 200 保存 | auto | 同上 |
| T05-C006 | D01 | .feature 正常 | 同上 | login.feature | 200 保存 | auto | 同上 |
| T05-C007 | D01 | .pdf 正常 | 同上 | tiny.pdf | 200 保存 | auto | 同上 |
| T05-C008 | D01 | .pptx 正常（中身は非pptx） | 同上 | slides.pptx | 拡張子検証のみのため 200（観測を記録） | auto | 同上 |
| T05-C009 | D01 | 大文字拡張子 .MD | 同上 | upper.MD | suffix.lower() により 200 | auto | 同上 |
| T05-C010 | D01 | 複数ファイル同時 | 同上 | ref_good.md + note.txt を1リクエスト | 200 saved 2 件 | auto | 同上 |
| T05-C011 | D02 | .doc 拒否 | 同上 | x.doc | 400 「旧バイナリ形式（.doc)…」文言 | auto | 同上 |
| T05-C012 | D02 | .xls 拒否 | 同上 | x.xls | 400 旧形式文言 | auto | 同上 |
| T05-C013 | D02 | .ppt 拒否 | 同上 | x.ppt | 400 旧形式文言 | auto | 同上 |
| T05-C014 | D03 | .exe 拒否 | 同上 | evil.exe | 400 未対応文言（対応形式一覧付き） | auto | 同上 |
| T05-C015 | D03 | .html 拒否 | 同上 | page.html | 400 未対応 | auto | 同上 |
| T05-C016 | D03 | 拡張子なし拒否 | 同上 | noext | 400 未対応 | auto | 同上 |
| T05-C017 | D04 | 0 バイト .md | 同上 | empty.md | サイズ下限チェックなし→挙動観測（200 想定） | auto | 同上 |
| T05-C018 | D04 | ちょうど 20MB | 同上 | big_eq20mb.md | `>` 判定のため 200 | auto | 同上 |
| T05-C019 | D04 | 20MB+1B | 同上 | big_20mb_plus1.md | 400 上限超文言 | auto | 同上 |
| T05-C020 | D05 | ファイル未指定 | 同上 | files なし POST | 400 「ファイルが指定されていません」 | auto | 同上 |
| T05-C021 | D05 | domain 空 | 同上 | domain="" | 400 「不正なドメインです」 | auto | 同上 |
| T05-C022 | D05 | domain=../evil | 同上 | domain=../evil | 400 不正ドメイン | auto | 同上 |
| T05-C023 | D05 | domain=..%2F..%2Fetc | 同上 | URL エンコード込み | 400 | auto | 同上 |
| T05-C024 | D05 | 未クロールの他ドメイン | 同上 | domain=evil.example | 形式妥当なため 200（任意ディレクトリ作成の観測） | auto | 同上 |
| T05-C025 | D06 | filename=../../evil.md | 同上 | multipart filename 偽装 | Path.name により reference_docs/evil.md へ保存、外部流出なし | auto | 同上 |
| T05-C026 | D06 | filename=..\\evil.md | 同上 | 同上 | POSIX では区切りでない→「..\\evil.md」名で dir 内保存、外部流出なし | auto | 同上 |
| T05-C027 | D06 | filename=/tmp/abs.md 絶対パス | 同上 | 同上 | abs.md として dir 内保存 | auto | 同上 |
| T05-C028 | D06 | filename に NUL（ev\0il.md） | 同上 | 同上 | 4xx で拒否されること（500 なら欠陥） | auto | 同上 |
| T05-C029 | D06 | 超長ファイル名（244 文字） | 同上 | 同上 | 4xx またはエラーメッセージ（500 なら欠陥） | auto | 同上 |
| T05-C030 | D06 | NFC/NFD 同名（ガイド.md） | 同上 | NFC 版・NFD 版を順に送付 | 挙動観測（別ファイル化/上書きを記録） | auto | 同上 |
| T05-C031 | D06 | 同名二重アップロード | 同上 | 同名・異内容を 2 回 | 2 回目が黙って上書き（観測・警告有無を記録） | auto | 同上 |
| T05-C032 | D07 | 偽装 .docx アップロード | 同上 | fake.docx（中身テキスト） | 拡張子のみ検証のため 200（観測） | auto | 同上 |
| T05-C033 | D23 | 混在バッチ（正→不正の順） | 同上 | [ref_good.md, evil.exe] 1 リクエスト | 400 だが先行ファイルの保存有無を検証（部分保存なら欠陥） | auto | 同上 |
| T05-C034 | D08 | safe path: 正規パス | C001 済 | _safe_reference_doc_paths(saved_path, DOM) | 採用される | auto | scripts/t05_safepath.py |
| T05-C035 | D08 | safe path: ../ 混入 | 同上 | output/DOM/reference_docs/../../x.md | 除外 | auto | 同上 |
| T05-C036 | D08 | safe path: 他ドメインのパス | 同上 | output/127.0.0.1:9199/reference_docs/x.md | 除外 | auto | 同上 |
| T05-C037 | D08 | safe path: 不存在ファイル | 同上 | 実在しないパス | 除外（missing_file） | auto | 同上 |
| T05-C038 | D08 | safe path: 絶対パス /etc/hosts | 同上 | 同上 | 除外 | auto | 同上 |
| T05-C039 | D08 | /run に不正+正パス混在（統合） | 同上 | POST /run reference_docs=正,../,他ドメイン | 正のみ使用しクロール続行 | auto | scripts/t05_run_fusion.py |
| T05-C040 | D09 | 参考資料付き実行の成果物 | ref_good.md 保存済 | POST /run urls=/,/about,/contact reference_docs=保存パス | doc_fusion.json/md 生成、report.json に official_name・document_conditions | auto | 同上 |
| T05-C041 | D09 | official_name の妥当性 | C040 済 | doc_fusion.json の screen_matches 確認 | URL ヒント一致で トップページ/会社概要/お問い合わせ が対応 | auto | 同上 |
| T05-C042 | D13 | REQ-999 未対応要件 | C040 済 | requirement_trace.json 確認 | REQ-999 が未対応（matched なし/低スコア）として記録 | auto | 同上 |
| T05-C043 | D14 | REQ-001 重複検出 | C040 済 | 実行ログ・trace 確認 | 重複警告（req_tracer._warn_duplicate_req_ids）が出る | auto | 同上 |
| T05-C044 | D09 | traceability_matrix.md 生成 | C040 済 | ファイル存在と REQ 行確認 | 全 REQ が表に載る | auto | 同上 |
| T05-C045 | D15 | 引用文の原文照合（全件） | C040 済 | doc_fusion.json 内 quote/evidence を ref_good.md と突合 | 全引用が原文に実在 | auto | scripts/t05_quote_audit.py |
| T05-C046 | D10 | 無関係資料のみで実行 | unrelated.md 保存済 | POST /run reference_docs=unrelated.md | 画面対応 0 件・doc_only/crawl_only として gap 報告、実行は完走 | auto | scripts/t05_run_fusion.py |
| T05-C047 | D11 | 幻の管理画面のルール | C040 済 | doc_fusion.json の doc_only 確認 | 幻の管理画面が doc_only（未対応）に載る | auto | 同上 |
| T05-C048 | D12 | 最大長「多め」の解析 | C040 済 | 項目 存在しない項目X の扱い確認 | 解析不能値が例外にならず継続（値の扱いを観測） | auto | 同上 |
| T05-C049 | D07 | 偽装 .docx で実行 | fake.docx 保存済 | CLI: src/main.py --urls http://127.0.0.1:9105/ --reference-doc fake.docx | 読込エラーを補足して継続 or 明示エラー（クラッシュなら欠陥） | auto | scripts/t05_cli_tests.sh |
| T05-C050 | D16 | web /run は --doc-llm を渡さない | コード | crawl.py generate() の cmd 組立を確認 | --doc-llm なし→UI 経由 doc_fusion は LLM 不使用・外部送信なし | code-trace | design.md 参照 |
| T05-C051 | D16 | CLI --doc-llm 鍵未設定 | OPENAI_API_KEY 未設定 | CLI: --doc-llm 付き実行（env -u OPENAI_API_KEY） | Phase1 のみで完走（llm_schema_reject 経路の縮退） | auto | scripts/t05_cli_tests.sh |
| T05-C052 | D16 | 外部送信停止設定の有無 | コード | main.py:1240 付近の provider 選択確認 | OPENAI_API_KEY 存在で自動的に外部呼出。明示的に止める設定の有無を記録 | code-trace | 同上 |
| T05-C053 | D17 | --refresh-doc 単独 | 同上 | CLI: --refresh-doc のみ | 警告して無視、refreshed_spec.md 非生成 | auto | scripts/t05_cli_tests.sh |
| T05-C054 | D18 | refresh 正常系 | ref_good.md | CLI: --reference-doc + --refresh-doc | refreshed_spec.md / refresh_log.json 生成 | auto | 同上 |
| T05-C055 | D19 | refresh 対応 0 件スキップ | unrelated.md | CLI: unrelated.md + --refresh-doc | スキップ（生成なし or 空版とログ）を観測 | auto | 同上 |
| T05-C056 | D20 | selector 逆引き失敗の縮退 | コード | refresh_reporter.py:68-73,169 確認 | None 返却→「実測値を特定できなかった」扱いで継続 | code-trace | design.md 参照 |
| T05-C057 | D21 | /api/doc-fusion 実行済ドメイン | C040 済 | GET /api/doc-fusion?domain=DOM | 200 JSON | auto | scripts/t05_upload_api.py |
| T05-C058 | D21 | 未実行ドメイン | - | domain=nodata.example | 404 {"error":"doc_fusion.json not found"} | auto | 同上 |
| T05-C059 | D21 | 不正ドメイン ../ | - | domain=../../etc | 404 | auto | 同上 |
| T05-C060 | D21 | 破損 JSON→500 | 制約により実書込不可 | コードトレースのみ | crawl.py:318-321 で 500 | code-trace(BLOCKED) | design.md 参照 |
| T05-C061 | D22 | UI 複数選択→一覧表示 | 8765 UI | Playwright: reference-doc-input に 2 ファイル | reference-doc-list に 2 件表示 | auto | scripts/t05_ui_test.py |
| T05-C062 | D22 | UI 削除ボタン | C061 済 | 1 件目の削除クリック | 一覧から消える | auto | 同上 |
| T05-C063 | D22 | UI 拒否理由の表示（.exe） | 8765 UI | evil.exe を選択 | reference-doc-status に未対応文言が表示される | auto | 同上 |
| T05-C064 | D22 | UI 拒否理由の表示（.doc） | 8765 UI | x.doc を選択 | 旧形式の変換案内文言が表示される | auto | 同上 |
| T05-C065 | D24 | 保存後に実体消失で /run | C001 済 | saved パスの実体を退避後 /run | safe path が除外→参考資料なしで完走（missing_file） | auto | scripts/t05_safepath.py |
