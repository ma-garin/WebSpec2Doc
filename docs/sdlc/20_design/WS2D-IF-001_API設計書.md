# WS2D-IF-001 API / インターフェース設計書

- 版数: 3.1 / 作成日: 2026-08-02 / 準拠: IPA 共通フレーム（外部設計）
- **as-built**: 本書のエンドポイント一覧は `docs/sdlc/_asbuilt/routes.json`（Flask `app.url_map` 実測、**200 本・Blueprint 26**）を正とする。旧版は `web/routes/*.py` の AST 解析による抽出で、一部 Blueprint の `url_prefix` を反映できず196本と誤集計していたため、抽出方式を url_map ベースへ修正した。
- **既存記載との差異（要修正・未対応）**: `docs/sdlc/README.md` および本書旧版（v2.0, 最終更新 2026-07-19）は「総 Blueprint 17・総エンドポイント 121」と記載している。しかし 2026-08-02 時点の実測は **Blueprint 26・エンドポイント 200** であり、一致しない。差分は `tenant_admin` / `oidc` / `api_v1_schedule` / `autorun_stages` / `autorun_report` / `llm_chat` 等、2026-07-19 以降に追加された Blueprint によるもの。**`docs/sdlc/README.md` の実測サマリ表・文書一覧の数値更新は本改訂の範囲外であり、別途対応が必要。**

## 1. API 方式

### 1.1 方式概要

- REST/JSON。同一オリジン運用（既定 `127.0.0.1:8765`）で CORS は想定しない。`web/security.py: localhost_guard` が `Host` ヘッダーを許可リスト（ローカルループバック ＋ 環境変数 `WEBSPEC2DOC_TRUSTED_HOSTS` で追加したホスト）で検査し、非許可ホストは 403 を返す。
- レスポンスは主に JSON。一部（`GET /api/v1/docs`、ダウンロード/プレビュー系、SPA ページ）は HTML またはファイルを返す。

### 1.2 認証方式（`web/auth.py`, `web/services/auth_store.py`）

- 動作モードは環境変数 `WEBSPEC2DOC_AUTH_MODE`（既定 `auto`）で切り替える。
  - `auto`: ユーザーが 1 人もいない間は認証なし（ローカル単独利用）。最初のユーザー作成後は保護対象になる。
  - `required`: 常にログイン必須。ユーザー未作成の間は `/auth/setup` のみ到達可能。
  - `off`: 認証を完全に無効化。
- 認証が有効な場合、`app.before_request(auth_guard)`（`web/__init__.py`）が全ルートに適用される。認証対象外パス: `/favicon.ico`, `/api/v1/healthz`, `/auth/login`, `/auth/logout`, `/auth/setup`, `/auth/signup`, および `/static/*`。
- 認証方式は 2 系統:
  1. **セッション Cookie**（`ws2d_session`。HttpOnly・SameSite=Lax・Secure はリクエストが HTTPS または `WEBSPEC2DOC_SECURE_COOKIES=1` のとき付与）。有効期限は既定 12 時間（`WEBSPEC2DOC_SESSION_HOURS` で変更可）。`auth_sessions` テーブルには **SHA-256 の `token_hash` のみ**保存し、生トークンは保存しない。
  2. **API トークン（Bearer）**: `/api/v1/*` 配下のみ、`Authorization: Bearer <token>` ヘッダーでセッションなしに認証可能。`api_tokens` テーブルに `token_hash`（SHA-256）で保存。スコープは `full`（全操作）／`read`（GET/HEAD/OPTIONS のみ許可。書き込み操作は 403 `forbidden_scope`）。
- 未ログイン時: 画面遷移（`Accept` が HTML、`/api` 配下以外）は `/auth/login?next=...` へ 302 リダイレクト。API 呼び出しは 401 JSON `{"error": "...", "code": "unauthorized"}`。
- テナント未選択時（ログイン済みだが所属テナント未確定）: 画面遷移は `/auth/tenant` へリダイレクト、API は 401 `{"code": "tenant_required"}`。除外パス: `/auth/user`, `/auth/tenant`, `/api/auth/me`, `/api/auth/tenants`。
- 管理者専用チェックは `require_admin()`（`web/auth.py`）を各ルートハンドラが呼び出す方式で実現されている（**デコレータではなく関数呼び出し**）。認証が無効な場合は制限しない。パターンは 2 通り確認した:
  - ブループリント単位の `@bp.before_request` が無条件または書き込みメソッド（POST/PUT/PATCH/DELETE）のときのみ `require_admin()` を呼ぶ（`admin`, `tenant_admin`, `api_v1_schedule`, `settings`, `schedule` の 5 ブループリントで確認）。
  - 個別のルート関数内で `require_admin()` を呼ぶ（`account` ブループリントの利用者/トークン管理系 6 関数で確認）。

### 1.3 テナント分離方式（`web/tenancy.py`）

- リクエストコンテキストの `g.tenant`（`auth_guard` が設定）を軸に、`scoped_output_dir()` / `scoped_instance_path()` が保存先を切り替える。
  - テナントあり: `output/tenants/{slug}/...`、`instance/tenants/{slug}/...`
  - テナントなし（ローカル単独利用・認証オフ・テスト）: 従来どおり `output/...`、`instance/...`
- `slug` は DB 値であってもパス構築の直前に `^[a-z0-9][a-z0-9-]{0,31}$` で再検証する（パストラバーサル防止）。
- 分離の実装単位は **行レベルの `tenant_id` フィルタではなく、ファイルシステムパスの切替＋ DB 接続先の切替（DB-per-tenant）** である。詳細はデータ設計書 `WS2D-DD-001` §4 を参照。

### 1.4 CSRF 対策（`web/security.py: csrf_guard`）

- 状態変更メソッド（POST/PUT/PATCH/DELETE）に対し、`Origin` ヘッダー（無ければ `Referer`）のホスト部分が自ホストと完全一致するかを検証する。不一致は 403。両方欠落する場合（curl 等の非ブラウザクライアント）は許可する。
- **トークン埋め込み方式ではなく、Origin/Referer の同一オリジン検証方式。**

### 1.5 レート制限

- コードベース全体を `rate.limit|limiter|ratelimit` で横断検索した結果、該当する実装は見つからなかった。**未実装。**

### 1.6 セキュリティヘッダー

- 全レスポンスに `add_security_headers`（`web/security.py`）が CSP・`X-Content-Type-Options`・`X-Frame-Options`・`Referrer-Policy` を付与する（`app.after_request`）。

## 2. エンドポイント一覧（Blueprint 別・全 200 本）

