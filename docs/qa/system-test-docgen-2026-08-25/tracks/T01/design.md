# テスト設計仕様書 T01 画面発見（discover / discover-stream / 範囲プリセット / 境界値）

## 1. 対象と前提

| 項目 | 内容 |
|---|---|
| 対象 API | `POST /api/discover`（同期）, `POST /api/discover-stream`（SSE） — `web/routes/discover.py` |
| コア | `src/main.py --discover [--stream]` → `src/crawler/page_crawler.py::discover_pages`, `src/crawler/url_safety.py` |
| 契約 | `quality/feature_contracts.yml` feature `discover`（risk_level: critical）。failure_modes: invalid_url / timeout / login_wall / restricted_url（4 件） |
| 環境 | 本体 `http://127.0.0.1:8765`、モック `http://127.0.0.1:9101`（cross=9199）。`02-test-environment.md` が正 |
| パラメータ仕様（実装） | depth: 既定2, クランプ1..10（MAX_DEPTH=10）/ max_pages: 既定30, クランプ1..500（MAX_PAGES_LIMIT=500）/ parallelism（stream のみ）: 既定4, クランプ1..8（MAX_PARALLELISM=8）。クランプは `web/validation.py::_clean_int`（非数値は既定値へフォールバック） |
| タイムアウト仕様（実装） | 同期版は `subprocess.run(timeout=DISCOVER_TIMEOUT_SEC=180)` → 504 + 「画面リスト取得がタイムアウトしました」。SSE 版はルート側タイムアウトなし |
| SSE イベント仕様 | `data: {"run_id"}` → `{"crawl_event":{...}}` → `{"page":{url,title,login_required,login_reasons,login_url}}`×n → `{"done":true,"total":n}`。異常時 `{"error":...}` / キャンセル時 `{"cancelled":true}` |
| CSRF | curl POST は Origin/Referer 無しで許可（02章） |

## 2. テスト条件一覧

| 条件ID | テスト条件 | 契約 failure_mode | 25010 特性 | ツアー/手法 | リスク |
|---|---|---|---|---|---|
| T01-D01 | SSE 正常系: 9101/ を depth 1/2 × max_pages 5/30 で発見し、イベント順序（run_id→crawl_event→page→done）と total=page 件数の整合を確認 | —（required_tests: happy_path/evidence） | 機能適合性（機能正確性） | 契約ベース | High |
| T01-D02 | 同期 API 正常系: 200 + `{"pages":[...]}` | —（happy_path） | 機能適合性 | 契約ベース | Medium |
| T01-D03 | depth 境界値 0/1/10/11 が 1..10 にクランプされる（送信値と実挙動の照合） | — | 機能適合性 | 境界値分析（ISTQB BVA） | Medium |
| T01-D04 | max_pages 境界値 0/1/500/501 が 1..500 にクランプされる | — | 機能適合性 | 境界値分析 | Medium |
| T01-D05 | parallelism 境界値 0/1/8/9 が 1..8 にクランプされ、いずれも正常完了する | — | 機能適合性・性能効率性 | 境界値分析 | Medium |
| T01-D06 | 不正 URL（空 / `not-a-url` / `ftp://x` / `http://` のみ）で 400 と日本語エラーが返る | discover.invalid_url | 機能適合性・使用性 | 契約ベース・エラー推測 | High |
| T01-D07 | ログイン壁: /login を含む発見で login_required/login_reasons/login_url が返る。/dashboard（未ログイン 302→/login）起点で壁検出 | discover.login_wall | 機能適合性 | 契約ベース・状態遷移 | High |
| T01-D08 | robots Disallow 領域（/private/secret）を起点/対象にした場合、クロールされず本文（SECRET-DO-NOT-CRAWL）が漏れない | discover.restricted_url | セキュリティ・機能適合性 | 契約ベース・Saboteur 観点 | High |
| T01-D09 | 遅延・大量リンク（/slow 4秒・/huge 300 リンク）を含む発見が完了し、max_pages で打ち切られる。同期版 180 秒 504 設計の確認 | discover.timeout | 信頼性・性能効率性 | 契約ベース | High |
| T01-D10 | Intellectual Tour: 日本語 URL・クエリ付き URL・フラグメント付き URL の発見が破綻しない | — | 機能適合性・互換性 | Whittaker Intellectual Tour | Medium |

## 3. 網羅性の根拠

| 照合基準 | 対応 |
|---|---|
| `quality/feature_contracts.yml` discover.failure_modes（4 件） | invalid_url→T01-D06 / timeout→T01-D09 / login_wall→T01-D07 / restricted_url→T01-D08。**4/4 全件ケース化** |
| 同 required_tests（happy_path / error_path / evidence） | happy_path→D01,D02 / error_path→D06〜D09 / evidence→全ケースで evidence/ に生ログ保存 |
| ISTQB 境界値分析（2値法: 境界と境界±1） | depth 0/1・10/11（D03）, max_pages 0/1・500/501（D04）, parallelism 0/1・8/9（D05）。上限値は `web/config.py`（MAX_DEPTH=10, MAX_PAGES_LIMIT=500, MAX_PARALLELISM=8）と照合 |
| ISO/IEC 25010 | 機能適合性（D01〜D07）・セキュリティ相当は T06/T07 に委譲しつつ D08 で契約分を担保・信頼性/性能効率性（D09, D05）・互換性（D10） |
| Whittaker ツアー | Intellectual Tour（D10: マルチバイト・クエリ・フラグメント） |
| ISO/IEC/IEEE 29119-3 | 本書=テスト設計仕様、cases.md=ケース仕様、execution-log.md=実行ログの文書体系に準拠 |

## 4. 意図的に除外した条件と理由

| 除外条件 | 理由 |
|---|---|
| 発見中の中断（/api/cancel・`cancelled` イベント） | T03（クロール実行・cancel）の担当範囲 |
| auth（認証状態ファイル）付き discover | T02（ログイン設定・記録）の担当範囲 |
| ウィザード UI 経由の discover 操作・表示 | T10（使用性）の担当範囲。本トラックは API 契約の検証（curl） |
| SSRF 系不正 URL（169.254.169.254 / file:// リダイレクト） | T06（セキュリティ入力系）の担当範囲。本トラックは契約 invalid_url の形式不正のみ |
| `/timeout`（120 秒無応答）を使った実測 | 統括指示により使用禁止。遅延挙動は /slow（4 秒）で代替 |
| 同期版 504 の実測（180 秒待機） | 1 ケース 180 秒超の資源消費は統制対象（A-10）。コードトレース（web/routes/discover.py L39-41）で設計確認し「未実行」と明記 |
| max_pages=501 と 500・depth=11 と 10 の内部値差の外形識別 | モックサイト総ページ数 < 500・深さ 8 のため、クランプ後の値の差が応答に現れない。エラーなく完了することと応答同一性のみ判定し、識別限界を実行ログに明記 |
