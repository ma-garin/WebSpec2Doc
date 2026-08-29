# テストケース仕様書 T03

実行束ね: RUN-G(初回 compare/format) → RUN-A(selected 5URL) → RUN-B(auto max_pages) → RUN-B2(auto depth) → RUN-B3(auto shadow) → RUN-C1/C2/C3(parallelism 1/4/8) は scripts/phase1_runs.py。RUN-D(失敗モード混在 14URL) → RUN-E(cancel) は scripts/phase2_failures.py。RUN-H1/H2(UI) は scripts/ui_execution_test.py。ベース: APP=http://127.0.0.1:8765, MOCK=http://127.0.0.1:9103。

| ケースID | 条件ID | 名称 | 前提条件 | 手順 | 期待結果 | 自動化 | スクリプト |
|---|---|---|---|---|---|---|---|
| T03-C001 | T03-D01 | selected 5URL で screens=5 | 9103 稼働 | 1. /run に urls=/,/about,/products,/contact,/form (5件), crawl_mode=selected, parallelism=4 を POST 2. ストリーム全読 | SUMMARY.screens が 5 | auto | scripts/phase1_runs.py RUN-A |
| T03-C002 | T03-D01 | REPORT_PATH の実在 | C001 実行 | 1. REPORT_PATH: 行のパスを stat | report.html が存在しサイズ>0 | auto | 同上 |
| T03-C003 | T03-D01 | ストリームのイベント順序 | C001 実行 | 1. 行順を解析: RUN_ID → crawl_started → page_started×n → crawl_completed → REPORT_PATH → SUMMARY | この順序で並ぶ。SUMMARY が最終行群にある | auto | 同上 |
| T03-C004 | T03-D01 | SUMMARY と report.json の整合 | C001 実行 | 1. SUMMARY の screens/forms を report.json の pages/forms 集計と比較 | 両者が一致 | auto | 同上 |
| T03-C005 | T03-D01 | 5 画面分のスクリーンショット | C001 実行 | 1. report.json 各 page の screenshot_path を確認 | 5 件全てに存在するファイルパス | auto | 同上 |
| T03-C006 | T03-D02 | auto max_pages=10 ちょうどで停止 | 9103 稼働 | 1. /run auto url=/ depth=2 max_pages=10 2. SUMMARY.screens とクロール済み page 数 | ちょうど 10。11 件目の page_started が無い | auto | scripts/phase1_runs.py RUN-B |
| T03-C007 | T03-D02 | max_pages 超過分の打ち切りイベント | RUN-B | 1. イベント列から page_started 総数を数える | page_started ≦ 10 | auto | 同上 |
| T03-C008 | T03-D08 | auto での robots 除外 | RUN-B（/private/secret は / から被リンク） | 1. イベント列の robots_skipped_urls / page_skipped(reason=robots) 2. report.json に /private/secret が無いこと | /private/secret はクロールされず、除外がイベントで可視 | auto | 同上 |
| T03-C009 | T03-D03 | depth=2 の深さ打ち切り | 9103 稼働 | 1. /run auto url=/deep/1 depth=2 max_pages=10 2. report.json の /deep/N 最大値 | 深さ制限を超える /deep/N がクロールされない（実測 N を記録） | auto | scripts/phase1_runs.py RUN-B2 |
| T03-C010 | T03-D03 | depth 超過の page_skipped イベント | RUN-B2 | 1. page_skipped(reason=depth 系) の有無 | 深さ超過がイベントとして可視 | auto | 同上 |
| T03-C011 | T03-D04 | parallelism 1 vs 4 の screens 一致 | 9103 稼働 | 1. 同一 6URL 集合で parallelism=1 と 4 を各 1 回実行 2. SUMMARY 比較 | screens が一致 | auto | scripts/phase1_runs.py RUN-C1/C2 |
| T03-C012 | T03-D04 | parallelism 4 vs 8 の screens 一致 | 同上 | 1. parallelism=8 で同一集合 2. 比較 | screens が一致 | auto | scripts/phase1_runs.py RUN-C2/C3 |
| T03-C013 | T03-D04 | forms/fields/buttons の 3 実行一致 | RUN-C1..C3 | 1. SUMMARY の forms/fields/buttons を 3 実行で比較 | 全て一致（不一致なら非決定性として記録） | auto | 同上 |
| T03-C014 | T03-D05 | 途中 cancel でストリームが「停止しました。」 | 実行中 run_id 取得 | 1. selected 4URL parallelism=1 で開始 2. 2 件目 page_started 観測後 /api/cancel 3. ストリーム末尾 | 末尾に 停止しました。 が出て終了 | auto | scripts/phase2_failures.py RUN-E |
| T03-C015 | T03-D05 | cancel API 正常応答 | RUN-E | 1. /api/cancel run_id=実 run_id | {"ok": true} | auto | 同上 |
| T03-C016 | T03-D05 | サブプロセス終了 | RUN-E cancel 後 | 1. ps -eo pid,command から src/main.py かつ 9103 を含む行を検索 | 該当プロセス無し | auto | 同上 |
| T03-C017 | T03-D05 | 部分成果物の状態 | RUN-E cancel 後 | 1. checkpoint_saved イベント有無 2. output/127.0.0.1:9103 配下の部分スナップショット 3. report.json が JSON として壊れていないこと | 途中結果が checkpoint として残るか、残らない場合も report.json は解釈可能（実測を記録） | auto | 同上 |
| T03-C018 | T03-D06 | 誤った run_id の cancel | 8765 稼働 | 1. /api/cancel run_id=deadbeef | {"ok": false} | auto | 同上 |
| T03-C019 | T03-D06 | 二重 cancel | RUN-E 直後 | 1. 同じ run_id で /api/cancel を再送 | 2 回目は ok:false（実測を記録） | auto | 同上 |
| T03-C020 | T03-D06 | 完了後 cancel | RUN-G 完了 | 1. 完了済み run_id で /api/cancel | {"ok": false} | auto | scripts/phase1_runs.py RUN-G |
| T03-C021 | T03-D07 | robots 禁止 URL の selected 明示指定 | 9103 稼働 | 1. RUN-D の urls に /private/secret を含めて実行 2. crawl_started.robots_skipped_urls とクロール済み一覧 | /private/secret はクロールされず robots_skipped_urls に載る | auto | scripts/phase2_failures.py RUN-D |
| T03-C022 | T03-D07 | 禁止本文の非取得 | RUN-D 完了 | 1. output/127.0.0.1:9103 全体を SECRET-DO-NOT-CRAWL で grep | ヒット 0 件 | auto | 同上 |
| T03-C023 | T03-D09 | 429 後の再試行と最終成功 | rate カウンタを次回 429 になる位置へ事前調整 | 1. RUN-D に /rate-limited を含め実行 2. /rate-limited の最終取得結果 | 429 を受けても backoff 再試行で最終的にページ取得成功 | auto | 同上 |
| T03-C024 | T03-D09 | backoff の証跡 | RUN-D | 1. ストリーム/イベント/audit.jsonl から 429・リトライ・待機の記録を探す | 再試行が証跡として可視 | auto | 同上 |
| T03-C025 | T03-D09 | /rate-limited/next の取得 | RUN-D | 1. report.json に /rate-limited/next が screens として存在 | 存在する | auto | 同上 |
| T03-C026 | T03-D10 | 破壊 POST の遮断（フォーム） | RUN-D に /mutation | 1. RUN-D 完了後 curl /mutation-state | deleted=False | auto | 同上 |
| T03-C027 | T03-D10 | audit.jsonl の mutation_blocked 記録 | RUN-D 完了 | 1. output/127.0.0.1:9103/**/audit.jsonl を検索 | event=mutation_blocked のレコードが存在し /delete への POST を含む | auto | 同上 |
| T03-C028 | T03-D10 | mutation_blocked の CRAWL_EVENT | RUN-D | 1. ストリームから event=mutation_blocked を探す | イベントが流れる（JS fetch POST も遮断対象） | auto | 同上 |
| T03-C029 | T03-D11 | cross-origin iframe の記録 | RUN-D に /iframe | 1. report.json の /iframe の embedded_frames | 9199 の絶対 URL が記録され、9199 側ページは screens に含まれない | auto | 同上 |
| T03-C030 | T03-D11 | same-origin iframe の記録 | RUN-D | 1. 同上で /about（same-origin iframe src）の記録 | same-origin iframe も embedded_frames に記録 | auto | 同上 |
| T03-C031 | T03-D12 | closed shadow host の記録 | RUN-D に /shadow | 1. report.json の /shadow の embedded_frames に shadow:<tag> 形式 | closed shadow root の存在が記録される | auto | 同上 |
| T03-C032 | T03-D12 | open shadow 内リンクの追従（auto） | 9103 稼働 | 1. /run auto url=/shadow depth=2 max_pages=10 2. /shadow/open-link のクロール有無 | open 側の実測を記録（取得可否） | auto | scripts/phase1_runs.py RUN-B3 |
| T03-C033 | T03-D12 | closed shadow 内リンクの到達不能 | RUN-B3 | 1. /shadow/hidden-link のクロール有無・報告 | クロールされない。到達不能である事実が成果物から判別可能 | auto | 同上 |
| T03-C034 | T03-D13 | ログイン壁のイベント | RUN-D に /dashboard（auth なし） | 1. event=login_wall_detected の有無 | /dashboard で発火 | auto | scripts/phase2_failures.py RUN-D |
| T03-C035 | T03-D13 | ログイン壁ページの report 扱い | RUN-D 完了 | 1. report.json/スナップショットに SECRET-AFTER-LOGIN が無いこと 2. /dashboard の screens 計上 | 認証後コンテンツ非取得。壁はスキップ扱いで記録 | auto | 同上 |
| T03-C036 | T03-D14 | /timeout でのページ打ち切り | RUN-D に /timeout | 1. /timeout の結果イベント 2. 後続ページのクロール継続 | 約 30 秒で当該ページのみ失敗し実行は継続 | auto | 同上 |
| T03-C037 | T03-D14 | /slow の正常取得 | RUN-D に /slow | 1. report.json に /slow | 4 秒遅延はタイムアウト内で取得成功 | auto | 同上 |
| T03-C038 | T03-D14 | 全体所要の妥当性 | RUN-D | 1. 実行の壁時計時間を計測 | ハングせず有限時間（目安 5 分以内）で完了 | auto | 同上 |
| T03-C039 | T03-D15 | /500 の扱い | RUN-D に /500 | 1. /500 のイベント・report 記録 | クラッシュせずエラーとして記録（実測を記録） | auto | 同上 |
| T03-C040 | T03-D15 | /broken-link ページの取得 | RUN-D に /broken-link | 1. report.json に /broken-link（selected のためリンク先は追わない） | ページ自体は取得成功 | auto | 同上 |
| T03-C041 | T03-D15 | マルチバイト URL | RUN-D に /unicode/日本語ページ | 1. report.json の該当 page とタイトル | 取得成功・タイトル「日本語」系が文字化けなし | auto | 同上 |
| T03-C042 | T03-D21 | 内部 IP リダイレクトの非追従 | RUN-D に /redirect-internal | 1. 169.254.169.254 のコンテンツ取得有無・イベント | メタデータ IP へ追従しない（取得コンテンツ無し） | auto | 同上 |
| T03-C043 | T03-D21 | file スキームリダイレクトの非追従 | RUN-D に /redirect-file | 1. 成果物に /etc/passwd 内容（root:）が無いこと | file:// へ追従しない | auto | 同上 |
| T03-C044 | T03-D16 | format 許可リスト外の無害化 | 9103 稼働・初回 | 1. /run urls=/about format=exe,../x compare=true 2. 応答と output 配下の生成物 | 400 か、既定形式（md,html,json）へ丸めて成功。exe/../x 由来のファイルが無い | auto | scripts/phase1_runs.py RUN-G |
| T03-C045 | T03-D17 | compare=true 初回実行 | output/127.0.0.1:9103 不存在（実測済み） | 1. RUN-G の完走とエラー有無 | 前回スナップショット無しでもエラー終了しない | auto | 同上 |
| T03-C046 | T03-D18 | estep-0..3 の進行 | 8765 UI・Playwright headless | 1. /generate で画面解析→実行 2. estep の class 遷移を記録 | is-active が 0→3 へ単調進行し完了で全て is-complete | auto | scripts/ui_execution_test.py RUN-H1 |
| T03-C047 | T03-D18 | exec-log の逐次表示 | RUN-H1 実行中 | 1. exec-log の textContent 長を 2 時点で採取 | 実行中に増加する | auto | 同上 |
| T03-C048 | T03-D18 | ライブプレビュー画像 | RUN-H1 実行中 | 1. exec-preview-image の src と表示状態（/api/live-screenshot） | 画像が取得され表示される（naturalWidth>0 または show class） | auto | 同上 |
| T03-C049 | T03-D18 | exec-eta / exec-count の妥当性 | RUN-H1 実行中 | 1. 実行中の exec-count・exec-eta のテキスト | 件数が n/m 形式で対象数と整合、ETA が表示される | auto | 同上 |
| T03-C050 | T03-D19 | 停止ボタンでの停止 | RUN-H2 実行中 | 1. exec-stop-btn 押下 2. ボタン表示と最終画面 | 「停止中…」→「実行を停止しました」。二度押し不能（disabled） | auto | scripts/ui_execution_test.py RUN-H2 |
| T03-C051 | T03-D19 | 実行中のフォーム再送防止 | RUN-H1/H2 実行中 | 1. 実行中に gen-panel の表示状態と form への再 submit 試行 | 入力パネル非表示で再送できない（二重実行が起きない） | auto | 同上 |
| T03-C052 | T03-D19 | exec-new-btn で入力へ戻る | RUN-H2 停止後 | 1. exec-new-btn 押下 | 実行ビューが閉じ入力パネルが再表示 | auto | 同上 |
| T03-C053 | T03-D19 | btn-view-report でレポート遷移 | RUN-H1 完了後 | 1. btn-view-report 押下 | 結果ビューが表示される | auto | 同上 |
| T03-C054 | T03-D20 | 失敗モード混在後の report.json 整合 | RUN-D 完了 | 1. report.json を JSON パース 2. pages 数と成功/失敗の内訳整合 | パース可能で、成功ページのみが screens 計上。壊れなし | auto | scripts/phase2_failures.py RUN-D |