以下は `docs/sdlc/_asbuilt/routes.json` の機械抽出結果を Blueprint 単位でグルーピングしたもの。**概要列は routes.json の `summary` フィールドが非空ならそれを使用し、空の場合は関数名をそのまま記載する**（本改訂では全 200 本への手動要約付与は行っていない）。認証要否は §1.2 の規則と各ブループリントのソースコードを実際に確認して判定した。判定できないものは「未確認」と明記する。

### account（アプリ利用者のログイン・初期セットアップ・アカウント管理ルート。）— 23本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/api/auth/api-tokens` | `account.api_list_tokens` | api_list_tokens | ログイン必須＋管理者権限 |
| POST | `/api/auth/api-tokens` | `account.api_create_token` | api_create_token | ログイン必須＋管理者権限 |
| DELETE | `/api/auth/api-tokens/<token_id>` | `account.api_revoke_token` | api_revoke_token | ログイン必須＋管理者権限 |
| GET | `/api/auth/me` | `account.api_me` | api_me | ログイン必須（テナント未選択でも可） |
| POST | `/api/auth/password` | `account.api_change_password` | api_change_password | ログイン必須 |
| GET | `/api/auth/tenants` | `account.api_my_tenants` | ログイン中ユーザーの所属テナント一覧（テナント選択のデータ源）。 | ログイン必須（テナント未選択でも可） |
| GET | `/api/auth/users` | `account.api_list_users` | api_list_users | ログイン必須＋管理者権限 |
| POST | `/api/auth/users` | `account.api_create_user` | api_create_user | ログイン必須＋管理者権限 |
| PATCH | `/api/auth/users/<user_id>` | `account.api_update_user` | api_update_user | ログイン必須＋管理者権限 |
| GET | `/api/onboarding` | `account.api_onboarding` | api_onboarding | ログイン必須 |
| POST | `/api/onboarding/complete` | `account.api_onboarding_complete` | api_onboarding_complete | ログイン必須 |
| GET | `/auth/account` | `account.account_page` | account_page | ログイン必須 |
| GET | `/auth/login` | `account.login_page` | login_page | 不要（認証対象外） |
| POST | `/auth/login` | `account.login_submit` | login_submit | 不要（認証対象外） |
| POST | `/auth/logout` | `account.logout` | logout | 不要（認証対象外） |
| GET | `/auth/setup` | `account.setup_page` | setup_page | 不要（認証対象外） |
| POST | `/auth/setup` | `account.setup_submit` | setup_submit | 不要（認証対象外） |
| GET | `/auth/signup` | `account.signup_page` | signup_page | 不要（認証対象外） |
| POST | `/auth/signup` | `account.signup_submit` | signup_submit | 不要（認証対象外） |
| GET | `/auth/tenant` | `account.tenant_page` | tenant_page | ログイン必須（テナント未選択でも可） |
| POST | `/auth/tenant` | `account.tenant_select` | tenant_select | ログイン必須（テナント未選択でも可） |
| GET | `/auth/user` | `account.user_page` | user_page | ログイン必須（テナント未選択でも可） |
| POST | `/auth/user` | `account.user_select` | user_select | ログイン必須（テナント未選択でも可） |

### admin（）— 5本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/api/admin/audit` | `admin.get_audit` | get_audit | ログイン必須＋管理者権限 |
| GET | `/api/admin/backup-guide` | `admin.get_backup_guide` | get_backup_guide | ログイン必須＋管理者権限 |
| GET | `/api/admin/retention` | `admin.get_retention` | get_retention | ログイン必須＋管理者権限 |
| PUT | `/api/admin/retention` | `admin.put_retention` | put_retention | ログイン必須＋管理者権限 |
| GET | `/api/admin/storage` | `admin.get_storage` | get_storage | ログイン必須＋管理者権限 |

### api_v1（）— 11本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/api/v1/docs` | `api_v1.api_docs` | APIリファレンス（自己完結HTML・外部ホスト非依存）。 | ログイン必須（Bearer APIトークン可） |
| GET | `/api/v1/healthz` | `api_v1.api_healthz` | システムヘルスチェック。スケジューラー稼働状態を返す。 | 不要（認証対象外） |
| GET | `/api/v1/jobs/<job_id>` | `api_v1.api_job_status` | クロールジョブの現在の状態を返す。 | ログイン必須（Bearer APIトークン可） |
| GET | `/api/v1/openapi.json` | `api_v1.api_openapi_spec` | 実装済みエンドポイントの OpenAPI 3.0 仕様を返す。 | ログイン必須（Bearer APIトークン可） |
| GET | `/api/v1/sites` | `api_v1.api_sites` | 登録済みサイト一覧を返す。 | ログイン必須（Bearer APIトークン可） |
| POST | `/api/v1/sites/<domain>/crawl` | `api_v1.api_crawl` | 非同期クロールをトリガーする。job_id を返し、バックグラウンドで実行する。 | ログイン必須（Bearer APIトークン可） |
| GET | `/api/v1/sites/<domain>/diff` | `api_v1.api_diff` | 最新 2 スナップショットの差分を返す。 | ログイン必須（Bearer APIトークン可） |
| GET | `/api/v1/sites/<domain>/jobs` | `api_v1.api_domain_jobs` | ドメインのジョブ履歴一覧を返す（新しい順、最大20件）。 | ログイン必須（Bearer APIトークン可） |
| GET | `/api/v1/sites/<domain>/report` | `api_v1.api_report` | 指定ドメインの最新 report.json を返す。 | ログイン必須（Bearer APIトークン可） |
| GET | `/api/v1/sites/<domain>/snapshots` | `api_v1.api_snapshots` | スナップショット一覧（ファイル名・タイムスタンプ）を返す。 | ログイン必須（Bearer APIトークン可） |
| GET | `/api/v1/sites/<domain>/test-cases` | `api_v1.api_test_cases` | 最新の playwright_candidates.json のテストケース一覧を返す。 | ログイン必須（Bearer APIトークン可） |

### api_v1_schedule（/api/v1 のスケジュール・通知設定 CRUD。）— 5本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/api/v1/sites/<domain>/notifications` | `api_v1_schedule.api_v1_notifications_get` | 通知設定を返す（送信先は _public_config の方針に従う）。 | ログイン必須（Bearer APIトークン可） |
| PUT | `/api/v1/sites/<domain>/notifications` | `api_v1_schedule.api_v1_notifications_put` | 通知設定のみを更新する（スケジュール間隔などは変更しない）。 | ログイン必須＋管理者権限 |
| DELETE | `/api/v1/sites/<domain>/schedule` | `api_v1_schedule.api_v1_schedule_delete` | 定期クロール設定を削除する。存在しない場合も 404 にはしない（冪等）。 | ログイン必須＋管理者権限 |
| GET | `/api/v1/sites/<domain>/schedule` | `api_v1_schedule.api_v1_schedule_get` | 定期クロール設定を返す。未設定なら既定値を返す。 | ログイン必須（Bearer APIトークン可） |
| PUT | `/api/v1/sites/<domain>/schedule` | `api_v1_schedule.api_v1_schedule_put` | 定期クロール設定を作成・更新する。 | ログイン必須＋管理者権限 |

