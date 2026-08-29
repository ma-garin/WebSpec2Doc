# テストケース仕様書 T01

前提条件（全ケース共通）: 本体 8765・モック 9101 稼働（02-test-environment.md）。curl は Origin/Referer 無しで POST。証跡は `evidence/<実行ID>.log|.json` と `evidence/summary.txt`（HTTP コード・所要時間）。

| ケースID | 条件ID | 名称 | 前提条件 | 手順 | 期待結果 | 自動化 | スクリプト |
|---|---|---|---|---|---|---|---|
| T01-C001 | T01-D01 | SSE 発見 depth1/max5 イベント順序 | 共通 | 1. `t01_cases.sh part1`（実行ID C001: url=9101/, depth=1, max_pages=5, parallelism=4） | HTTP200。先頭行 run_id → crawl_event → page×n → 最終行 done。n≤5 かつ total=n | auto | scripts/t01_cases.sh |
| T01-C002 | T01-D01 | SSE 発見 depth2/max30 total 整合 | 共通 | 1. 同（C002: depth=2, max_pages=30） | HTTP200。page 件数=total≤30。depth2 のページ（/products/N 配下等）を含む | auto | scripts/t01_cases.sh |
| T01-C003 | T01-D02 | 同期発見 depth1/max5 | 共通 | 1. 同（C003） | HTTP200。`{"pages":[...]}` 件数≤5。各要素に url/title | auto | scripts/t01_cases.sh |
| T01-C004 | T01-D03 | depth=0 → 1 クランプ | 共通 | 1. 同（C004a: depth=0, max_pages=40）2. C004b: depth=1 と比較 | depth=0 がエラー・0 件にならず、depth=1 と同一件数（クランプの実挙動） | auto | scripts/t01_cases.sh |
| T01-C005 | T01-D03 | depth=11 → 10 クランプ | 共通 | 1. 同（C004c: url=9101/deep/1, depth=11）2. C004d: depth=10 と比較 | depth=11 がエラーなく完了し depth=10 と同一結果（/deep/8 まで到達）。内部値差は外形識別不能のため応答同一性で判定 | auto | scripts/t01_cases.sh |
| T01-C006 | T01-D04 | max_pages=0 → 1 クランプ | 共通 | 1. 同（C005a: max_pages=0）2. C005b: max_pages=1 と比較 | max_pages=0 で 0 件・エラーにならず 1 件返る | auto | scripts/t01_cases.sh |
| T01-C007 | T01-D04 | max_pages=501 → 500 クランプ | 共通 | 1. 同（C005c: url=9101/about, max_pages=501）2. C005d: 500 と比較 | 501 がエラーなく完了し 500 と同一結果（識別限界は design.md §4） | auto | scripts/t01_cases.sh |
| T01-C008 | T01-D05 | parallelism=0 → 1 クランプ | 共通 | 1. `t01_cases.sh part2`（C006a: depth=1, max_pages=10, parallelism=0） | HTTP200・done まで完了。page 集合が C006b と一致 | auto | scripts/t01_cases.sh |
| T01-C009 | T01-D05 | parallelism=9 → 8 クランプ | 共通 | 1. 同（C006b: parallelism=9） | HTTP200・done まで完了（エラーなし） | auto | scripts/t01_cases.sh |
| T01-C010 | T01-D06 | 空 URL（同期） | 共通 | 1. 同（C007: url=） | HTTP400 + `{"pages":[],"error":"URLを入力してください"}` | auto | scripts/t01_cases.sh |
| T01-C011 | T01-D06 | 空 URL（SSE） | 共通 | 1. 同（C007s: url=） | HTTP400 + 日本語エラー JSON（ストリームでなく即時応答） | auto | scripts/t01_cases.sh |
| T01-C012 | T01-D06 | `not-a-url`（同期/SSE） | 共通 | 1. 同（C008, C008s） | 契約期待: HTTP400 + 日本語エラー | auto | scripts/t01_cases.sh |
| T01-C013 | T01-D06 | `ftp://x`（スキーム不正） | 共通 | 1. 同（C009） | 契約期待: HTTP400 + 日本語エラー | auto | scripts/t01_cases.sh |
| T01-C014 | T01-D06 | `http://`（ホスト欠落） | 共通 | 1. 同（C010） | 契約期待: HTTP400 + 日本語エラー | auto | scripts/t01_cases.sh |
| T01-C015 | T01-D07 | ハブ発見でログイン壁ページ検出 | 共通 | 1. 同（C011: url=9101/, depth=1, max_pages=40） | /dashboard 等の page に login_required=true・login_reasons 非空・login_url 設定 | auto | scripts/t01_cases.sh |
| T01-C016 | T01-D07 | /dashboard 起点（302→/login）で壁検出 | 共通 | 1. 同（C012: url=9101/dashboard） | 発見結果に login_required=true・login_url に /login を含む | auto | scripts/t01_cases.sh |
| T01-C017 | T01-D08 | robots 禁止領域を起点 | 共通 | 1. 同（C013: url=9101/private/secret） | /private/secret の本文（SECRET-DO-NOT-CRAWL）が証跡に現れない。robots スキップが観測できる | auto | scripts/t01_cases.sh |
| T01-C018 | T01-D08 | robots 禁止領域が発見対象に含まれる | C011 実行済み | 1. C011/C002 の SSE ログを解析 | 発見 page 一覧に /private/ 配下が含まれない（または robots_skipped として通知） | auto（ログ解析） | scripts/t01_cases.sh |
| T01-C019 | T01-D09 | /slow（4 秒遅延）を含む発見の完了 | 共通 | 1. 同（C015a: url=9101/slow） | HTTP200・done 到達。所要 ≥4 秒（遅延がタイムアウト扱いされない） | auto | scripts/t01_cases.sh |
| T01-C020 | T01-D09 | /huge（300 リンク）の max_pages 打ち切り | 共通 | 1. 同（C015b: url=9101/huge, max_pages=50, parallelism=8） | HTTP200・total≤50 で done（打ち切りが機能） | auto | scripts/t01_cases.sh |
| T01-C021 | T01-D09 | 同期版 180 秒タイムアウト 504 設計 | — | 1. コードトレース: web/routes/discover.py L39-41, web/config.py DISCOVER_TIMEOUT_SEC=180 | 504 + 「画面リスト取得がタイムアウトしました」（設計確認のみ・実測は 180 秒超の資源統制により未実行） | manual | —（未実行） |
| T01-C022 | T01-D10 | 日本語 URL 起点の発見 | 共通 | 1. 同（C016: url=9101/unicode/日本語ページ） | HTTP200・ページが発見され title/url が文字化けしない | auto | scripts/t01_cases.sh |
| T01-C023 | T01-D10 | クエリ付き URL 起点の発見 | 共通 | 1. 同（C017: url=9101/products/1?ref=qa&x=1） | HTTP200・クエリで処理が破綻しない | auto | scripts/t01_cases.sh |
| T01-C024 | T01-D10 | フラグメント付き URL 起点の発見 | 共通 | 1. 同（C018: url=9101/about#team） | HTTP200・フラグメントが無害に処理される | auto | scripts/t01_cases.sh |
