# テストケース仕様書 T05

前提共通: 本体 `http://127.0.0.1:8765` 稼働、`output/127.0.0.1:9105/` を事前クロールで生成済み。`D=127.0.0.1:9105`。フィクスチャは `scripts/fixtures/`。

| ケースID | 条件ID | 名称 | 前提条件 | 手順 | 期待結果 | 自動化 | スクリプト |
|---|---|---|---|---|---|---|---|
| T05-C001 | T05-D01 | 正常 .md | ref.md 準備 | `curl -F domain=$D -F files=@ref.md /api/reference-docs` | 200 `{ok:true, saved:[ref.md]}`。`reference_docs/ref.md` 実在 | auto | run_t05.sh |
| T05-C002 | T05-D02 | 複数 .txt+.pdf | ref.txt/ref.pdf | 同上に files を2つ添付 | 200、saved 2 件 | auto | run_t05.sh |
| T05-C003 | T05-D01 | 正常 .docx | ref.docx | files=@ref.docx | 200 saved | auto | run_t05.sh |
| T05-C004 | T05-D01 | 正常 .xlsx | ref.xlsx | files=@ref.xlsx | 200 saved | auto | run_t05.sh |
| T05-C005 | T05-D01 | 正常 .feature/.json/.yaml | 各fixture | files を3つ添付 | 200 saved 3 件 | auto | run_t05.sh |
| T05-C010 | T05-D03 | legacy .doc | legacy.doc | files=@legacy.doc | 400 `旧バイナリ形式（.doc）は未対応`、保存されない | auto | run_t05.sh |
| T05-C011 | T05-D03 | legacy .xls | legacy.xls | files=@legacy.xls | 400 `旧バイナリ形式（.xls）` | auto | run_t05.sh |
| T05-C012 | T05-D03 | legacy .ppt | legacy.ppt | files=@legacy.ppt | 400 `旧バイナリ形式（.ppt）` | auto | run_t05.sh |
| T05-C020 | T05-D04 | 非対応 .exe | bad.exe | files=@bad.exe | 400 `未対応の文書形式です: bad.exe` | auto | run_t05.sh |
| T05-C021 | T05-D04 | 非対応 .zip | bad.zip | files=@bad.zip | 400 `未対応の文書形式` | auto | run_t05.sh |
| T05-C022 | T05-D04 | 非対応 .svg | bad.svg | files=@bad.svg | 400 `未対応の文書形式` | auto | run_t05.sh |
| T05-C030 | T05-D05 | サイズ境界 20MB ちょうど | exact20mb.md（20971520B） | files=@exact20mb.md | 200 saved（`>` 判定のため上限値は許可） | auto | run_t05.sh |
| T05-C031 | T05-D05 | サイズ境界 20MB+1 | over20mb.md（20971521B） | files=@over20mb.md | 400 `ファイルサイズが上限（20MB）を超えています` | auto | run_t05.sh |
| T05-C040 | T05-D06 | traversal `../../evil.md` | evil_payload.md | `files=@payload;filename=../../evil.md` | `reference_docs/` 外へ書かれない（`Path().name` で `evil.md` に丸め） | auto | run_t05.sh |
| T05-C041 | T05-D06 | traversal `..%2f..%2fpasswd.md` | 同上 | `filename=..%2f..%2fpasswd.md` | 外へ書かれない（%2f 非デコード・リテラル保存） | auto | run_t05.sh |
| T05-C042 | T05-D06 | traversal 絶対パス名 | 同上 | `filename=/private/tmp/abs_evil.md` | 外へ書かれない（`abs_evil.md` に丸め） | auto | run_t05.sh |
| T05-C043 | T05-D06 | traversal バックスラッシュ | 同上 | `filename=..\..\win.md` | POSIX 上は外へ書かれない（リテラル保存） | auto | run_t05.sh |
| T05-C050 | T05-D07 | 不正domain 空 | ref.md | `domain=` | 400 `不正なドメインです` | auto | run_t05.sh |
| T05-C051 | T05-D07 | 不正domain `../` | ref.md | `domain=../127.0.0.1:9105` | 400 `不正なドメインです` | auto | run_t05.sh |
| T05-C052 | T05-D07 | 不正domain スラッシュ | ref.md | `domain=127.0.0.1:9105/../../etc` | 400 `不正なドメインです` | auto | run_t05.sh |
| T05-C053 | T05-D11 | 未クロールの妥当domain | ref.md | `domain=192.0.2.55:1` | 挙動観測（副作用: ディレクトリ生成の有無） | auto | run_t05.sh |
| T05-C060 | T05-D08 | missing_file | — | files 添付なし | 400 `ファイルが指定されていません` | auto | run_t05.sh |
| T05-C070 | T05-D09 | doc-fusion 候補不在 | doc_fusion.json 不在 | `GET /api/doc-fusion?domain=$D` | 404 `doc_fusion.json not found`（candidates_file_missing_or_corrupt 相当） | auto | run_t05.sh |
| T05-C071 | T05-D10 | doc-fusion 不正domain | — | `?domain=../etc` | 404 `not found`（情報を返さない） | auto | run_t05.sh |
| T05-C080 | T05-D12 | LLM抽出系 failure_modes | 実LLM | コード確認（`matcher.py`/`filter_hallucinations`/`load_reference_documents`） | 未実行（実LLM未接続）。設計・コード存在のみ確認 | manual | — |
