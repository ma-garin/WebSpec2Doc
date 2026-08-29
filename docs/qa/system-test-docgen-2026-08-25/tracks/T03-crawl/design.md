# テスト設計仕様書 T03 クロール実行

## 1. 対象と前提

- 対象: `POST /run`（クロール実行ストリーム）・`POST /api/cancel`・`GET /api/live-screenshot`・実行ビュー UI（`templates/partials/view-generate.html` P3/P4, `static/js/execution.js`）。
- 契約: `quality/feature_contracts.yml` feature_id="crawl"（risk_level: critical）。failure_modes 11 項目を全て条件化する。
- SUT: 本体 `http://127.0.0.1:8765`（停止禁止）。モック `http://127.0.0.1:9103`（9199 は iframe 参照先のみ）。02-test-environment.md を正とし環境再調査はしない。
- 前提条件（実測記録）: 開始時点で `output/127.0.0.1:9103/` は存在しない（`ls output/` 実測）。よって compare=true「初回」条件が成立する。`output/` の既存 19 エントリには触れない。
- クロール 1 回は数十秒〜数分かかるため、条件を 10 実行（G, A, B, B2, B3, C1, C2, C3, D, E）+ UI 2 実行（H1, H2）に束ねる。
- 設計根拠のソース事実（読解済み・実行で検証する）:
  - selected モードでも robots.txt は `_filter_robots_targets` で適用され、除外 URL は `crawl_started.robots_skipped_urls` に載る（page_crawler.py:521-538）。
  - 429/503 は `RetryableHTTPError` → `backoff_delays`（初期 2 秒・上限 60 秒・最大 5 回）で再試行（politeness.py:58-73, 247-252）。
  - 破壊的リクエストは `MutationBlocker` が遮断し `audit.jsonl` に `mutation_blocked` を記録（page_crawler.py:998, _audit_mutation_blocked）。
  - ページ遷移タイムアウトは `DEFAULT_TIMEOUT_MS=30_000`（page_crawler.py:46）。
  - closed shadow root は `"shadow:<タグ名>"` として embedded_frames に記録（page_crawler.py:223-228）。
  - `format` は `ALLOWED_FORMATS` 許可リストで濾過し空なら md,html、json は常時付加（crawl.py:92-95, validation.py:_clean_formats）。
  - cancel は `_terminate_proc`（SIGTERM）→ `returncode < 0` → `停止しました。`（crawl.py:167-169, 242-249）。

## 2. テスト条件一覧