### auto_run（）— 10本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| POST | `/api/autorun/approve` | `auto_run.api_autorun_approve` | api_autorun_approve | ログイン必須 |
| POST | `/api/autorun/cancel` | `auto_run.api_autorun_cancel` | api_autorun_cancel | ログイン必須 |
| GET | `/api/autorun/jobs` | `auto_run.api_autorun_jobs` | api_autorun_jobs | ログイン必須 |
| GET | `/api/autorun/live-screenshot` | `auto_run.api_autorun_live_screenshot` | テスト実行中の最新スクリーンショットを返す（screenshot:'on' 設定済みの | ログイン必須 |
| GET | `/api/autorun/preview` | `auto_run.api_autorun_preview` | テストケース一覧・スクリプト内容・フィルター件数を返す。 | ログイン必須 |
| GET | `/api/autorun/report` | `auto_run.api_autorun_report` | api_autorun_report | ログイン必須 |
| POST | `/api/autorun/start` | `auto_run.api_autorun_start` | api_autorun_start | ログイン必須 |
| GET | `/api/autorun/status` | `auto_run.api_autorun_status` | api_autorun_status | ログイン必須 |
| POST | `/api/autorun/submit-input` | `auto_run.api_autorun_submit_input` | ログイン情報などの人的インプットを受け取り、待機中のジョブを再開する。 | ログイン必須 |
| GET | `/api/history/runs` | `auto_run.api_history_runs` | 種別を問わない一般化された実行履歴（R2-27）。 | ログイン必須 |

### autorun_report（AutoRun 実行結果レポート専用ページ（仕様15〜17）。）— 2本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/api/autorun/report/<domain>` | `autorun_report.api_autorun_report` | レポートのセクション内容を返す。 | ログイン必須 |
| GET | `/autorun/report/<domain>` | `autorun_report.autorun_report_page` | 実行結果レポートの専用ページ（仕様16）。 | ログイン必須 |

### autorun_stages（AutoRun 段階承認パイプラインの API（仕様7〜13）。）— 14本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/api/autorun/decisions` | `autorun_stages.api_decisions` | 実行条件の質問を返す。 | ログイン必須 |
| POST | `/api/autorun/decisions` | `autorun_stages.api_submit_decisions` | 実行条件を確定し、全段階を承認して後続へ進む。 | ログイン必須 |
| GET | `/api/autorun/review-queue` | `autorun_stages.api_review_queue` | 要確認キューを返す。 | ログイン必須 |
| POST | `/api/autorun/review-queue/auto-approve` | `autorun_stages.api_auto_approve` | 自動承認の対象（実測 × 低〜中リスク）をまとめて承認する。 | ログイン必須 |
| GET | `/api/autorun/stages` | `autorun_stages.api_stages` | 段階の一覧と現在地を返す。 | ログイン必須 |
| POST | `/api/autorun/stages/adopt` | `autorun_stages.api_adopt_suggestion` | LLM の提案を項目として採用する。出所は llm として残す。 | ログイン必須 |
| POST | `/api/autorun/stages/approve` | `autorun_stages.api_approve_stage` | 段階を承認する。項目承認が必要な段階では全項目の承認を要求する。 | ログイン必須 |
| POST | `/api/autorun/stages/generate` | `autorun_stages.api_generate_stage` | 指定段階の内容を生成する（ルールベース）。 | ログイン必須 |
| POST | `/api/autorun/stages/item` | `autorun_stages.api_update_item` | 項目の承認状態・内容を更新する。 | ログイン必須 |
| POST | `/api/autorun/stages/proceed` | `autorun_stages.api_proceed` | 段階承認を終えて、後続（Playwright化・実行）へ進む。 | ログイン必須 |
| POST | `/api/autorun/stages/reset` | `autorun_stages.api_reset_stages` | 段階状態を初期化する（作り直し）。 | ログイン必須 |
| POST | `/api/autorun/stages/skip` | `autorun_stages.api_skip_stage` | 2回目以降のみ、スキップ可能な段階を飛ばす（仕様8）。 | ログイン必須 |
| POST | `/api/autorun/stages/suggest` | `autorun_stages.api_suggest` | 段階に対する追加候補を LLM に問い合わせる（補助）。 | ログイン必須 |
| GET | `/api/autorun/stages/testcases` | `autorun_stages.api_test_cases` | テストケースを QualityForward のカラム構成で返す（表 / CSV）。 | ログイン必須 |

### crawl（）— 5本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| POST | `/api/cancel` | `crawl.api_cancel` | api_cancel | ログイン必須 |
| GET | `/api/doc-fusion` | `crawl.api_doc_fusion` | output/{domain}/doc_fusion.json をそのまま返す（無ければ 404）。 | ログイン必須 |
| GET | `/api/live-screenshot` | `crawl.live_screenshot` | live_screenshot | ログイン必須 |
| POST | `/api/reference-docs` | `crawl.upload_reference_docs` | 参考文書のアップロード（multipart）。output/{domain}/reference_docs/ へ保存する。 | ログイン必須 |
| POST | `/run` | `crawl.run` | run | ログイン必須 |

### discover（）— 2本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| POST | `/api/discover` | `discover.api_discover` | api_discover | ログイン必須 |
| POST | `/api/discover-stream` | `discover.api_discover_stream` | 発見ページを SSE（text/event-stream）でリアルタイム配信する。 | ログイン必須 |

### history（）— 7本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/api/history` | `history.api_history` | api_history | ログイン必須 |
| DELETE | `/api/site/<domain>` | `history.api_delete_site` | api_delete_site | ログイン必須 |
| GET | `/api/snapshot-comparison` | `history.api_snapshot_comparison` | 2つのスナップショット間を「現新比較（4分類）」でHTML化して返す。 | ログイン必須 |
| GET | `/api/snapshot-comparison.json` | `history.api_snapshot_comparison_json` | 現新比較をペア単位の JSON で返す（現新比較ワークスペース用）。 | ログイン必須 |
| GET | `/api/snapshot-diff` | `history.api_snapshot_diff` | 2つのスナップショット間の仕様ドリフト差分をHTMLで返す。 | ログイン必須 |
| GET | `/api/snapshot-diff-summary` | `history.api_snapshot_diff_summary` | 2 時点間に仕様の変更があったかを JSON で返す（P2-1）。 | ログイン必須 |
| GET | `/api/snapshots` | `history.api_snapshots` | サイトのクロール履歴（スナップショット）一覧。新しい順。 | ログイン必須 |

