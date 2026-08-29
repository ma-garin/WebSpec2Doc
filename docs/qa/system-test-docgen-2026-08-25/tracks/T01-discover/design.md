# テスト設計仕様書 T01 画面発見（discover）

## 1. 対象と前提

- 対象: `POST /api/discover-stream`（SSE）、`POST /api/discover`（同期）、`POST /api/cancel`、ドキュメント作成画面 P1（`/generate` の `#wizard-p1`）。
- 実装経路（設計根拠として読解）: `web/routes/discover.py` → `src/main.py --discover [--stream]`（サブプロセス）→ `src/crawler/page_crawler.py: discover_pages` / `parallel_crawler.py: discover_pages_parallel` → `src/crawler/url_safety.py: is_safe_target`。UI は `static/js/wizard.js`（`validateUrlInput`, `discoverUrls`）と `templates/partials/view-generate.html`。
- 環境: `02-test-environment.md` が正。本体 `http://127.0.0.1:8765`（`WEBSPEC2DOC_ALLOW_LOCAL=1`, `AUTH_MODE=off`）、モック `http://127.0.0.1:9101`（9199 は iframe 参照先）。
- 前提条件: `output/` に過去実行ディレクトリが残存（削除禁止）。`WEBSPEC2DOC_ALLOW_LOCAL=1` のため `validate_target_url` のローカル/プライベート IP 拒否は**無効化されている**（url_safety.py L57-58: `if _local_targets_allowed(): return`）。restricted_url 系の判定は「本番既定（ALLOW_LOCAL 無し）では拒否されるはずの URL に対し、本環境では到達を試みる」ことを前提に、追従挙動（リダイレクト先の再検証有無）を観測する。
- 設計上の着眼点（ソース読解で得た仮説。検証対象）:
  1. ルート層は `url` の非空チェックのみで、スキーム・ホスト検証を行わない（discover.py L18-24, L54-58）。安全判定はクローラ側 `_skip_reason → is_safe_target` に依存し、不正 URL は「エラー」ではなく「0 件発見」として返る可能性がある。
  2. `normalize_url` はスキーム欠落時に `https` を補う（page_crawler.py L1037）。スキーム無し入力は https として扱われる。
  3. `is_safe_target` は**遷移前 URL のみ**を検査し、HTTP リダイレクト先（`/redirect-internal` → 169.254.169.254、`/redirect-file` → file://）は再検証されない。
  4. SSE 版には全体タイムアウトが無い（`DISCOVER_TIMEOUT_SEC=180` は同期版 `subprocess.run` のみ）。ページ単位は Playwright `DEFAULT_TIMEOUT_MS=30_000`。
  5. `_clean_int` は範囲外を**クランプ**、非数値を**既定値**に置換する（400 を返さない）。
  6. `url` が `-` 始まりの場合 `--url --version` として argparse に渡る。

## 2. テスト条件一覧

