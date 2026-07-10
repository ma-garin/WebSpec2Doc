# アプリ利用者認証とテナント分離

WebSpec2Doc を「1人のローカルツール」から「チーム/商用で共有できるサーバ」として
運用するための、アプリ利用者認証（ログイン）とテナント（ワークスペース）分離の仕様。

> 既存の「ログイン」機能（`/api/login/*`, `web/routes/login.py`）は **クロール対象サイト**への
> 認証であり、本書の対象ではない。本書はWebSpec2Doc自体を使うユーザーの認証を扱う。

## 動作モード（`WEBSPEC2DOC_AUTH_MODE`）

| モード | 挙動 |
|---|---|
| `auto`（既定） | ユーザーが1人も居ない間は従来どおり認証なし（ローカル単独利用）。`/auth/setup` で最初のワークスペース＋オーナーを作成した時点から全ルートでログイン必須になる |
| `required` | 常にログイン必須。ユーザー未作成の間は `/auth/setup` のみ到達可能 |
| `off` | 認証を完全に無効化（明示的なオプトアウト） |

既定が `auto` なのは、既存のローカル利用・E2Eテスト（`make verify-ui`）を壊さず、
共有サーバ展開時にだけ認証を有効化できるようにするため。

## 画面とAPI

- `GET/POST /auth/setup` — 初期セットアップ（ワークスペース＋オーナー作成、ユーザー0人時のみ）
- `GET/POST /auth/login` / `POST /auth/logout` — ログイン/ログアウト
- `GET /auth/account` — マイページ（プロフィール・パスワード変更、管理者はメンバー管理・APIトークン）
- `GET /api/auth/me` — 現在のユーザー・テナント・認証モード
- `POST /api/auth/password` — パスワード変更（変更後は全セッション失効）
- `GET/POST /api/auth/users`, `PATCH /api/auth/users/<id>` — メンバー管理（owner/admin のみ）
- `GET/POST/DELETE /api/auth/api-tokens` — `/api/v1` 用テナントAPIトークン（owner/admin のみ）

## セキュリティ仕様

- パスワード: werkzeug（scrypt）でハッシュ化。10文字以上、メールアドレスと同一は拒否
- セッション: サーバサイド管理（`instance/auth.db` の `auth_sessions`）。クッキーには
  ランダムトークンのみ（`ws2d_session`, HttpOnly, SameSite=Lax）。DBにはトークンの
  SHA-256のみ保存。既定12時間で失効（`WEBSPEC2DOC_SESSION_HOURS`）
- ロックアウト: ログイン5回連続失敗で15分ロック（正しいパスワードでも拒否）
- ロール: `owner` / `admin` / `member`。設定変更（OpenAIキー等）とメンバー管理は
  owner/admin のみ。最後の有効オーナーは無効化・降格不可
- 無効化・パスワード変更時は該当ユーザーの既存セッションを即時失効
- `next` パラメータは相対パスのみ許可（オープンリダイレクト防止）
- 監査ログ: ログイン・ユーザー作成/変更・トークン発行/失効を `audit_log` に記録
- SECRET_KEY: `WEBSPEC2DOC_SECRET_KEY` → `instance/secret_key`（0600で自動生成）の順で解決
- HTTPS 終端の背後では `WEBSPEC2DOC_SECURE_COOKIES=1` を設定すること

## テナント分離のデータ配置

| データ | 共有モード（認証オフ/ユーザーなし） | テナントモード |
|---|---|---|
| クロール成果物 | `output/{domain}/` | `output/tenants/{slug}/{domain}/` |
| 観点DB | `instance/viewpoints.db` | `instance/tenants/{slug}/viewpoints.db`（DB-per-tenant） |
| 認証DB | `instance/auth.db`（全テナント共通） | 同左 |

- テナント解決は `web/auth.py` の `auth_guard` が `g.tenant` に設定し、
  `web/tenancy.py: scoped_output_dir() / scoped_instance_path()` が保存先を切り替える
- slug はDB由来でもパス構築前に `^[a-z0-9][a-z0-9-]{0,31}$` で再検証する（トラバーサル防止）
- **リクエストコンテキスト外**（ストリーミング応答・AutoRun/クロールのバックグラウンド
  スレッド・スケジューラ）ではテナントを自動解決できないため、ビュー/ジョブ開始時に
  解決した出力先をクロージャ・ジョブ属性（`AutoRunJob._output_dir`）・引数
  （`start_crawl_job(output_dir=...)`）で明示的に持ち回る。CLIサブプロセスには
  `--output` で渡す
- `/api/v1` は `Authorization: Bearer <token>` のテナントAPIトークンでも認証できる
  （トークンは発行時に一度だけ表示。DBにはSHA-256のみ保存）

## 既知の制約（未対応・今後の拡張）

- OpenAI APIキー等の `.env` 設定はインスタンス全体で共有（テナント別キーは未対応）。
  変更操作は owner/admin に限定して緩和している
- スケジューラ・AutoRunの実行キューはインスタンス共有（テナント別のレート制御なし）
- SSO（OAuth/OIDC）、パスワードリセットメール、監査ログのUI表示は未実装
- 既存データの移行: 認証導入前の `output/{domain}/` はテナントからは見えない。
  必要なら `output/tenants/{slug}/` へ手動で移動する

## 利用ガバナンス（Phase 2）

| 制限 | 単位 | 既定（standard） | pro | unlimited |
|---|---|---|---|---|
| APIレート | ユーザー/APIトークン毎分 | 120 | 300 | 無制限 |
| 月次クロール | テナント/月 | 100 | 1000 | 無制限 |
| 同時実行ジョブ | テナント | 2 | 5 | 無制限 |

- 解決順序: プラン既定値 → テナント個別上書き（`tenants.limits_json`）→ 環境変数（`WEBSPEC2DOC_RATE_PER_MINUTE` 等）。値 0 は無制限
- 超過時は 429（`rate_limited` / `quota_exceeded`）。レート超過は `Retry-After` ヘッダー付き
- クォータは**成功した**クロール/AutoRunのみ消費（usage_log.jsonl 集計。失敗は数えない）
- 認証オフ（ローカル単独利用）では一切制限しない
- プラン変更はオーナーのみ: `PATCH /api/auth/tenant {"plan": "pro", "limits": {...}}`
- 使用量確認: `GET /api/auth/usage` またはアカウント画面の「使用量と上限」カード
- 制約: レートリミットはプロセス内実装（現行の単一プロセス運用前提。マルチワーカー化時は共有ストアに要置換）

## デプロイ連動Webhook

```bash
curl -X POST https://<host>/api/v1/hooks/deploy \
  -H "Authorization: Bearer ws2d_..." \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-app.example.com"}'
```

- 202 と `job_id` を返し、`compare=True` で再クロール（進捗は `GET /api/v1/jobs/{job_id}`）
- 差分検出時は既存のSlack通知が発火する
- クォータ・同時実行制限の対象

## スペックドリフト トレンド

- `GET /api/drift-trend?domain=<domain>` — スナップショットごとの画面/フォーム/フィールド/ボタン数の時系列（直近60点）
- ダッシュボードの解析履歴カードに直近2スナップショット間の変化を「ドリフト」バッジで表示
