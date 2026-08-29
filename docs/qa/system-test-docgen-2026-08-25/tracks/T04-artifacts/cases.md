# テストケース仕様書 T04

前提共通: 8765 稼働・9104 モック稼働・`output/127.0.0.1:9104/` は初回実行前に不存在。DOM=`127.0.0.1:9104`、BASE=`http://127.0.0.1:8765`。

| ケースID | 条件ID | 名称 | 前提条件 | 手順 | 期待結果 | 自動化 | スクリプト |
|---|---|---|---|---|---|---|---|
| T04-C001 | T04-D01 | 初回実行の完走 | 出力ディレクトリ不存在 | 1. `POST /run`（urls=/,/about,/products,/contact,/form,/login・crawl_mode=selected・format=md,html,json） 2. ストリーム保存 | RUN_ID/REPORT_PATH/SUMMARY が出力され正常終了 | auto | scripts/run_crawl.sh |
| T04-C002 | T04-D02 | report.json 画面数 | C001 完了 | report.json を解析 | screens が 6 件・選択 6 URL と一致 | auto | scripts/verify_run1.py |
| T04-C003 | T04-D02 | SUMMARY 整合 | C001 | SUMMARY と report.json の集計を突合 | screens/forms/fields/buttons が完全一致 | auto | scripts/verify_run1.py |
| T04-C004 | T04-D03 | required 抽出 | C001 | `/form` 画面の fields を検査 | required が記録されている | auto | scripts/verify_run1.py |
| T04-C005 | T04-D03 | maxlength 抽出 | C001 | 同上 | maxlength が記録されている | auto | scripts/verify_run1.py |
| T04-C006 | T04-D03 | pattern 抽出 | C001 | 同上 | pattern が記録されている | auto | scripts/verify_run1.py |
| T04-C007 | T04-D03 | min/max 抽出 | C001 | 同上 | number/date の min/max が記録されている | auto | scripts/verify_run1.py |
| T04-C008 | T04-D04 | report.html 件数一致 | C001 | report.html 内の画面 URL を照合 | 6 画面すべて記載 | auto | scripts/verify_run1.py |
| T04-C009 | T04-D04 | screens.md/forms.md | C001 | md の存在と画面数照合 | 存在し全画面記載 | auto | scripts/verify_run1.py |
| T04-C010 | T04-D05 | スクショ欠損ゼロ | C001 | screenshots/*.png を数える | 画面数分（6 枚）存在 | auto | scripts/verify_run1.py |
| T04-C011 | T04-D06 | snapshots 永続化 | C001 | snapshots/ を確認 | スナップショットが保存される | auto | scripts/verify_run1.py |
| T04-C012 | T04-D07 | audit.jsonl | C001 | 行数・各行 JSON 妥当性 | 存在し全行有効 JSON | auto | scripts/verify_run1.py |
| T04-C013 | T04-D08 | site.json 条件保存 | C001 | site.json 解析 | urls=6 件・crawl_mode=selected・depth/max_pages 記録 | auto | scripts/verify_run1.py |
| T04-C014 | T04-D08 | login_urls 無偽陽性 | C001（login_urls 未指定） | site.json の login_urls | 空（偽フラグなし） | auto | scripts/verify_run1.py |
| T04-C015 | T04-D09 | accessibility_audit.json | C001 | 存在と JSON 妥当性 | 生成され解析可能 | auto | scripts/verify_run1.py |
| T04-C016 | T04-D09 | technical_health.json | C001 | 存在と JSON 妥当性 | 生成され解析可能 | auto | scripts/verify_run1.py |
| T04-C017 | T04-D10 | /api/result summary | C001 | `GET /api/result?domain=DOM` | summary が report.json 集計と一致 | auto | scripts/verify_api.py |
| T04-C018 | T04-D10 | files 実在 | C017 | files の非空パスを stat | 全パスが実在ファイル | auto | scripts/verify_api.py |
| T04-C019 | T04-D10 | screenshots/is_sample | C017 | 応答の screenshots・is_sample | 実ファイルと一致・is_sample=false | auto | scripts/verify_api.py |
| T04-C020 | T04-D12 | /api/runs 一覧 | C001 | `GET /api/runs/DOM` | total=1・run_id あり・current_run_id 一致 | auto | scripts/verify_api.py |
| T04-C021 | T04-D12 | run 詳細整合 | C020 | `GET /api/runs/DOM/<id>` | artifacts/files が実在と一致・position 1/1 | auto | scripts/verify_api.py |
| T04-C022 | T04-D12 | /exists | C020 | 実在 id と架空 id で照会 | true / false | auto | scripts/verify_api.py |
| T04-C023 | T04-D12 | /artifact + traversal | C020 | name=report.json と name=../../../etc/passwd | 前者パス返却・後者 404 | auto | scripts/verify_api.py |
| T04-C024 | T04-D11 | run_id 指定 result | C020 | `GET /api/result?domain=DOM&run_id=<id>` | 当該回の summary と一致 | auto | scripts/verify_api.py |
| T04-C025 | T04-D13 | 履歴の実行条件 | C001 | `GET /api/history/runs` | DOM 行に scope_preset/depth/max_pages/crawl_mode/target_url_count | auto | scripts/verify_api.py |
| T04-C026 | T04-D14 | 2 回目実行 | C001〜 | `POST /run`（urls=/,/products,/dashboard・login_urls=/dashboard） | 正常完了 | auto | scripts/run_crawl.sh |
| T04-C027 | T04-D14 | 最新の上書き | C026 | 現 report.json の screens | 2 回目の URL 集合（3 件）に置き換わる | auto | scripts/verify_run2_history.py |
| T04-C028 | T04-D14 | runs 2 件 | C026 | `GET /api/runs/DOM` | total=2・新しい順 | auto | scripts/verify_run2_history.py |
| T04-C029 | T04-D14 | 過去回の取り出し | C026 | `GET /api/result?run_id=<run1>` | 1 回目の内容（6 画面）を返す | auto | scripts/verify_run2_history.py |
| T04-C030 | T04-D14 | 過去回スクショ保全 | C026 | runs/<run1>/screenshots | 6 枚保持 | auto | scripts/verify_run2_history.py |
| T04-C031 | T04-D15 | 履歴順序・時刻 | C026 | `/api/history/runs` の DOM 行 | 2 件・降順・時刻妥当 | auto | scripts/verify_run2_history.py |
| T04-C032 | T04-D17 | 再クロール条件復元 | C026 | `GET /api/site?domain=DOM` | 2 回目の urls/depth/max_pages/crawl_mode を復元 | auto | scripts/verify_run2_history.py |
| T04-C033 | T04-D17 | login_required 保全 | C026 | site.json の login_urls | /dashboard が残る | auto | scripts/verify_run2_history.py |
| T04-C034 | T04-D16 | サンプル展開 | - | `POST /api/sample-report` | 200・domain=sample.webspec2doc.local | auto | scripts/verify_sample_recrawl.py |
| T04-C035 | T04-D16 | is_sample 明示 | C034 | `GET /api/result?domain=sample...` | is_sample=true | auto | scripts/verify_sample_recrawl.py |
| T04-C036 | T04-D16 | 履歴不混入 | C034 | `/api/history`・`/api/history/runs` | sample ドメインが現れない | auto | scripts/verify_sample_recrawl.py |
| T04-C037 | T04-D16 | サンプル再クロール導線 | C034 | `GET /api/site?domain=sample...` | 導線の実態を記録（dead-end 検証） | auto | scripts/verify_sample_recrawl.py |
| T04-C038 | T04-D18 | xlsx 7 シート | C026 | `/api/export/spec-xlsx?domain=DOM` を openpyxl で開く | 7 シート（画面一覧〜遷移表） | auto | scripts/verify_export_preview.py |
| T04-C039 | T04-D18 | 行数 UI 一致 | C038 | 画面一覧シート行数と report.json | 画面数と一致 | auto | scripts/verify_export_preview.py |
| T04-C040 | T04-D18 | 再エクスポート重複なし | C038 | 2 回目の取得・比較 | シート名同一・重複なし | auto | scripts/verify_export_preview.py |
| T04-C041 | T04-D18 | 不正ドメイン | - | `?domain=../etc` | 404 | auto | scripts/verify_export_preview.py |
| T04-C042 | T04-D19 | download-zip | C026 | `/download-zip?domain=DOM` を zipfile で開く | 有効 ZIP・report.json 含む | auto | scripts/verify_export_preview.py |
| T04-C043 | T04-D20 | spec-ts | C026 | `/api/report/DOM/spec-ts` | 200 または理由付き 404 | auto | scripts/verify_export_preview.py |
| T04-C044 | T04-D21 | preview 正常 | C026 | report.json と report.html を `/preview` | 200・inline 表示 | auto | scripts/verify_export_preview.py |
| T04-C045 | T04-D21 | preview 異常系 | C026 | 不在パス・output 外パス・他ドメインパス | 不在/外部は 404。他ドメインの挙動を記録 | auto | scripts/verify_export_preview.py |
| T04-C046 | T04-D22 | report.json 破損 | C026・バックアップ取得 | report.json を不正 JSON に置換し `/api/result` | 500 でなく縮退応答（エラー明示） | auto | scripts/verify_corrupt.py |
| T04-C047 | T04-D22 | report.json 欠落 | C046 | report.json を退避し `/api/result` | 縮退応答・復元後正常 | auto | scripts/verify_corrupt.py |
| T04-C048 | T04-D23 | 結果パネル件数 | C026 | Playwright で `/runs/DOM/<current>` を開く | ドメイン・件数表示が report.json と一致 | auto | scripts/ui_results_panel.py |
| T04-C049 | T04-D23 | タブ・リンク実在 | C048 | タブ表示とファイルリンクを収集し HTTP 照合 | 全リンク 200・実ファイルと一致 | auto | scripts/ui_results_panel.py |
| T04-C050 | T04-D23 | btn-view-report 経由 | UI からの実行完了 | UI で実行→btn-view-report 押下 | 結果ビューへ遷移 | manual | -（未実行予定・design.md 4. 参照） |