### llm_chat（QA アシスタント（LLM チャット）の API。）— 1本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| POST | `/api/llm/chat` | `llm_chat.api_llm_chat` | QA アシスタントへの相談。 | ログイン必須 |

### login（）— 7本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| POST | `/api/login/record/cancel` | `login.api_login_record_cancel` | 保存前にレコーダーを中断する（PID を直接 terminate。状態はファイルで共有するため | ログイン必須 |
| POST | `/api/login/record/complete` | `login.api_login_record_complete` | 「ログイン完了」ボタン。シグナルファイルを作成し、レコーダーに保存を指示する。 | ログイン必須 |
| POST | `/api/login/record/start` | `login.api_login_record_start` | 認証フローレコーダーを起動する。ブラウザは非ブロッキングで起動し、 | ログイン必須 |
| GET | `/api/login/record/status` | `login.api_login_record_status` | レコーダーの進行状態をポーリングする（1秒間隔想定）。 | ログイン必須 |
| POST | `/api/login/scrape` | `login.api_login_scrape` | ログインページのフォームフィールドを動的スクレイプする（ADR-0002）。 | ログイン必須 |
| POST | `/api/login/simple` | `login.api_login_simple` | IDとパスワードをtype属性ベースで自動マッピングしてログインする（シンプルフロー）。 | ログイン必須 |
| POST | `/api/login/submit` | `login.api_login_submit` | ログインフォームを自動送信してセッションを保存する（ADR-0002）。 | ログイン必須 |

### metrics（Prometheus のスクレイプ先 `/metrics`。）— 1本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/metrics` | `metrics.metrics` | Prometheus 形式のメトリクスを返す。 | ログイン必須 |

### oidc（SSO（OIDC）のログイン開始とコールバック。）— 2本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/auth/oidc/callback` | `oidc.oidc_callback` | IdP からの戻り。state 照合 → トークン交換 → 利用者解決 → セッション発行。 | ログイン必須 |
| GET | `/auth/oidc/login` | `oidc.oidc_login` | IdP の認可画面へ送る。 | ログイン必須 |

### pages（）— 5本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/` | `pages.index` | index | ログイン必須 |
| GET | `/<view_name>` | `pages.view` | view | ログイン必須 |
| GET | `/cli` | `pages.cli_mode` | CLI モード（System 03）の案内。 | ログイン必須 |
| GET | `/settings/<tab>` | `pages.settings_tab` | 設定画面をタブ指定で開く（例: /settings/api）。 | ログイン必須 |
| GET | `/systems` | `pages.systems` | ログイン後のシステム選択ハブ。ドキュメント作成 / AutoRun / CLI モードを選ぶ。 | ログイン必須 |

### qa_process（）— 17本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/api/qa-process/advanced` | `qa_process.api_qa_process_advanced` | api_qa_process_advanced | ログイン必須 |
| POST | `/api/qa-process/generate` | `qa_process.api_qa_process_generate` | api_qa_process_generate | ログイン必須 |
| POST | `/api/qa-process/generate-advanced` | `qa_process.api_qa_process_generate_advanced` | api_qa_process_generate_advanced | ログイン必須 |
| GET | `/api/qa-process/input` | `qa_process.api_qa_process_input` | api_qa_process_input | ログイン必須 |
| GET | `/api/qa-process/result` | `qa_process.api_qa_process_result` | api_qa_process_result | ログイン必須 |
| GET | `/api/test-design` | `qa_process.api_test_design` | MBT テスト設計（BVA/DT/PW/ST）を画面ごとに生成して JSON で返す。 | ログイン必須 |
| GET | `/api/test-design/by-screen` | `qa_process.api_test_design_by_screen` | 画面別テスト設計。page_id 省略で画面リスト、指定でその画面の条件一覧を返す。 | ログイン必須 |
| GET | `/api/testcases` | `qa_process.api_testcases` | api_testcases | ログイン必須 |
| POST | `/api/testcases/cell` | `qa_process.api_testcases_cell` | 1 セルを更新する。value は文字列、または list 列なら配列。 | ログイン必須 |
| POST | `/api/testcases/cell/reset` | `qa_process.api_testcases_cell_reset` | api_testcases_cell_reset | ログイン必須 |
| GET | `/api/testcases/count` | `qa_process.api_testcases_count` | テストケース件数だけを返す。 | ログイン必須 |
| GET | `/api/testcases/history` | `qa_process.api_testcases_history` | api_testcases_history | ログイン必須 |
| GET | `/api/testcases/live-progress` | `qa_process.api_testcases_live_progress` | 実行中のテスト進捗を返す。実行完了を待たずに、その時点までの結果を読む。 | ログイン必須 |
| GET | `/api/testcases/live-screenshot` | `qa_process.api_testcases_live_screenshot` | 実行中の最新スクリーンショットを返す（config の screenshot:'on' が | ログイン必須 |
| POST | `/api/testcases/row` | `qa_process.api_testcases_row` | 行の追加・削除・復元。action で切り替える。 | ログイン必須 |
| POST | `/api/testcases/run` | `qa_process.api_testcases_run` | テストケース表から Playwright spec を生成し、その場で実行して結果を保存する。 | ログイン必須 |
| GET | `/api/testcases/table` | `qa_process.api_testcases_table` | 9 列のローレベルテストケース表（生成値＋ユーザー編集）を返す。 | ログイン必須 |

### report（）— 10本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/api/coverage-heatmap` | `report.api_coverage_heatmap` | カバレッジヒートマップ（kind=analysis: 取得状況3色 / kind=autorun: 実行回数×成否）をHTMLで返す。 | ログイン必須 |
| GET | `/api/export/spec-xlsx` | `report.export_spec_xlsx` | テスト仕様書一式（7 シート）の Excel を返す（P2-3）。 | ログイン必須 |
| GET | `/api/report/<domain>/spec-ts` | `report.download_spec_ts` | download_spec_ts | ログイン必須 |
| GET | `/api/result` | `report.api_result` | 結果ページのデータ源。 | ログイン必須 |
| POST | `/api/sample-report` | `report.api_sample_report` | 同梱のサンプルレポートを自テナントの出力先へ展開し、開くドメインを返す（P3-1）。 | ログイン必須 |
| GET | `/api/state-table` | `report.api_state_table` | 状態遷移表（ISTQB 状態遷移テスト）を report.json から導出して返す。 | ログイン必須 |
| GET | `/download` | `report.download` | download | ログイン必須 |
| GET | `/download-zip` | `report.download_zip` | ドメイン配下をZIP化する。`paths`（複数値・カンマ区切りいずれも可）を指定した場合は | ログイン必須 |
| GET | `/open` | `report.open_file` | open_file | ログイン必須 |
| GET | `/preview` | `report.preview` | preview | ログイン必須 |

