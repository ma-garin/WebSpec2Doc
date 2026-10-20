# WebSpec2Doc 運用手順書

本番（社内サーバ／コンテナ）で運用する担当者向け。開発手順は `DEVELOPMENT.md`、認証とテナントは `AUTH_TENANCY.md`、バックアップは `OPERATIONS_BACKUP.md` を参照。

## 1. 起動

前提: Python 3.12、`pip install -r requirements.txt`、`playwright install chromium` 済み。

```bash
# 本番（FLASK_TESTING は付けない）
WEBSPEC2DOC_TRUSTED_HOSTS=<公開ホスト名またはIP> \
WEBSPEC2DOC_SECURE_COOKIES=1 \
WEBSPEC2DOC_AUTH_MODE=required \
WEBSPEC2DOC_AUTH_MOCK=0 \
nohup venv/bin/python app.py > /var/log/webspec2doc.log 2>&1 &

curl -s http://127.0.0.1:8765/api/v1/healthz   # 死活確認（認証なしで到達可）
```

- **`FLASK_TESTING=1` は開発用。本番では付けない。** 付けるとブラウザ自動オープンが止まり、Flask が TESTING モードで動く。
- 起動時に Playwright Chromium の起動確認を行い、失敗すると終了する。
- 待ち受け: `WEBSPEC2DOC_TRUSTED_HOSTS` 未設定は `127.0.0.1` のみ。設定すると `0.0.0.0` で待ち受け、許可ホスト以外は 403 で拒否する（`web/security.py`）。TLS 終端はリバースプロキシで行う。
- ポート既定は 8765（`WEBSPEC2DOC_PORT`）。
- 内蔵サーバ（`app.run`）で動く単一プロセス構成。冗長化はしない。
- Prometheus 向けメトリクスは `/metrics`。

## 2. 環境変数

`grep -rhoE "WEBSPEC2DOC_[A-Z_]+" app.py web src | sort -u` で実在を確認した分のみ。`.env`（リポジトリ直下）にも書ける。「既定」欄が空欄の変数は、未設定時の挙動を各定義箇所で確認すること。

### 起動・認証

| 変数 | 意味 | 既定 |
|---|---|---|
| `WEBSPEC2DOC_PORT` | 待ち受けポート（`web/config.py`） | 8765 |
| `WEBSPEC2DOC_TRUSTED_HOSTS` | 追加で許可するホスト（カンマ区切り）。設定時のみ全 IF で待ち受け | 未設定（ループバックのみ） |
| `WEBSPEC2DOC_AUTH_MODE` | `auto`／`required`／`off`。`auto` はユーザー未作成の間だけ認証なし | `auto`（`TRUSTED_HOSTS` 設定時は `required`） |
| `WEBSPEC2DOC_AUTH_MOCK` | `1` でパスワードなしログイン（一覧から選択）。社内モック用 | `1`（有効。`TRUSTED_HOSTS` 設定時は `0`） |
| `WEBSPEC2DOC_BOOTSTRAP_ADMIN` | `0`／`off`／`false` で初期管理者の自動作成を止める | 有効 |
| `WEBSPEC2DOC_SECRET_KEY` | セッション署名鍵。未設定なら `instance/secret_key` を生成・利用 | 自動生成 |
| `WEBSPEC2DOC_SECURE_COOKIES` | `1` でセッション Cookie に Secure 属性。HTTPS 配下では必須 | 未設定 |
| `WEBSPEC2DOC_SESSION_HOURS` | セッション有効時間（時間） | 12 |
| `WEBSPEC2DOC_AUTH_DB` | 認証 DB のパス | `instance/auth.db` |
| `WEBSPEC2DOC_OIDC_PROVIDER` | SSO プロバイダ。設定時に OIDC を有効化 | 未設定 |
| `WEBSPEC2DOC_OIDC_CLIENT_ID` / `_CLIENT_SECRET` / `_REDIRECT_URI` | OIDC クライアント情報 | 未設定 |
| `WEBSPEC2DOC_OIDC_ISSUER` / `_TENANT` | 発行元、およびテナント（`_TENANT` 未設定は `common`） | |
| `WEBSPEC2DOC_OIDC_ALLOWED_DOMAINS` | 許可するメールドメイン（カンマ区切り） | |
| `WEBSPEC2DOC_OIDC_AUTO_PROVISION` | 初回ログイン時のユーザー自動作成 | |
| `WEBSPEC2DOC_TEMPLATES_AUTO_RELOAD` | `1` でテンプレート自動再読込（開発用） | 無効 |

