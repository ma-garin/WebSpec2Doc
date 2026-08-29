# テストケース仕様書 T04

対象ドメイン: `127.0.0.1:9104` / サンプル: `sample.webspec2doc.local`。証跡は `evidence/` に保存。

| ケースID | 条件ID | 名称 | 前提条件 | 手順 | 期待結果 | 自動化 | スクリプト |
|---|---|---|---|---|---|---|---|
| T04-C001 | T04-D01 | 成果物一式生成 | output/127.0.0.1:9104 不存在 | 1. POST /run（urls=9104の4URL, crawl_mode=selected, format=md,html,json, depth=1, max_pages=10, parallelism=2） 2. ストリームから RUN_ID/REPORT_PATH/SUMMARY を取得 3. output/127.0.0.1:9104/ を検査 | report.json/html/md, screenshots/, snapshots/, audit.jsonl, site.json が全て存在 | auto | scripts/t04_crawl.sh, scripts/t04_checks.py phase1 |
| T04-C002 | T04-D02 | 成果物の中身健全性 | C001 完了 | 1. 各ファイルのサイズ>0 を確認 2. スクショのマジックバイト（PNG/JPEG）確認 3. report.json 内 performance（LCP/CLS/TTFB）の存在と数値確認 | 全ファイル非空・スクショ実画像・LCP/CLS/TTFB が数値で記録 | auto | scripts/t04_checks.py phase1 |
| T04-C003 | T04-D03 | SUMMARY と report.json の整合 | C001 完了 | 1. ストリーム末尾 SUMMARY の screens/forms/fields を取得 2. report.json から実数を集計 3. 突合 | 3 値が一致 | auto | scripts/t04_checks.py phase1 |
| T04-C004 | T04-D04 | /contact フォーム項目反映 | C001 完了 | 1. report.json の /contact 画面のフォーム項目を抽出 2. name/email/body の存在、required/maxlength 属性を確認 | 3 項目が定義され required/maxlength がモック実装どおり | auto | scripts/t04_checks.py phase1 |
| T04-C005 | T04-D05 | /api/result domain 指定 | C001 完了 | GET /api/result?domain=127.0.0.1:9104 | 200。要約（screens 等）と files 一覧が返り実ファイルと一致。is_sample=false | auto | scripts/t04_checks.py phase1 |
| T04-C006 | T04-D05 | /api/result run_id 指定 | C001 完了（RUN_ID 取得済） | GET /api/result?domain=…&run_id=<RUN_ID> | 200。該当実行の結果が返る | auto | scripts/t04_checks.py phase1 |
| T04-C007 | T04-D06 | spec-xlsx エクスポート | C001 完了 | 1. GET /api/export/spec-xlsx?domain=… をファイル保存 2. zipfile として開きシート名を列挙 | 正規 xlsx。シート: 画面一覧/フォーム/項目定義/境界値/テスト設計/テストケース/遷移表 の 7 種 | auto | scripts/t04_checks.py phase1 |
| T04-C008 | T04-D07 | download-zip 完全性 | C001 完了 | 1. GET /download-zip?domain=… を保存 2. testzip 3. 名簿と output 実ファイルを突合 | 破損なし。domain 配下全ファイルを含む | auto | scripts/t04_checks.py phase1 |
| T04-C009 | T04-D08 | preview で report.json 閲覧 | C001 完了 | GET /preview?path=127.0.0.1:9104/report.json | 200・JSON として parse 可能・inline 表示 | auto | scripts/t04_checks.py phase1 |
| T04-C010 | T04-D08 | パストラバーサル拒否（軽確認） | — | GET /preview?path=../../etc/passwd および /download?path=../../etc/passwd | 404（内容漏えいなし） | auto | scripts/t04_checks.py phase1 |
| T04-C011 | T04-D09 | サンプル展開と is_sample | demo/sample_report 同梱 | 1. POST /api/sample-report 2. output/sample.webspec2doc.local/ を検査 3. GET /api/result?domain=sample… の is_sample、9104 側の is_sample を確認 | 200 {domain}。一式展開。sample=is_sample:true / 9104=false で識別可能 | auto | scripts/t04_checks.py phase2 |
| T04-C012 | T04-D10 | サンプルの履歴非混入 | C011 直前に履歴を採取 | 1. POST 前に /api/history・/api/history/runs を保存 2. POST /api/sample-report 3. POST 後の両 API を diff | 差分にサンプル domain の新規エントリが現れない | auto | scripts/t04_checks.py phase2 |
| T04-C013 | T04-D11 | サンプルからの再クロール導線 | C011 完了 | 1. GET /api/site?domain=sample… 2. recrawl.js の URL 復元経路（site→result→https://+domain）と突合 3. UI で再クロールボタンの有無を確認（C017 と併走） | 導線が存在し、復元 URL が到達不能な死に URL のみなら「行き止まり」と判定 | auto(部分) | scripts/t04_checks.py phase2, scripts/t04_ui.py |
| T04-C014 | T04-D12 | 実行履歴の記録と出所 | C001 完了 | 1. GET /api/history/runs に 9104 の実行が RUN_ID 付きで載るか 2. output/usage_log.jsonl に該当行があるか 3. 履歴実装の出所（usage_log.jsonl+実行中ジョブ）を確認 | 実行が記録され、usage_log.jsonl の行と一致 | auto | scripts/t04_checks.py phase1 |
| T04-C015 | T04-D13 | 再クロールでの更新と login_required 保持 | C001 完了・phase1 で事前状態保存済 | 1. site.json/report.json の login_required・mtime を保存 2. 同一 4 URL で POST /run（2 回目） 3. mtime 更新・screens 数維持・login_required 保持を突合 | 成果物が更新され、login_required フラグが消えない | auto | scripts/t04_crawl.sh c015, scripts/t04_checks.py phase3 |
| T04-C016 | T04-D14 | スクリーンショット健全性（重点） | C001 完了 | 1. screenshots/ 全ファイルの size/マジック確認 2. 枚数と report の screen 数を突合 3. 再クロール後（C015）も再確認 | 全画像が実画像・0 バイトなし・枚数=screen 数 | auto | scripts/t04_checks.py phase1/phase3 |
| T04-C017 | T04-D15 | UI: 結果パネルと再クロールボタン | C001・C011 完了 | 1. Playwright headless で 8765/#report/127.0.0.1:9104 を開きスクショ 2. 再クロールボタンの存在確認 3. #report/sample.webspec2doc.local でサンプル表示とサンプル識別表示を確認 | 結果パネルが描画され再クロール導線がある。サンプルはサンプルであると視認できる | auto | scripts/t04_ui.py |
| T04-C018 | T04-D05 | state-table / coverage-heatmap 応答 | C001 完了 | GET /api/state-table?domain=… と /api/coverage-heatmap?domain=… | ともに 200 で成果物由来のデータを返す | auto | scripts/t04_checks.py phase1 |