### review（）— 3本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/review/cases` | `review.api_review_cases` | api_review_cases | ログイン必須 |
| GET | `/review/export` | `review.api_review_export` | api_review_export | ログイン必須 |
| POST | `/review/update` | `review.api_review_update` | api_review_update | ログイン必須 |

### runs（実行回ごとの成果物を返すルート（案A: 実行結果ページ = 実行回のハブ）。）— 5本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/api/runs/<domain>` | `runs.api_runs` | そのサイトの実行回一覧（新しい順）。実行回セレクタが使う。 | ログイン必須 |
| GET | `/api/runs/<domain>/<run_id>` | `runs.api_run_detail` | 1 実行回の中身。3 つの成果物の有無とファイルパスを返す。 | ログイン必須 |
| GET | `/api/runs/<domain>/<run_id>/artifact` | `runs.api_run_artifact` | 実行回の成果物ファイルの実パスを返す（/preview で開くために使う）。 | ログイン必須 |
| GET | `/api/runs/<domain>/<run_id>/exists` | `runs.api_run_exists` | 実行回の成果物があるかだけを返す（一覧の行が導線を出すかの判断用）。 | ログイン必須 |
| GET | `/runs/<domain>/<run_id>` | `runs.run_page` | 実行結果ページ（実行回のハブ）。実体の描画はクライアント側が行う。 | ログイン必須 |

### schedule（）— 6本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/schedule/config` | `schedule.api_schedule_config_get` | api_schedule_config_get | ログイン必須 |
| POST | `/schedule/config` | `schedule.api_schedule_config_post` | api_schedule_config_post | ログイン必須＋管理者権限 |
| GET | `/schedule/history` | `schedule.api_schedule_history` | api_schedule_history | ログイン必須 |
| POST | `/schedule/notify/test` | `schedule.api_schedule_notify_test` | api_schedule_notify_test | ログイン必須＋管理者権限 |
| POST | `/schedule/run-now` | `schedule.api_schedule_run_now` | api_schedule_run_now | ログイン必須＋管理者権限 |
| GET | `/schedule/status` | `schedule.api_schedule_status` | api_schedule_status | ログイン必須 |

### settings（）— 8本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/api/settings` | `settings.get_settings` | get_settings | ログイン必須 |
| POST | `/api/settings` | `settings.post_settings` | post_settings | ログイン必須＋管理者権限 |
| GET | `/api/settings/allow-local` | `settings.get_allow_local` | get_allow_local | ログイン必須 |
| POST | `/api/settings/allow-local` | `settings.post_allow_local` | post_allow_local | ログイン必須＋管理者権限 |
| GET | `/api/settings/llm-models` | `settings.list_llm_models` | ローカル LLM サーバ（Ollama 等）が提供するモデル一覧を返す。 | ログイン必須 |
| POST | `/api/settings/test-connection` | `settings.post_test_connection` | post_test_connection | ログイン必須＋管理者権限 |
| GET | `/api/settings/test-design` | `settings.get_test_design` | get_test_design | ログイン必須 |
| POST | `/api/settings/test-design` | `settings.post_test_design` | post_test_design | ログイン必須＋管理者権限 |

### site（）— 1本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/api/site` | `site.api_site` | api_site | ログイン必須 |

### tenant_admin（テナントとユーザーの管理画面（管理者専用）。）— 9本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/admin/console` | `tenant_admin.console_page` | console_page | ログイン必須（管理者以外は画面側でリダイレクト） |
| GET | `/api/admin/tenancy` | `tenant_admin.api_snapshot` | api_snapshot | ログイン必須＋管理者権限 |
| POST | `/api/admin/tenancy/tenants` | `tenant_admin.api_create_tenant` | api_create_tenant | ログイン必須＋管理者権限 |
| DELETE | `/api/admin/tenancy/tenants/<tenant_id>` | `tenant_admin.api_delete_tenant` | api_delete_tenant | ログイン必須＋管理者権限 |
| PATCH | `/api/admin/tenancy/tenants/<tenant_id>` | `tenant_admin.api_rename_tenant` | api_rename_tenant | ログイン必須＋管理者権限 |
| POST | `/api/admin/tenancy/users` | `tenant_admin.api_create_user` | api_create_user | ログイン必須＋管理者権限 |
| DELETE | `/api/admin/tenancy/users/<user_id>` | `tenant_admin.api_delete_user` | api_delete_user | ログイン必須＋管理者権限 |
| PATCH | `/api/admin/tenancy/users/<user_id>` | `tenant_admin.api_update_user` | アカウントの有効/無効化（全テナントに効く）。 | ログイン必須＋管理者権限 |
| PUT | `/api/admin/tenancy/users/<user_id>/memberships` | `tenant_admin.api_set_memberships` | api_set_memberships | ログイン必須＋管理者権限 |

### traceability（）— 2本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/traceability/matrix` | `traceability.api_traceability_matrix` | report.json + playwright_candidates.json を読んで TraceabilityMatrix を返す。 | ログイン必須 |
| GET | `/traceability/view` | `traceability.view_traceability` | トレーサビリティマトリクスビューをレンダリングする。 | ログイン必須 |

### usage（ROI ダッシュボード: 利用実績と推定削減工数を表示する。）— 2本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| GET | `/api/usage` | `usage.api_usage` | 累計利用実績と推定削減工数（ROI）を返す。 | ログイン必須 |
| GET | `/usage` | `usage.view_usage` | ROI ダッシュボードビューをレンダリングする。 | ログイン必須 |

### viewpoints（）— 37本