### SSRF 保護・外向き通信

| 変数 | 意味 | 既定 |
|---|---|---|
| `WEBSPEC2DOC_ALLOW_LOCAL` | `1` でローカル／プライベート宛を許可（§4） | 未設定（拒否） |
| `WEBSPEC2DOC_EGRESS_POLICY` | 送信ゲートウェイのポリシー（JSON）。内部で自動設定される | |
| `WEBSPEC2DOC_ALLOW_MUTATION` | `1` でクロール中の更新系リクエスト遮断を解除 | 遮断 |
| `WEBSPEC2DOC_ALLOW_FORM_SUBMIT` | `1` でフォーム送信を許可（別途明示フラグとの二重オプトイン） | 無効 |
| `WEBSPEC2DOC_CRAWL_INTERVAL_SEC` | クロールのリクエスト間隔（秒） | |
| `WEBSPEC2DOC_BACKENDTEST_PROD_HOST_SUFFIXES` | バックエンドテストが本番扱いするホスト接尾辞（カンマ区切り） | なし |
| `WEBSPEC2DOC_DISABLE_NOTIFY` | 通知（Webhook 等）を抑止 | 無効 |
| `WEBSPEC2DOC_ALLOW_NOTIFY_IN_TEST` | テスト実行中でも通知を送る | 無効 |

### LLM・自己修復

| 変数 | 意味 |
|---|---|
| `WEBSPEC2DOC_LLM_API_KEY` | LLM の API キー（未設定時は `OPENAI_API_KEY` を参照） |
| `WEBSPEC2DOC_LLM_BASE_URL` / `_LLM_MODEL` | OpenAI 互換エンドポイント、およびモデル名（ローカル LLM 用） |
| `WEBSPEC2DOC_LLM_ACTIVITY_DIR` | LLM 利用ログの出力先 |
| `WEBSPEC2DOC_EMBED_MODEL` | 影響分析の埋め込みモデル |
| `WEBSPEC2DOC_DOCVERIFY_SEMANTIC` | 文書検証の意味比較の無効化スイッチ |
| `WEBSPEC2DOC_HEALING_MONITOR` | `1` で自己修復の監視スレッドを起動 | 
| `WEBSPEC2DOC_HEALING_ROOTS` | 自己修復が触ってよいディレクトリ（OS のパス区切り） |
| `WEBSPEC2DOC_HEALING_WORKTREE_DIR` | 自己修復の作業ツリー置き場（既定は OS の一時ディレクトリ配下） |
| `WEBSPEC2DOC_HEALING_OPENAI_MODEL` / `_OLLAMA_HOST` / `_OLLAMA_MODEL` | 自己修復で使うモデル／Ollama の接続先 |

### クロール・生成・実行の調整

| 変数 | 意味 |
|---|---|
| `WEBSPEC2DOC_DATA_DIR` | データディレクトリ（既定 `data`） |
| `WEBSPEC2DOC_STABILITY_TIMEOUT_MS` | ページ安定待ちのタイムアウト（ミリ秒） |
| `WEBSPEC2DOC_FULL_SCREENSHOT` | フルページ撮影の切替 |
| `WEBSPEC2DOC_MAX_ACTIONS_PER_PAGE` | 1 ページで探索する操作数の上限 |
| `WEBSPEC2DOC_COMPARE_DIFF_THRESHOLD` / `_TOLERANCE` | スクリーンショット差分の閾値と許容値 |
| `WEBSPEC2DOC_PW_MAX_EXEC_SEC` | Playwright 実行 subprocess の最大秒数 |
| `WEBSPEC2DOC_RECORD_HEADLESS` | `1` で操作記録をヘッドレス実行 |
| `WEBSPEC2DOC_REA_COMMAND` | リバース解析の実行コマンド |
| `WEBSPEC2DOC_STAGE_REVIEW` | 自動実行パイプラインの段階レビュー方式（既定 `review`） |
| `WEBSPEC2DOC_CLI` | CLI 経由の実行印（`src/cli.py` が自動設定。手動設定は不要） |