| 条件ID | テスト条件 | 契約 failure_mode | 25010 特性 | ツアー/手法 | リスク |
|---|---|---|---|---|---|
| T03-D01 | selected モード 5 URL 指定の正常系（screens=5・REPORT_PATH・イベント順序） | (happy_path) | 機能適合性 | 契約ベース | High |
| T03-D02 | auto モード max_pages=10 でちょうど 10 画面で停止 | (happy_path) | 機能適合性 | 境界値分析 | High |
| T03-D03 | auto モード depth=2 の深さ制限（/deep/ 直鎖での打ち切り） | (happy_path) | 機能適合性 | 境界値分析 | High |
| T03-D04 | parallelism 1/4/8 で同一 URL 集合の結果一致（非決定性検出） | (happy_path) | 信頼性 | ペア実行比較 | High |
| T03-D05 | 実行途中の /api/cancel（停止応答・プロセス終了・部分成果物） | cancel, partial_checkpoint | 信頼性 | 契約ベース | Critical |
| T03-D06 | cancel API 頑健性（誤 run_id・二重・完了後） | cancel | 信頼性 | ネガティブ | Medium |
| T03-D07 | robots 禁止 URL を selected で明示指定（取得されないこと） | robots_disallowed | セキュリティ | 契約ベース | Critical |
| T03-D08 | auto モードでの robots 除外（イベント・非クロール） | robots_disallowed | セキュリティ | 契約ベース | Critical |
| T03-D09 | 429 + Retry-After での再試行・backoff・最終結果 | rate_limit_backoff | 信頼性 | 障害注入 | High |
| T03-D10 | 破壊操作の遮断（deleted=False・audit.jsonl・JS ボタン） | mutation_blocked, mutation_blocked_audit | セキュリティ | 障害注入 | Critical |
| T03-D11 | cross-origin iframe（9199）と same-origin iframe の記録 | cross_origin_iframe | 機能適合性 | 契約ベース | Medium |
| T03-D12 | closed shadow root 内リンクの到達不能報告・open 側の扱い | closed_shadow_root | 機能適合性 | 契約ベース | Medium |
| T03-D13 | 認証なしで /dashboard 指定時のログイン壁扱い | login_wall_during_crawl | 機能適合性 | 契約ベース | High |
| T03-D14 | ページ単位タイムアウト（/timeout）後の実行継続・/slow の成功 | timeout | 信頼性 | 障害注入 | High |
| T03-D15 | 異常ページの扱い（/500・/broken-link・マルチバイト URL） | (error_path) | 信頼性 | エラー推測 | Medium |
| T03-D16 | format 許可リスト外（format=exe,../x）の無害化 | (error_path) | セキュリティ | ネガティブ | High |
| T03-D17 | compare=true の初回実行（前回スナップショット無し） | (error_path) | 信頼性 | 境界値分析 | Medium |
| T03-D18 | 実行ビュー UI の進行表示（estep・ログ逐次・プレビュー・ETA/件数） | (evidence) | 使用性 | UI ツアー | High |
| T03-D19 | UI 操作系（停止ボタン・新規実行・レポート遷移・再送防止） | cancel | 使用性 | UI ツアー | High |
| T03-D20 | 全失敗モード混在後の report.json 整合性（部分結果・復旧） | partial_checkpoint | 信頼性 | 契約ベース | High |
| T03-D21 | 内部 IP / file スキームへのリダイレクトの非追従 | restricted_url | セキュリティ | 障害注入 | Critical |

## 3. 網羅性の根拠

- 照合基準: ISO/IEC 25010:2011（機能適合性・信頼性〔成熟性/障害許容性/回復性〕・セキュリティ・使用性に条件を割付）、ISTQB CTFL v4.0 のテスト技法（境界値分析 D02/D03/D17・ネガティブテスト D06/D16・障害注入は ISO/IEC/IEEE 29119-4 の error guessing / fault injection に対応）。
- 契約 failure_modes との対応表:

| failure_mode | 条件ID |
|---|---|
| login_wall_during_crawl | D13 |
| restricted_url | D21 |
| timeout | D14 |
| cancel | D05, D06, D19 |
| partial_checkpoint | D05, D20 |
| robots_disallowed | D07, D08 |
| rate_limit_backoff | D09 |
| mutation_blocked | D10 |
| mutation_blocked_audit | D10 |
| cross_origin_iframe | D11 |
| closed_shadow_root | D12 |

- required_tests との対応: happy_path=D01-D04 / error_path=D15-D17 / cancel_path=D05,D06,D19 / checkpoint_path=D05,D20 / evidence=全実行のストリーム・output 成果物・audit.jsonl・UI スクリーンショットを evidence/ に保存。

## 4. 意図的に除外した条件と理由

- `/xss`（XSS 注入ページの解析安全性）: セキュリティトラックの担当領域。クロール実行の制御フローには関与しない。
- `auth` 指定ありのログインクロール・`/mfa` 突破: T-ログイン系トラックの担当（feature_id="login"）。本トラックは「認証なしでの壁検出」のみ扱う。
- `/api/discover-stream` 系: T-画面解析トラックの担当（feature_id="discover"）。
- `/huge`（300 リンク）の性能限界・MAX_PAGES_LIMIT=500 上限: 性能トラック領域。max_pages 境界は 10 で代表させる（境界値の機構は同一）。
- reference_docs / doc_fusion 連携: feature_id="doc_fusion" の担当。
- 9199 側を対象としたクロール: 割当 port 違反になるため実施しない（iframe 参照先としてのみ使用）。