| メソッド | パス | エンドポイント名 | 概要 | 認証要否 |
|---|---|---|---|---|
| DELETE | `/api/viewpoint-assignments/<assignment_id>` | `viewpoints.api_delete_viewpoint_assignment` | api_delete_viewpoint_assignment | ログイン必須 |
| PATCH | `/api/viewpoint-assignments/<assignment_id>` | `viewpoints.api_update_viewpoint_assignment` | api_update_viewpoint_assignment | ログイン必須 |
| DELETE | `/api/viewpoint-folders/<item_id>` | `viewpoints.api_delete_viewpoint_folder` | api_delete_viewpoint_folder | ログイン必須 |
| DELETE | `/api/viewpoint-items/<item_id>` | `viewpoints.api_delete_viewpoint_item` | api_delete_viewpoint_item | ログイン必須 |
| PATCH | `/api/viewpoint-items/<item_id>` | `viewpoints.api_update_viewpoint_item` | api_update_viewpoint_item | ログイン必須 |
| PATCH | `/api/viewpoint-items/<item_id>/move` | `viewpoints.api_move_viewpoint_item` | api_move_viewpoint_item | ログイン必須 |
| POST | `/api/viewpoint-items/<item_id>/restore` | `viewpoints.api_restore_viewpoint_item` | api_restore_viewpoint_item | ログイン必須 |
| POST | `/api/viewpoint-items/bulk` | `viewpoints.api_bulk_update_viewpoint_items` | api_bulk_update_viewpoint_items | ログイン必須 |
| POST | `/api/viewpoint-proposals/<proposal_id>/decision` | `viewpoints.api_decide_viewpoint_proposal` | api_decide_viewpoint_proposal | ログイン必須 |
| GET | `/api/viewpoint-selection` | `viewpoints.api_viewpoint_selection` | api_viewpoint_selection | ログイン必須 |
| GET | `/api/viewpoint-sets` | `viewpoints.api_viewpoint_sets` | api_viewpoint_sets | ログイン必須 |
| POST | `/api/viewpoint-sets` | `viewpoints.api_create_viewpoint_set` | api_create_viewpoint_set | ログイン必須 |
| DELETE | `/api/viewpoint-sets/<set_id>` | `viewpoints.api_delete_viewpoint_set` | api_delete_viewpoint_set | ログイン必須 |
| GET | `/api/viewpoint-sets/<set_id>` | `viewpoints.api_get_viewpoint_set` | api_get_viewpoint_set | ログイン必須 |
| PATCH | `/api/viewpoint-sets/<set_id>` | `viewpoints.api_update_viewpoint_set` | api_update_viewpoint_set | ログイン必須 |
| GET | `/api/viewpoint-sets/<set_id>/assignments` | `viewpoints.api_viewpoint_assignments` | api_viewpoint_assignments | ログイン必須 |
| POST | `/api/viewpoint-sets/<set_id>/assignments` | `viewpoints.api_create_viewpoint_assignment` | api_create_viewpoint_assignment | ログイン必須 |
| GET | `/api/viewpoint-sets/<set_id>/export` | `viewpoints.api_export_viewpoint_set` | api_export_viewpoint_set | ログイン必須 |
| POST | `/api/viewpoint-sets/<set_id>/folders` | `viewpoints.api_create_viewpoint_folder` | api_create_viewpoint_folder | ログイン必須 |
| POST | `/api/viewpoint-sets/<set_id>/import` | `viewpoints.api_import_viewpoint_set` | api_import_viewpoint_set | ログイン必須 |
| PATCH | `/api/viewpoint-sets/<set_id>/items/reorder` | `viewpoints.api_reorder_viewpoint_items` | api_reorder_viewpoint_items | ログイン必須 |
| GET | `/api/viewpoint-sets/<set_id>/proposals` | `viewpoints.api_viewpoint_proposals` | api_viewpoint_proposals | ログイン必須 |
| POST | `/api/viewpoint-sets/<set_id>/proposals` | `viewpoints.api_generate_viewpoint_proposals` | api_generate_viewpoint_proposals | ログイン必須 |
| POST | `/api/viewpoint-sets/<set_id>/restore` | `viewpoints.api_restore_viewpoint_set` | api_restore_viewpoint_set | ログイン必須 |
| POST | `/api/viewpoint-sets/<set_id>/templates/<template_key>/apply` | `viewpoints.api_apply_viewpoint_template` | api_apply_viewpoint_template | ログイン必須 |
| GET | `/api/viewpoint-sets/<set_id>/tree` | `viewpoints.api_viewpoint_tree` | api_viewpoint_tree | ログイン必須 |
| GET | `/api/viewpoint-sets/<set_id>/versions` | `viewpoints.api_viewpoint_versions` | api_viewpoint_versions | ログイン必須 |
| POST | `/api/viewpoint-sets/<set_id>/versions` | `viewpoints.api_create_viewpoint_draft` | api_create_viewpoint_draft | ログイン必須 |
| GET | `/api/viewpoint-sets/<set_id>/versions/<int:version>/items` | `viewpoints.api_viewpoint_items` | api_viewpoint_items | ログイン必須 |
| POST | `/api/viewpoint-sets/<set_id>/versions/<int:version>/items` | `viewpoints.api_create_viewpoint_item` | api_create_viewpoint_item | ログイン必須 |
| POST | `/api/viewpoint-sets/<set_id>/versions/<int:version>/publish` | `viewpoints.api_publish_viewpoint_version` | api_publish_viewpoint_version | ログイン必須 |
| POST | `/api/viewpoint-sets/<set_id>/versions/<int:version>/rollback` | `viewpoints.api_rollback_viewpoint_version` | api_rollback_viewpoint_version | ログイン必須 |
| GET | `/api/viewpoint-sets/<set_id>/versions/diff` | `viewpoints.api_diff_viewpoint_versions` | api_diff_viewpoint_versions | ログイン必須 |
| GET | `/api/viewpoint-sources` | `viewpoints.api_viewpoint_sources` | 観点の根拠となる規格・ガイドラインの出典一覧。 | ログイン必須 |
| GET | `/api/viewpoint-sources/resolve` | `viewpoints.api_resolve_viewpoint_source` | standards 文字列から出典を引く。該当が無ければ source は null。 | ログイン必須 |
| GET | `/api/viewpoint-templates` | `viewpoints.api_viewpoint_templates` | api_viewpoint_templates | ログイン必須 |
| POST | `/api/viewpoint-templates/<template_key>/create-set` | `viewpoints.api_create_set_from_template` | テンプレートから観点セットを新規作成する。 | ログイン必須 |


## 3. 主要API詳細仕様

業務上重要な 14 本について、実装（`web/routes/*.py`）を読んだ上でのリクエスト/レスポンス/エラー仕様を示す。

### 3.1 POST /auth/login（`account.login_submit`）

- 認証要否: 不要（認証対象外パス）
- リクエスト: `application/x-www-form-urlencoded` — `email`（string, 必須）, `password`（string, 任意）
- 処理: モック認証有効かつ `password` が空なら `authenticate_passwordless(email)`、それ以外は `authenticate(email, password)`。
- レスポンス（成功）: 302 リダイレクト。モック認証時は `/auth/user`、通常時は `/auth/tenant`。
- エラー: 認証失敗時は HTTP 401 で `auth/login.html` をエラーメッセージ付きで再描画（JSON ではなく HTML）。