| 条件ID | テスト条件 | 契約 failure_mode | 25010 特性 | ツアー/手法 | リスク |
|---|---|---|---|---|---|
| T01-D01 | 不正 URL（空・空白・非 http スキーム・スキーム無し・IDN・超長・改行・`-` 始まり）で 400 または明示エラーが返り、サブプロセスが安全に終了する | discover.invalid_url | 機能適合性 / 信頼性 | 契約ベース + 同値分割 + 悪意ツアー | High |
| T01-D02 | 内部/予約アドレス・localhost・IP 表記ゆれ・内部/file へのリダイレクトを起点にした時の拒否または追従 | discover.restricted_url | セキュリティ | 契約ベース + SSRF チェックリスト（OWASP ASVS V12.6 / SSRF 表記ゆれ） | Critical |
| T01-D03 | 無応答ページ（/timeout）・遅延ページ（/slow）のページ単位タイムアウトと同期版 180 秒の全体タイムアウト | discover.timeout | 信頼性（回復性）/ 性能効率性 | 契約ベース + 時間計測 | High |
| T01-D04 | ログイン壁（302 → /login）の `login_required` 判定と `login_url` | discover.login_wall | 機能適合性 | 契約ベース | High |
| T01-D05 | 正常系: SSE イベント順序（run_id → crawl_event → page → done）、page フィールド、done.total とページ数の一致 | happy_path | 機能適合性 / 互換性（プロトコル） | ランドマークツアー | High |
| T01-D06 | depth / max_pages / parallelism の境界値（クランプ・既定値置換）と max_pages ちょうどでの停止 | error_path | 機能適合性 | 境界値分析 | Medium |
| T01-D07 | 発見途中の `/api/cancel` によるストリーム終了とサブプロセス残存なし | evidence | 信頼性 / 保守性（資源解放） | 契約ベース + プロセス観測 | High |
| T01-D08 | robots.txt Disallow 配下（/private/secret）が発見対象から除外され、page_skipped が通知される | restricted_url（robots） | 適法性 / 機能適合性 | 契約ベース | High |
| T01-D09 | 500 応答・壊れたリンク・到達不能ホスト・マルチバイト URL でクローラが落ちない | error_path | 信頼性（成熟性） | 障害ツアー | Medium |
| T01-D10 | 末尾スラッシュ・#fragment・?query の正規化と重複排除 | happy_path | 機能適合性（正確性） | 同値分割 | Medium |
| T01-D11 | 同期版 `/api/discover` と SSE 版で発見 URL 集合が一致する | happy_path | 機能適合性（一貫性） | バックツーバック比較 | Medium |
| T01-D12 | クライアント切断時にサブプロセスが終了する | evidence | 信頼性（資源解放） | 障害ツアー + プロセス観測 | High |
| T01-D13 | UI: url-input 検証メッセージ、プリセット→depth/max_pages 反映、カスタム入力、sample-url-btn | invalid_url（UI） | 使用性 / 機能適合性 | UI 契約（wizard.js） | Medium |
| T01-D14 | UI: discover-loading/elapsed 表示、p1-screens-num / p1-login-num の API との一致、p1-next-btn 活性、url-history-list、中断ボタン | evidence（UI） | 使用性 / 機能適合性 | UI 契約（wizard.js） | High |
| T01-D15 | CSRF: `Origin: null` の POST を 403 で拒否 | restricted_url（起点制限） | セキュリティ | 02-test-environment §3 の CSRF 仕様 | High |

## 3. 網羅性の根拠

- 契約 `quality/feature_contracts.yml` feature_id=discover: `failure_modes` = invalid_url / timeout / login_wall / restricted_url、`required_tests` = happy_path / error_path / evidence。

| 契約項目 | 対応条件 |
|---|---|
| invalid_url | D01, D13 |
| timeout | D03 |
| login_wall | D04 |
| restricted_url | D02, D08, D15 |
| happy_path | D05, D10, D11 |
| error_path | D06, D09 |
| evidence | D07, D12, D14（証跡: SSE ログ・ps 出力・スクリーンショット） |

- 照合した外部基準:
  - ISO/IEC 25010:2023 品質特性（機能適合性・信頼性・セキュリティ・使用性・性能効率性・互換性）で各条件を分類。
  - ISTQB CTFL v4.0 テスト技法: 同値分割（D01, D10）、境界値分析（D06）、状態遷移（D07: 実行中→中断）、エラー推測（D09）。
  - OWASP ASVS 4.0 V12.6（SSRF 対策）と PortSwigger SSRF 表記ゆれ（10 進 IP・16 進 IP・`127.1` 短縮・IPv6・リダイレクト経由）を D02 の入力集合に使用。
  - Rapid Software Testing のツアー（ランドマーク・障害・悪意）を手法欄に記載。

## 4. 意図的に除外した条件と理由

- `auth`（保存済みセッション）付き発見: ログイン機能トラック（他トラック担当）の範囲。
- 実インターネット上の IDN ホスト（例 `日本語.jp`）: 外部送信禁止のため `.invalid` TLD（RFC 2606）で代替。
- `WEBSPEC2DOC_ALLOW_LOCAL` 無しでの拒否動作: 本体 8765 の再起動が禁止のため実測不可。ソース根拠（url_safety.py）のみ記載し「未検証」とする。
- SSE 版の全体タイムアウト（180 秒超）: ソース上存在しないことを読解で確認（D03 に観測項目として記載、実測は同期版のみ）。
- max_pages=500 の実測: 501 と同一のクランプ後値（500）となり `/huge`（301 画面）では識別不能のため 501 のみ実測。
