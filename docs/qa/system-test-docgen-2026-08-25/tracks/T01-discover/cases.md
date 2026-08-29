# テストケース仕様書 T01

共通前提: 本体 8765 起動済み（`ALLOW_LOCAL=1`, `AUTH_MODE=off`）、モック 9101 起動済み。M=`http://127.0.0.1:9101`。API ケースは form で `url` / `depth` / `max_pages` / `parallelism` を送る（省略時 depth=2, max_pages=30, parallelism=4）。SSE の期待は `data:` 行を JSON 化したイベント列で記述する。

| ケースID | 条件ID | 名称 | 前提条件 | 手順 | 期待結果 | 自動化 | スクリプト |
|---|---|---|---|---|---|---|---|
| T01-C001 | T01-D05 | SSE 正常系イベント順序 | 共通 | 1. `POST /api/discover-stream` url=M/ depth=2 max_pages=30 parallelism=4 2. 全イベント受信 | 先頭が `run_id`、次に `crawl_event`(discover_started…)、`page` が 1 件以上、末尾が `done:true`。`error` 無し | auto | scripts/api_discover.py A |
| T01-C002 | T01-D05 | page フィールド | C001 と同時 | page イベントを検査 | 各 page に `url`,`title`,`login_required`(bool),`login_reasons`(list),`login_url`(str) が存在 | auto | 同上 |
| T01-C003 | T01-D05 | done.total とページ数一致 | C001 と同時 | done.total と page 件数を比較 | `done.total == page 件数` かつ ≤ 30 | auto | 同上 |
| T01-C004 | T01-D04 | /login /dashboard の login_required | C001 と同時 | url 末尾 `/login`,`/dashboard` の page を抽出 | 両方 `login_required=true`、`login_url` に `/login` を含む。`/about` は false | auto | 同上 |
| T01-C005 | T01-D01 | url 空 | 共通 | url="" を POST | HTTP 400、`error` に「URLを入力してください」 | auto | 同上 |
| T01-C006 | T01-D01 | url 空白のみ | 共通 | url="   " を POST | HTTP 400 | auto | 同上 |
| T01-C007 | T01-D01 | `ftp://` | 共通 | url=`ftp://127.0.0.1:9101/` | 400 または SSE で `error`/`page_skipped(unsafe_url)`。page 0 件。done で正常終了 | auto | 同上 |
| T01-C008 | T01-D01 | `javascript:` | 共通 | url=`javascript:alert(1)` | 同上（ページ 0 件・エラー明示）。サーバ側で実行されない | auto | 同上 |
| T01-C009 | T01-D01 | `data:` | 共通 | url=`data:text/html,<h1>x</h1>` | 同上 | auto | 同上 |
| T01-C010 | T01-D01 | スキーム無し | 共通 | url=`127.0.0.1:9101/about` | 400 か、または明示的に http/https 補完して結果を返す（補完先を記録） | auto | 同上 |
| T01-C011 | T01-D01 | IDN ホスト | 共通 | url=`http://テスト.invalid/` | ページ 0 件・エラー明示・サブプロセス正常終了（外部送信なし） | auto | 同上 |
| T01-C012 | T01-D01 | 65,000 文字 URL | 共通 | url=`http://127.0.0.1:9101/` + "a"×65000 | 400 または SSE で正常終了（500/例外なし） | auto | 同上 |
| T01-C013 | T01-D01 | 改行混入 | 共通 | url=`http://127.0.0.1:9101/\nfoo` | 400 または 改行を除去して処理（記録） | auto | 同上 |
| T01-C014 | T01-D01 | `-` 始まり | 共通 | url=`--version` | 400 または SSE `error`。サブプロセスの argparse エラーが利用者に露出しない | auto | 同上 |
| T01-C015 | T01-D02 | メタデータ IP | ALLOW_LOCAL=1 | url=`http://169.254.169.254/` depth=1 max_pages=1 | 本番既定では拒否（未検証）。本環境では到達試行の有無と所要時間を記録。page_skipped(unsafe_url) が出れば PASS | auto | scripts/api_discover.py B |
| T01-C016 | T01-D02 | プライベート IP | 同上 | url=`http://10.0.0.1/` | 同上 | auto | 同上 |
| T01-C017 | T01-D02 | IPv6 ループバック | 同上 | url=`http://[::1]/` | 同上 | auto | 同上 |
| T01-C018 | T01-D02 | 16 進 IP | 同上 | url=`http://0x7f000001/` | 同上 | auto | 同上 |
| T01-C019 | T01-D02 | 短縮 IP | 同上 | url=`http://127.1/` | 同上 | auto | 同上 |
| T01-C020 | T01-D02 | localhost | 同上 | url=`http://localhost/` | 同上（ALLOW_LOCAL=1 の影響を明記） | auto | 同上 |
| T01-C021 | T01-D02 | 内部へのリダイレクト追従 | 同上 | url=M/redirect-internal depth=1 max_pages=2 | リダイレクト先（169.254.169.254）を再検証して拒否。page の url が 169.254 になっていない | auto | 同上 |
| T01-C022 | T01-D02 | file:// へのリダイレクト | 同上 | url=M/redirect-file | file:// に追従しない。page に `/etc/passwd` 相当の内容が無い | auto | 同上 |
| T01-C023 | T01-D03 | 無応答ページ起点 | 共通 | url=M/timeout depth=1 max_pages=3 | ページ単位タイムアウト（30 秒）で打ち切り、done で正常終了。所要 ≤ 60 秒 | auto | 同上 |
| T01-C024 | T01-D03 | 遅延ページ | 共通 | url=M/slow depth=1 max_pages=3 | /slow が page として発見される（4 秒遅延はタイムアウト未満） | auto | 同上 |
| T01-C025 | T01-D03 | 同期版 180 秒タイムアウト | 共通 | `POST /api/discover` url=M/huge depth=1 max_pages=500 | 180 秒超なら 504 + error。180 秒内なら pages 返却（所要を記録） | auto | scripts/api_discover.py L |
| T01-C026 | T01-D04 | ログイン壁起点 | 共通 | url=M/dashboard depth=1 max_pages=5 | page.login_required=true、login_url に `/login` を含む | auto | scripts/api_discover.py A |
| T01-C027 | T01-D06 | depth=0 | 共通 | url=M/deep/1 depth=0 max_pages=20 | 400 またはクランプ（1 扱い → 2 画面）。挙動を記録 | auto | scripts/api_discover.py C |
| T01-C028 | T01-D06 | depth=1 | 共通 | 同 depth=1 | 2 画面（/deep/1, /deep/2） | auto | 同上 |
| T01-C029 | T01-D06 | depth=10 | 共通 | 同 depth=10 | 8 画面（鎖の末端まで） | auto | 同上 |
| T01-C030 | T01-D06 | depth=11 | 共通 | 同 depth=11 | 400 またはクランプ 10 → 8 画面 | auto | 同上 |
| T01-C031 | T01-D06 | depth=-1 | 共通 | 同 depth=-1 | 400 またはクランプ 1 → 2 画面 | auto | 同上 |
| T01-C032 | T01-D06 | depth=abc | 共通 | 同 depth=abc | 400 または既定 2 → 3 画面 | auto | 同上 |
| T01-C033 | T01-D06 | max_pages=0 | 共通 | url=M/huge depth=1 max_pages=0 | 400 またはクランプ 1 → 1 画面 | auto | 同上 |
| T01-C034 | T01-D06 | max_pages=1 | 共通 | 同 max_pages=1 | 1 画面（/huge のみ） | auto | 同上 |
| T01-C035 | T01-D06 | max_pages=500 | 共通 | 同 max_pages=500 | 301 画面（/huge + 300 リンク） | manual | 未実行（design §4） |
| T01-C036 | T01-D06 | max_pages=501 | 共通 | 同 max_pages=501 parallelism=8 | 400 またはクランプ 500 → 301 画面 | auto | scripts/api_discover.py L |
| T01-C037 | T01-D06 | max_pages=abc | 共通 | 同 max_pages=abc | 400 または既定 30 → 30 画面 | auto | scripts/api_discover.py C |
| T01-C038 | T01-D06 | parallelism=0 | 共通 | url=M/huge depth=1 max_pages=5 parallelism=0 | 400 またはクランプ 1 → 5 画面 | auto | 同上 |
| T01-C039 | T01-D06 | parallelism=1 | 共通 | 同 parallelism=1 | 5 画面 | auto | 同上 |
| T01-C040 | T01-D06 | parallelism=8・max_pages ちょうどで停止 | 共通 | 同 max_pages=20 parallelism=8 | ちょうど 20 画面（超過なし） | auto | 同上 |
| T01-C041 | T01-D06 | parallelism=9 | 共通 | 同 max_pages=20 parallelism=9 | 400 またはクランプ 8 → 20 画面 | auto | 同上 |
| T01-C042 | T01-D07 | 発見途中のキャンセル | 共通 | 1. SSE 開始 url=M/?t01cancel=1 depth=2 max_pages=30 2. 1 page 受信後 `POST /api/cancel` run_id 3. ストリーム終端待ち 4. `ps` で `--discover` プロセス確認 | cancel が `{"ok":true}`、ストリームが `cancelled` で終端、5 秒以内にサブプロセス消滅 | auto | scripts/api_discover.py D |
| T01-C043 | T01-D08 | robots 除外 | 共通 | C001 のイベントを検査 | page に `/private/secret` が無い。`page_skipped reason=robots` イベントあり | auto | scripts/api_discover.py A |
| T01-C044 | T01-D09 | 500 応答起点 | 共通 | url=M/500 depth=1 max_pages=3 | 例外なく done。500 ページの扱い（page 出力の有無）を記録 | auto | 同上 |
| T01-C045 | T01-D09 | 壊れたリンク | 共通 | url=M/broken-link depth=1 max_pages=5 | 404 先・到達不能ホストで落ちず done。所要 ≤ 60 秒 | auto | 同上 |
| T01-C046 | T01-D09 | マルチバイト URL | 共通 | url=M/unicode/日本語ページ depth=1 max_pages=2 | page.url がデコード可能な同一 URL、title 取得 | auto | 同上 |
| T01-C047 | T01-D10 | 末尾スラッシュ正規化 | 共通 | url=M/about/ max_pages=1 | page.url が `M/about`（スラッシュ除去）または一貫した表記 | auto | 同上 |
| T01-C048 | T01-D10 | #fragment 除去 | 共通 | url=M/about#sec max_pages=1 | page.url に `#` を含まない | auto | 同上 |
| T01-C049 | T01-D10 | ?query 保持 | 共通 | url=M/about?x=1 max_pages=1 | page.url に `?x=1` が保持される | auto | 同上 |
| T01-C050 | T01-D11 | 同期版と SSE 版の一致 | 共通 | `/api/discover` と `/api/discover-stream` を url=M/about depth=1 max_pages=10 で実行 | url 集合が一致 | auto | 同上 |
| T01-C051 | T01-D12 | クライアント切断 | 共通 | 1. SSE 開始 url=M/?t01disc=1 2. run_id 受信直後にソケット close 3. 10 秒後 `ps` | サブプロセスが消滅している | auto | scripts/api_discover.py D |
| T01-C052 | T01-D15 | CSRF Origin: null | 共通 | `Origin: null` 付きで POST | 403 | auto | scripts/api_discover.py A |
| T01-C053 | T01-D13 | UI: URL 未入力で解析 | `/generate` 表示 | 画面解析クリック | `#url-input-message` に「URLを入力してから…」 | auto | scripts/ui_discover.py |
| T01-C054 | T01-D13 | UI: 不正形式 | 同上 | `foo` 入力 | `is-invalid` 付与、メッセージ「URL は https://example.com の形式…」 | auto | 同上 |
| T01-C055 | T01-D13 | UI: ftp スキーム | 同上 | `ftp://a.b/` 入力 | 不正扱い（送信されない） | auto | 同上 |
| T01-C056 | T01-D13 | UI: プリセット反映 | 同上 | 「広め」選択 → 解析 | 送信 body に depth=5 max_pages=300。`#discover-scope-est` に「最大 300 画面」 | auto | 同上 |
| T01-C057 | T01-D13 | UI: カスタム欄と範囲外値 | 同上 | カスタム選択、depth=99 max=9999 | 欄が表示され、送信値が 10 / 500 にクランプ | auto | 同上 |
| T01-C058 | T01-D13 | UI: サンプル URL | 同上 | `#sample-url-btn` クリック | `#url-input` に example.com | auto | 同上 |
| T01-C059 | T01-D14 | UI: 進行表示 | 同上 | M/ 「この1画面のみ」で解析 | 実行中 `#discover-loading` 表示・`#discover-elapsed` に秒表示、完了で非表示 | auto | 同上 |
| T01-C060 | T01-D14 | UI: 件数の一致 | 同上 | M/ 標準で解析 | `#p1-screens-num` = API の done.total、`#p1-login-num` = login_required 件数 | auto | 同上 |
| T01-C061 | T01-D14 | UI: 次へボタン活性 | 同上 | 解析前後で `#p1-next-btn` の可視/活性を確認 | 解析前は非表示（summary hidden）、完了後に表示・活性 | auto | 同上 |
| T01-C062 | T01-D14 | UI: URL 履歴 | 同上 | 解析完了後 `#url-history-list option` を数える | 1 件以上 | auto | 同上 |
| T01-C063 | T01-D14 | UI: 中断ボタン | 同上 | 標準で解析開始 → `#discover-cancel-btn` | `#discover-status` に「中断しました」、取得済み件数表示 | auto | 同上 |