### 3.2 POST /api/auth/api-tokens（`account.api_create_token`）

- 認証要否: ログイン必須＋管理者権限
- リクエスト: JSON `{"name": string}`
- レスポンス（成功 200）: `{"ok": true, "token": {...}}`（`AuthStore.create_api_token` の戻り値）
- エラー: `AuthError` 捕捉時 400 `{"error": "...", "code": "..."}`

### 3.3 POST /api/auth/password（`account.api_change_password`）

- 認証要否: ログイン必須
- リクエスト: JSON `{"current": string, "new": string}`
- レスポンス（成功 200）: `{"ok": true, "relogin": true}`（パスワード変更後は全セッション失効するため再ログインを要求）
- エラー: `AuthError` 捕捉時 400 `{"error": "...", "code": "..."}`

### 3.4 GET /api/v1/healthz（`api_v1.api_healthz`）

- 認証要否: 不要（認証対象外パス）
- レスポンス（200）: `{"status": "ok", "scheduler": {"running": bool}, "viewpoints_db": "<ファイル名のみ>", "version": "1.0"}`

### 3.5 GET /api/v1/sites（`api_v1.api_sites`）

- 認証要否: ログイン必須（Bearer API トークン可）
- レスポンス（成功 200）: `{"sites": [...]}`（`registry.site_registry.list_sites` の一覧）
- エラー: 内部例外捕捉時 500 `{"error": "内部エラーが発生しました。ログを確認してください。"}`

### 3.6 GET /api/v1/sites/<domain>/report（`api_v1.api_report`）

- パスパラメータ: `domain`（string, 必須。`_valid_domain` で書式検証）
- レスポンス（成功 200）: `output/{domain}/report.json` の内容をそのまま返す
- エラー: 不正 domain 400 / report.json 不在 404 `{"error": "report not found"}` / 読込失敗 500

### 3.7 GET /api/v1/sites/<domain>/diff（`api_v1.api_diff`）

- レスポンス（成功 200）: 直近 2 スナップショットの差分（`compute_diff` の dataclass を dict 化）
- エラー: スナップショット 2 件未満 404 `{"error": "need at least 2 snapshots"}`

### 3.8 POST /api/v1/sites/<domain>/crawl（`api_v1.api_crawl`）

- リクエスト: JSON — `url`（string, 任意。無ければ `site.json` から補完）, `depth`（int, 既定 2, `MAX_DEPTH` まで）, `max_pages`（int, 既定 30, `MAX_PAGES_LIMIT` まで）, `compare`（bool, 既定 true）
- 処理: `start_crawl_job` で非同期ジョブを開始（バックグラウンド実行）
- レスポンス（202 Accepted）: `{"job_id": string, "status": "queued", "domain": string}`
- エラー: `url` 未指定・不正 URL は 400 `{"error": "..."}`

### 3.9 GET /api/v1/jobs/<job_id>（`api_v1.api_job_status`）

- レスポンス（成功 200）: ジョブの現在状態（dataclass を dict 化）
- エラー: 404 `{"error": "job not found"}`

### 3.10 GET/PUT /api/v1/sites/<domain>/schedule（`api_v1_schedule`）

- 認証要否: GET は ログイン必須（Bearer 可）、PUT は ログイン必須＋管理者権限（`_admin_guard` が書き込み系メソッドのみ管理者を要求）
- GET レスポンス（200）: `{"schedule": {...}}`（未設定時は既定値）
- PUT リクエスト: JSON ボディ（`_validated_schedule` で検証。検証エラーは 400 `{"error": "<メッセージ>"}`）
- PUT 成功時: 監査ログ `record_admin_event(action="schedule.updated", ...)` を記録し `{"schedule": {...}}` を返す

### 3.11 POST /api/viewpoint-sets/<set_id>/versions/<version>/publish（`viewpoints.api_publish_viewpoint_version`）

- パスパラメータ: `set_id`（string）, `version`（int）
- リクエスト: JSON `{"revision": any(任意), "change_reason": string(任意)}`
- レスポンス（成功 200）: `{"version": {...公開後のバージョン...}}`

### 3.12 POST /api/viewpoint-sets/<set_id>/proposals（`viewpoints.api_generate_viewpoint_proposals`）

- 処理: OpenAI API キー未設定なら 503 `{"error": "OpenAI設定がないためAI提案は利用できません。"}` を即返却。設定済みなら `generate_viewpoint_proposals` を実行。
- エラー: `OpenAIQAError` 捕捉時 502 `{"error": "<メッセージ>"}`
- 成功時（200）: `{"proposals": [...]}`

### 3.13 POST /api/admin/tenancy/tenants（`tenant_admin.api_create_tenant`）

- 認証要否: ログイン必須＋管理者権限（`_guard` が `console_page` 以外の全 API に適用）
- リクエスト: JSON `{"name": string, "slug": string(任意)}`
- レスポンス（成功 200）: `{"ok": true, "tenant": {...}, ...テナント一覧スナップショット}`
- エラー: `AuthError` 捕捉時 400 `{"error": "...", "code": "..."}`

### 3.14 GET /auth/oidc/login・GET /auth/oidc/callback（`oidc.oidc_login` / `oidc.oidc_callback`）

- 認証要否: ログイン必須（`web/auth.py` の認証除外パス一覧に `/auth/oidc/login` `/auth/oidc/callback` は含まれていないことをソースで確認済み。したがって未ログイン状態でアクセスすると `auth_guard` が先に `/auth/login` へリダイレクトする。SSO単独でのログイン開始を許すには、この2パスを認証除外パスへ追加する実装変更が別途必要と考えられる。`WEBSPEC2DOC_OIDC_PROVIDER` 未設定時はそもそも `oidc_enabled()` が false を返し機能自体が無効化される）
- 処理フロー: login → state/nonce を生成しセッションへ保存 → IdP 認可エンドポイントへ 302。callback → state 照合（`secrets.compare_digest` による定数時間比較）→ 認可コード交換（`requests.post`、client_secret 使用）→ ID トークンを IdP の JWKS で署名検証（`authlib.jose`）→ userinfo 取得 → メールアドレスが一致する **既存**ユーザーのみセッション発行（自動プロビジョニングなし）。
- エラー時: 各段階の失敗は `/auth/login?sso_error=<message>` へリダイレクト（セッションは発行されない）。未登録メールは「このアカウントは登録されていません」で拒否。

## 4. 共通仕様

### 4.1 HTTP ステータスコード方針

