# テスト環境定義

## 1. 被試験体（SUT）

| 項目 | 値 |
|---|---|
| 本体（通常テスト用） | `http://127.0.0.1:8765` — `FLASK_TESTING=1 WEBSPEC2DOC_ALLOW_LOCAL=1 WEBSPEC2DOC_AUTH_MODE=off` |
| 本体（破壊試験専用・T09 のみ停止可） | `http://127.0.0.1:8766` — 同上 + `WEBSPEC2DOC_PORT=8766 WEBSPEC2DOC_DATA_DIR=<scratchpad>/data8766` |
| 起動ログ | `/tmp/ws2d.log`, `/tmp/ws2d_8766.log` |
| 出力先 | リポジトリ直下 `output/{host:port}/`（両インスタンス共通・CWD 相対） |
| 事前状態 | `output/` に過去実行ディレクトリ（`127.0.0.1:8765` 等 10 件）が残存。**削除禁止**。前提条件として記録する |
| Python | `venv/bin/python`（Playwright sync_api 利用可） |
| ソース | 変更禁止。テストは読み取りと実行のみ |

## 2. モック対象サイト（`env/mock_site.py`）

起動: `python3 env/mock_site.py <port> 9199`。各トラックは割当 port のみ使用（出力先 `output/127.0.0.1:<port>/` が分離される）。9199 は cross-origin iframe の参照先。

| パス | 用途 |
|---|---|
| `/` | 21 リンクのハブ |
| `/about`, `/about/team`, `/products`, `/products/{1..12}`, `/products/{n}/detail|reviews` | 通常階層（depth 1〜3） |
| `/contact`, `/form` | フォーム（required/maxlength/pattern/number/date/select/radio/checkbox/file/hidden） |
| `/login` | ID `admin` / PW `secret123` で Cookie `session=ok` → `/dashboard`。失敗は 401 |
| `/mfa` | 2 段階（コード `000000`） |
| `/dashboard`, `/account`, `/dashboard/settings` | Cookie 無しは `/login?next=` へ 302（ログイン壁） |
| `/robots.txt` | `Disallow: /private/` |
| `/private/secret` | robots 禁止領域（本文 `SECRET-DO-NOT-CRAWL`） |
| `/slow` | 4 秒遅延 / `/timeout` 120 秒無応答 |
| `/xss` | title/本文/属性に script 注入（`window.__xss*` フラグ・`document.title='XSS-EXEC'`） |
| `/iframe` | cross-origin (9199) と same-origin の iframe |
| `/shadow` | closed/open Shadow DOM 内リンク |
| `/redirect-internal` | 302 → `http://169.254.169.254/latest/meta-data/` |
| `/redirect-file` | 302 → `file:///etc/passwd` |
| `/rate-limited` | 3 回に 1 回 429 + `Retry-After: 1` |
| `/mutation` | `POST /delete` の削除フォーム＋JS ボタン。`/mutation-state` で `deleted=True/False` を確認 |
| `/broken-link` | 404 リンクと到達不能ホスト |
| `/deep/1..8` | 深さ 8 の直鎖 |
| `/huge` | 300 リンク |
| `/500` | 500 応答 |
| `/unicode/日本語ページ` | マルチバイト URL |

## 3. API 仕様（実測・2026-08-25）

| API | 入力（form） | 出力 |
|---|---|---|
| `POST /api/discover-stream` | `url`, `depth`(1..10), `max_pages`(1..500), `parallelism`(1..8), `auth` | SSE `data: {"run_id"}` → `{"crawl_event":{...}}` → `{"page":{url,title,login_required,login_reasons,login_url}}` → `{"done":true,"total":n}` |
| `POST /api/discover` | 同上（同期版） | `{"pages":[...]}` / 400 / 504（180 秒） / 500 |
| `POST /run` | `urls`(カンマ区切り), `login_urls`, `login_landing_url`, `depth`, `max_pages`, `format`(md,html,json), `compare`, `auth`, `crawl_mode`(auto/selected), `parallelism`, `reference_docs`, `scope_preset`, `scope_depth`, `scope_max_pages` | text stream: `RUN_ID:` → ログ行 / `CRAWL_EVENT:{...}` → `REPORT_PATH:` → `SUMMARY:{screens,forms,fields,buttons}`。停止時 `停止しました。` |
| `POST /api/cancel` | `run_id` | `{"ok":bool}` |
| `GET /api/live-screenshot` | `domain` | 画像 |
| `POST /api/reference-docs` | `domain`, files | `{"ok","saved"}` / 400（不正ドメイン・未指定・旧形式 .doc/.xls・非対応拡張子・サイズ上限超） |
| `GET /api/doc-fusion?domain=` | | fusion 結果 |
| `POST /api/login/simple` | `domain`, `login_url`, `username`, `password` | `{"success"}`。資格情報は stdin 経由 |
| `POST /api/login/scrape` | `url` | フォーム項目 |
| `POST /api/login/submit` | `domain`, `login_url`, `fields_json` | |
| `POST /api/login/record/start|complete|cancel`, `GET /api/login/record/status?domain=` | `domain`, `url`, `pid` | `.login_status.json` |
| `GET /api/result?domain=&run_id=` | | report.json 要約・files |
| `GET /api/site?domain=` | | site.json |
| `POST /api/sample-report` | | サンプル展開 |
| `GET /api/history`, `/api/history/runs` | | 実行履歴 |

CSRF: POST は `Origin`/`Referer` が同一ホストなら許可、いずれも無ければ許可（curl 用）。`Origin: null` や他ホストは 403。Host ヘッダは許可ホスト以外 403。

## 4. 制約・禁止事項（全トラック共通）

1. **8765 を停止・再起動しない**（T09 のみ 8766 を停止してよい）。
2. **ソース・テンプレート・設定を変更しない。** `output/` 配下の既存ディレクトリを削除しない。
3. **割当 port 以外のモックを使わない。** 他トラックの出力ディレクトリに触れない。
4. **`pytest` / `make test` / `make verify-ui` / `make lint` を実行しない**（ハーネス側で拒否される）。
5. **UI 操作は `venv/bin/python` + Playwright sync_api のスクリプト（headless）で行う。** MCP 共有ブラウザは並列衝突するため使わない。スクリプトは `tracks/<ID>/scripts/` に保存する（納品対象）。
6. 秘密情報（API キー・パスワード）を証跡に残さない。`.env` を読まない。
7. 書き込み先は自トラックのディレクトリ `docs/qa/system-test-docgen-2026-08-25/tracks/<ID>/` のみ。
8. 環境の再調査をしない（本書が正）。不明点は「未確認」と書いて進める。
