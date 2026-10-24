# S07 DONE（1 周目・2026-10-24）

所要時間: 開始 17:43 ／ 終了 17:51（JST・date で取得）
| 工程 | 時刻 | 分 |
|---|---|---|
| 読む（ブリーフ・仕様・既存コード） | 17:43–17:45 | 2 |
| 実装（boundary/judge・画面） | 17:45–17:47 | 2 |
| 起動・実データ通し・3 幅確認 | 17:47–17:50 | 3 |
| 文書・後片付け・版管理 | 17:50–17:51 | 2 |

## 通した経路（検証データ: A1/v1/C_batch_date_boundary/spec_requirements.md ＋ 自作 daily_close.sh・sales.csv）
- /batch-test → POST /api/batch-test/jobs → store.new → data/batchtest/<id>/job.json
- 取り込み → POST …/files（3 件: script/spec/input と判定）→ store.add_file → files/
- 読み取る → POST …/analyze → parse.analyze・docverify.ingest（仕様 65 段落）→ job.facts/spec
- ケース → POST …/cases → design.design＋boundary.cases → 20 件。根拠仕様は REQ-C-002/006/010/011/012/013 等を名指し
- コード → POST …/code → codegen.generate → test_daily_close.py・README.md・fixtures/
- 実行 → スクリプトを sh で 5 ケース（B-01/04/14/15/19）実実行。結果を JUnit XML にして取り込み
- 結果 → POST …/results → judge.parse_junit → job.results（5 件合格）
- 判定 → job.verdict: 全体「判定保留・未検証 15 件」、今回の変更分（B-08 を記入後）「1 件・判定保留」
- 失敗時: 壊れた XML → 400「結果ファイルを読めません。JUnit 形式の XML を選んでください。」
- 作り直しで変更なし → 今回の変更分 0 件（mark_changed の実測）

## 確認した状態と幅
- 観点とケース表（通常・結果あり）: 1366×768 / 1920×1080 / 1024×660 で横スクロール 0、判定帯表示、JS エラー 0
- 案件一覧（通常）1366×768 横スクロール 0
- 撮影: scratchpad/s07data/s07-{1366,1920,1024}.png

## 未検証
- 生成した pytest コードそのものの実行（pytest 実行禁止のため）。スクリプトを直接 5 ケース走らせて代替
- Pester / bats での env_set（TZ）の反映（pytest のみ対応）
- 状態: 読込中・0件・検索0件・未保存・競合・復元・権限不足の撮影（未撮影）
- サーバ停止後に直した段の注記文言 2 か所（JS）の画面表示
- 既存テスト tests/test_batchtest.py への影響（旧「再実行」観点は「冪等性」に統合。未実行）
- parse の既知の誤読: awk の式を出力ファイル、$3 を引数3と読む（既存不具合・未修正）

## 要判断
- 「今回の変更分」の定義: 前回の作成から観点・入力・期待結果が変わったケース＋追加・記入したケース。基準をコミット差分や前回書き出しに置くかは未決
- 作り直しで実行結果を空に戻す（ID が振り直されるため）。結果を残す運用が要るか
- 部分失敗・再開は「手動確認」で skip 生成。単位（店舗）を模擬する自動ケースを作るか

## 変更要求
- なし（v1）