### 工数見積の係数

`WEBSPEC2DOC_HOURLY_RATE_YEN`（時間単価）、`WEBSPEC2DOC_MIN_PER_SCREEN`／`_MIN_PER_CONDITION`／`_MIN_PER_DIFF`／`_MIN_PER_COMPARE_SCREEN`／`_MIN_PER_UX_FINDING`（作業ごとの所要分）、`WEBSPEC2DOC_PLAN_WEIGHT_CRITICAL`／`_HIGH`／`_MEDIUM`／`_LOW`（テスト計画の重み）。レポートの削減工数・計画配分にのみ影響する。

## 3. 認証

- 既定 `auto` は、ユーザーが 1 人も居ない間は認証なしで使える。**本番は `WEBSPEC2DOC_AUTH_MODE=required` にする。**
- 初回起動時に初期管理者（ログインID `admin`／パスワード `password`）が作られる。**初回ログイン直後に変更する。** 事前に管理者を用意済みなら `WEBSPEC2DOC_BOOTSTRAP_ADMIN=0`。
- **モック認証は既定で有効（パスワードなしでユーザー一覧から選択）。本番は `WEBSPEC2DOC_AUTH_MOCK=0` を必ず設定する。** 無効にするとパスワードポリシーが強制される。
- HTTPS 配下では `WEBSPEC2DOC_SECURE_COOKIES=1`。
- 認証なしで到達できるのは `/api/v1/healthz`・ログイン関連・静的ファイルのみ。
- 認証 DB は `instance/auth.db`、署名鍵は `instance/secret_key`（権限 600）。どちらもバックアップ対象。
- テナント分離の仕様は `AUTH_TENANCY.md`。

## 4. SSRF 保護

`WEBSPEC2DOC_ALLOW_LOCAL=1` を付けない限り、次を拒否する。対象は**クロール、リンク検査、Webhook 通知**（`src/crawler/url_safety.py`、`src/diff/link_checker.py`、`web/services/notifier.py`）。

- 内部アドレス: ループバック、プライベート、リンクローカル、予約済み IP、`localhost` 系の名前、`.local`／`.localhost`／`.internal`
- 内部名に解決されるホスト: 公開名に見えても DNS 解決結果が非グローバル IP なら拒否（例: メタデータ用 169.254.169.254）
- 内部へのリダイレクト: 公開 URL から内部 URL への転送も、リダイレクト先ごとに再検証して拒否
- `http`／`https` 以外のスキーム（`file://` 等）

自動実行系の外向き通信は送信ゲートウェイ（`web/services/egress_gateway.py`）経由で、同じく名前解決後に内部宛を拒否し、実リクエスト数を計数・記録する。

運用方針: 本番サーバでは `ALLOW_LOCAL` を設定しない。社内ステージングを対象にする必要がある場合のみ、専用インスタンスで設定する。設定画面（`web/routes/settings.py`）からの切替は `.env` に書き込まれ、警告ログが残る。

## 5. バックアップ

`OPERATIONS_BACKUP.md` を参照（対象は `output/` と `instance/` を同時点で）。`instance/secret_key` と `instance/auth.db` を含む。`.env` は秘密情報保管庫へ別管理する。

## 6. ログの場所