| コード | 意味 |
|---|---|
| 200 | 成功 |
| 201 | 作成成功 |
| 202 | 非同期受理（例: クロール開始） |
| 400 | リクエスト不正（バリデーションエラー） |
| 401 | 未認証 |
| 403 | 権限不足・CSRF 拒否・API トークンのスコープ不足・Host 不一致 |
| 404 | 対象なし |
| 500 | 内部エラー |
| 502 | 外部連携（OpenAI 等）呼び出し失敗 |
| 503 | 外部連携が未設定（例: OpenAI API キー未設定） |

### 4.2 エラーレスポンス共通スキーマ

```json
{"error": "利用者向けメッセージ", "code": "機械可読コード"}
```

`code` の例: `unauthorized`, `forbidden`, `forbidden_scope`, `tenant_required`, `not_member`, `invalid_request` など（`web/auth.py` のヘルパーおよび `web/services/auth_store.py: AuthError` が発生源）。全エンドポイントが厳密にこのスキーマに従うかは個別確認できておらず、一部（HTML 再描画系・ファイルダウンロード系）は対象外。

### 4.3 ページネーション

- 汎用的なページネーション機構（limit/offset・カーソル）は確認されなかった。一部 API（例: `api_domain_jobs` はジョブ履歴を新しい順で最大 20 件）は固定件数上限で対応している。

### 4.4 日時フォーマット

- ISO 8601 文字列（`auth_store._iso()` 等）。DB には `TEXT` 型で保存する。

### 4.5 文字コード

- UTF-8 固定（ソース全体で `encoding="utf-8"` を明示）。

## 5. 外部連携I/F

| 連携先 | 用途 | 通信方向 | I/F | 認証 | 失敗時の挙動 |
|---|---|---|---|---|---|
| OpenAI API | QA 自動生成・接続確認（`web/services/openai_qa.py`） | WebSpec2Doc → OpenAI | `POST https://api.openai.com/v1/responses`（`urllib.request`, timeout 90s）／`GET https://api.openai.com/v1/models`（接続確認, timeout 10s） | API キー（管理者が `/api/settings` で設定した `OPENAI_API_KEY`） | `HTTPError`/`URLError`/timeout 等を捕捉し `OpenAIQAError` 等の利用者向けメッセージへ変換。呼び出し元 API は 502/503 を返す |
| Ollama（ローカル LLM） | QA 生成のローカル代替（OpenAI 互換 API、`web/routes/settings.py`） | WebSpec2Doc → ローカルホスト（既定 `http://127.0.0.1:11434/v1`、モデル既定 `qwen2.5:3b`） | `GET {base_url}/models`（timeout 3s） | なし（ローカル限定。`_is_local_base_url` で外部 URL 指定を拒否し SSRF を防止） | 接続失敗時は `urllib.error.URLError`/`OSError`/timeout 等を捕捉しモデル一覧取得エラーを返す |
| OIDC（SSO） | Microsoft Entra ID / Google Workspace でのログイン（`web/routes/oidc.py`, `web/services/oidc.py`） | WebSpec2Doc → IdP | `GET /auth/oidc/login` → IdP 認可エンドポイント、`GET /auth/oidc/callback` ← IdP。内部で `POST {token_endpoint}`・`GET {userinfo_endpoint}`・`GET {issuer}/.well-known/openid-configuration`・JWKS 取得（`requests`, timeout 15s） | `client_id`/`client_secret`（環境変数）＋ state/nonce ＋ ID トークン署名検証（`authlib`） | 各段階の例外は `OidcError` に畳み `/auth/login?sso_error=...` へリダイレクト。未登録メールは自動作成せず拒否 |
| Prometheus | 運用監視（メトリクス公開、`web/routes/metrics.py` → `web/services/metrics.py: render_metrics`） | Prometheus → WebSpec2Doc（スクレイプ） | `GET /metrics` | 既定ではログイン必須（`/metrics` は `web/auth.py` の認証除外パスに含まれていないことをソースで確認済み）。Prometheus 側の認証設定は未確認 | スクレイプ失敗時の挙動は Prometheus 側の運用に依存し、本体側の挙動は未確認 |
| MCP サーバ | レガシー仕様の read-only 供給（AI エージェント向け、`docs/specs/spec-4-2_mcp_server.md`） | **未実装** | 設計のみ存在。`mcp` パッケージは `requirements.txt` に未導入（spec 内に「未: MCPプロトコル対応の一切」と明記） | ― | ― |
| クロール対象サイト（送信ゲートウェイ経由） | 生成テスト実行時の外向き通信を一元検査・監査（`web/services/egress_gateway.py`） | WebSpec2Doc（生成テスト）→ クロール対象サイト | Playwright の `route` インターセプトで URL 単位に許可判定 | ポリシー（環境変数 `WEBSPEC2DOC_EGRESS_POLICY` の JSON）でホスト許可・private address 拒否等を判定 | 危険と判定した通信は `route.abort()` で遮断し `egress_log.ndjson` に記録（「送信 0」の実証に使用） |

## 6. OpenAPI 仕様の自動生成

- `GET /api/v1/openapi.json`（`web/services/openapi_spec.py: build_openapi_spec`）が、実行中 Flask アプリに登録済みの `/api/v1` 配下ルートから **動的に** OpenAPI 3.0.3 仕様を生成する（実装済みルートのみ列挙するためドキュメントと実装がドリフトしない）。
- `GET /api/v1/docs`（`web/services/openapi_docs.py: render_openapi_docs`）が、上記仕様を自己完結 HTML（外部 CDN 非依存）のリファレンスとして描画する。
- 本書 §2 の手動一覧との関係: 自動生成される OpenAPI 仕様は `api_v1` ブループリント配下のみを対象とするため、本書 §2 は `api_v1` を含む全 26 ブループリントを対象とする上位互換の一覧として補完関係にある。

## 改訂履歴

| 版 | 日付 | 内容 | 作成者 |
|---|---|---|---|
| 1.0 | 2026-07-16 | 初版作成 | 開発チーム |
| 2.0 | 2026-07-19 | ログインフロー順序修正等を反映 | 開発チーム |
| 3.0 | 2026-08-02 | 全面改訂。エンドポイントを実測 196 本・Blueprint 26 に全件化（旧版は 121 本・17 ブループリント）。認証方式・テナント分離・CSRF・レート制限・外部連携 I/F を実装確認の上で追記。README.md との数値差異を明記 | 開発チーム |
| 3.1 | 2026-08-02 | エンドポイント抽出方式を AST 解析から Flask `app.url_map` 実測へ修正し200本に更新（`api_v1`/`api_v1_schedule`/`admin`/`oidc` の計23本で `url_prefix` 欠落によるパス誤りを是正）。DD-001 の WS2D-PD-001 参照誤りも合わせて修正 | 開発チーム |