| 内容 | 場所 |
|---|---|
| アプリログ（Flask／logging） | 標準出力・標準エラー。§1 の例ではリダイレクト先ファイル。ローテーションは運用側（logrotate 等）で行う |
| 管理監査ログ | `instance/` 配下（`OPERATIONS_BACKUP.md` 参照） |
| LLM 利用ログ | `WEBSPEC2DOC_LLM_ACTIVITY_DIR` |
| バックエンドテストの実行ログ・パージ記録 | 実行ごとのディレクトリの `<name>.log`、保管領域の `purge.log` |
| 自動実行の送信記録 | 実行ディレクトリの `egress_log.ndjson` |
| メトリクス | `/metrics`（Prometheus） |

## 7. アップグレードと切り戻し

アップグレード:

1. 実行中のクロール・スケジューラがないことを確認し、プロセスを停止する。
2. `OPERATIONS_BACKUP.md` の手順でバックアップを取り、チェックサムを検証する。
3. 現行のリビジョンを控える（`git rev-parse HEAD`）。
4. 新版を取得する（`git pull --ff-only` またはリリース成果物の展開）。
5. `venv/bin/pip install -r requirements.txt` と `venv/bin/playwright install chromium`。
6. 起動し、`/api/v1/healthz`、ログイン、既存レポートの表示を確認する。

切り戻し:

1. プロセスを停止する。
2. §7-3 で控えたリビジョンへコードを戻す（`git checkout <rev>`）。
3. `venv/bin/pip install -r requirements.txt` で依存を旧版へ戻す。
4. 新版でデータ形式が変わった疑いがある場合は、手順 2 のバックアップを `OPERATIONS_BACKUP.md` の「リストア」で戻す。**`output/` と `instance/` は必ず対で戻す。**
5. 起動して §7-6 の確認を行う。

DB マイグレーションの自動巻き戻しはない。データを戻す手段はバックアップのみ。

## 8. よくある障害と対処

| 症状 | 原因と対処 |
|---|---|
| 起動直後に終了する／Playwright のエラー | Chromium 未導入。`venv/bin/playwright install chromium` を実行。メッセージは `crawler.playwright_runtime` が出す |
| 起動してもブラウザタブが開く | 本番では想定どおり開かない（`TRUSTED_HOSTS` 設定時）。開発機でのみ開く。開発時は `FLASK_TESTING=1` |
| 社内の別端末から 403 | `WEBSPEC2DOC_TRUSTED_HOSTS` に接続元で使うホスト名／IP を追加して再起動 |
| ログインできない／毎回ログインに戻る | HTTPS なのに `SECURE_COOKIES` 未設定、または HTTP なのに `1`。`SECRET_KEY` 変更後は既存セッションが無効になる |
| ログイン画面にパスワード欄がない | モック認証が有効。`WEBSPEC2DOC_AUTH_MOCK=0` を設定 |
| 初期管理者で入れない | `BOOTSTRAP_ADMIN=0` で作成を止めていないか確認。ユーザー作成後は `auth.db` の内容が正 |
| クロールが「ローカルホスト／プライベートアドレス禁止」で失敗 | SSRF 保護どおりの動作。対象が社内ステージングなら §4 の方針に従い、専用インスタンスで `ALLOW_LOCAL=1` |
| 通知（Webhook）が届かない | 宛先が内部アドレスで拒否されている、または `DISABLE_NOTIFY` が有効。ログで `UnsafeUrlError` を確認 |
| 更新系リクエストが送られない／フォーム送信されない | 既定の安全側動作。`ALLOW_MUTATION`／`ALLOW_FORM_SUBMIT` は本番対象には設定しない |
| LLM 機能が使えない | `OPENAI_API_KEY`（または `WEBSPEC2DOC_LLM_API_KEY`）か `WEBSPEC2DOC_LLM_BASE_URL` が未設定 |
| 起動時に secret_key を書けない警告 | `instance/` が書込不可。プロセス内一時キーで動くため再起動でセッションが失効する。権限を直すか `WEBSPEC2DOC_SECRET_KEY` を設定 |
| ポート競合 | `lsof -ti:<port>` で確認。`WEBSPEC2DOC_PORT` で変更 |
| 変更したテンプレート・CSS・JS が反映されない | 再起動でのみ反映される |
