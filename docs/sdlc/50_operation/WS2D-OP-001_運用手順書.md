# WS2D-OP-001 運用手順書（管理者向け）

- 文書ID: WS2D-OP-001
- 版数: 3.0 / 作成日: 2026-07-16 / 最終更新: 2026-08-02
- 対象読者: 本番運用を担当する管理者。
- 関連文書: エンドユーザー向けの使い方は `docs/userguide.md` / `docs/GUIDE_ja.md`。構築手順の全量は `docs/sdlc/50_operation/WS2D-EN-001_環境構築手順書.md`。障害発生時の切り分けは `docs/sdlc/50_operation/WS2D-TS-001_障害対応手順書.md`。

## 1. 運用体制と運用時間の前提

- 本製品はPC（デスクトップ）専用のローカル/社内サーバー運用を想定しており、SaaS型の24/365運用を前提とした体制（オンコール等）は定義されていない。
- 運用時間・SLA・当番体制は **本書時点で未定義**。社内展開する場合は導入組織側で定めること。
- 管理者ロール（`ROLE_ADMIN`）はテナント単位で付与され、`web/routes/tenant_admin.py` の管理コンソール（`/admin/console`）とテナント内管理API（`web/routes/account.py`）の双方の操作権限を持つ。

## 2. 起動・停止

```bash
source venv/bin/activate
python app.py                    # 127.0.0.1:8765 で起動しブラウザを自動起動
# または
./run.sh <URL>                   # 環境チェック込みの単発クロール実行
```

停止は `Ctrl-C`。Playwrightランタイム未整備時は `make setup-runtime`。
構築手順・環境変数の全量は `WS2D-EN-001_環境構築手順書.md` を正とする。本書では運用上必要な手順のみ抜粋する。

### 2.1 認証の有効化手順（社内共有時）

```bash
export WEBSPEC2DOC_TRUSTED_HOSTS="webspec2doc.example.internal"
export WEBSPEC2DOC_AUTH_MODE=required           # または auto
export WEBSPEC2DOC_SECRET_KEY="<32文字以上のランダム値>"
export WEBSPEC2DOC_SECURE_COOKIES=1             # HTTPS 終端の背後
python app.py
```

ブラウザで `/auth/setup` を開き、最初のワークスペースとオーナーを作成する。以降は全routeがログイン必須になる。詳細は `docs/AUTH_TENANCY.md`。

## 3. 定常運用作業

| 頻度 | 作業 | 手順 | 確認観点 |
|---|---|---|---|
| 日次 | メトリクス確認 | `curl http://127.0.0.1:8765/metrics` | crawl失敗数・スケジュール遅延・ジョブ滞留が増えていないか |
| 日次 | エラーログ確認 | アプリの標準出力（`configure_json_logging()` 有効時はJSON1行ログ） | 例外・タイムアウトの有無 |
| 日次 | クロール監査ログ確認 | `output/{domain}/audit.jsonl` | 想定外の遮断・送信が無いか |
| 週次 | ディスク使用量確認 | `du -sh output instance` | 保持ポリシーで想定した増加率に収まっているか |
| 週次 | バックアップ実施 | 本書§5 | アーカイブとチェックサムが生成されているか |
| 週次 | AutoRunジョブ滞留確認 | `/api/autorun/status`、メトリクス`webspec2doc_job_queue_depth` | 長時間PENDINGのジョブが無いか |
| 月次 | 依存関係の脆弱性監査 | `make audit` | critical/high の有無 |
| 月次 | Playwrightブラウザの更新確認 | `make setup-runtime` | Chromiumが最新の対応バージョンか |
| 月次 | 保持ポリシーの実施結果確認 | `instance/retention.json`（テナント別は`instance/tenants/<tenant>/retention.json`）と実際の`output/`世代数の突合 | 意図通りに世代管理されているか |
| 四半期 | リストア演習 | 本書§5.2の手順を隔離環境で実施 | 復旧時間・欠落データの有無を記録 |

## 4. 監視

### 4.1 メトリクス（`GET /metrics`、Prometheus形式）

出典: `web/routes/metrics.py`（エンドポイント本体）→ `web/services/metrics.py`（`render_metrics()`）。

| 指標 | 型 | 見るべき理由 |
|---|---|---|
| `webspec2doc_crawl_total{result}` | Counter | 失敗が増えていないか |
| `webspec2doc_crawl_duration_seconds` | Histogram | 所要時間の悪化 |
| `webspec2doc_schedule_delay_seconds` | Gauge | 予定どおり動いているか |
| `webspec2doc_job_queue_depth` | Gauge | ジョブが滞留していないか |
| `webspec2doc_notification_total{result,channel}` | Counter | 通知が届いているか |

成功数だけでなく失敗・遅延・滞留を対で公開している。「動いているか」ではなく **「静かに壊れていないか」** を見るための値。公開するのは本プロセスが観測した値のみで、対象サイトの品質やSLA達成度は含まない。

**アラート閾値: 本書時点で未定義。** 導入組織のSLAに応じて、失敗率・遅延・滞留の許容値を別途定めること。

### 4.2 ログ

- **構造化ログ**: `web.services.metrics.configure_json_logging()` で1行1JSONへ切替可能。
- **クロール監査ログ**: `output/{domain}/audit.jsonl`（礼儀制御・破壊的リクエストの遮断記録）。
- **アプリケーションログ**: `web/` `src/` 配下の主要モジュールが `logging.getLogger(__name__)` で標準loggingを使用。既定では専用ログファイルではなくプロセスの標準出力/標準エラーに出る（個別のファイル出力設定は本書では未確認）。

## 5. バックアップ・リストア

対象: リポジトリ直下の `output/`（収集結果・スナップショット・レポート・差分・テスト成果物）と `instance/`（認証DB・テナント別設定・保持設定・管理監査ログ）。この2ディレクトリは必ず同じ時点の対として扱う。`output/` だけを戻すと、認証・テナント・保持設定・スケジュール情報との整合が失われる。`.env` はAPIキー等を含むため、必要な場合だけ別の秘密情報保管庫へ保存し、通常のバックアップアーカイブには含めない。

バックアップには認証情報・画面内容・監査証跡が含まれる。保存先を暗号化し、アクセス権を運用管理者に限定すること。

### 5.1 バックアップ手順

1. 実行中のクロールとスケジューラが無いことを確認し、WebSpec2Docプロセスを停止する（SQLiteと生成ファイルを同じ時点で保存するため、稼働中のコピーは行わない）。
2. リポジトリ直下で実行する。

   ```bash
   stamp=$(date +%Y%m%d-%H%M%S)
   mkdir -p backups
   tar -czf "backups/webspec2doc-${stamp}.tar.gz" output instance
   shasum -a 256 "backups/webspec2doc-${stamp}.tar.gz" > "backups/webspec2doc-${stamp}.tar.gz.sha256"
   chmod 600 "backups/webspec2doc-${stamp}.tar.gz" "backups/webspec2doc-${stamp}.tar.gz.sha256"
   ```

3. アーカイブの一覧とチェックサムを検証する。

   ```bash
   tar -tzf "backups/webspec2doc-${stamp}.tar.gz" | sed -n '1,40p'
   shasum -a 256 -c "backups/webspec2doc-${stamp}.tar.gz.sha256"
   ```

4. アーカイブと `.sha256` を同じ保持単位で、リポジトリ外の暗号化ストレージへ複製する。復旧要件に応じて日次・週次・月次の保管世代を決める。

### 5.2 リストア手順

リストアは既存データを置き換える。対象アーカイブ、復旧時点、作業者を変更記録に残してから実行する。

1. WebSpec2Docプロセスを停止する。
2. チェックサムを検証する。

   ```bash
   shasum -a 256 -c backups/webspec2doc-YYYYMMDD-HHMMSS.tar.gz.sha256
   ```

3. 作業用ディレクトリへ展開し、`output/` と `instance/` 以外が含まれていないことを確認する。

   ```bash
   restore_dir=$(mktemp -d)
   tar -xzf backups/webspec2doc-YYYYMMDD-HHMMSS.tar.gz -C "$restore_dir"
   find "$restore_dir" -maxdepth 2 -print | sed -n '1,80p'
   ```

4. 現在のデータを退避してから、対で入れ替える。`RESTORE_TIMESTAMP` は同じ値を使用する。

   ```bash
   RESTORE_TIMESTAMP=$(date +%Y%m%d-%H%M%S)
   mv output "output.pre-restore-${RESTORE_TIMESTAMP}"
   mv instance "instance.pre-restore-${RESTORE_TIMESTAMP}"
   mv "$restore_dir/output" output
   mv "$restore_dir/instance" instance
   ```

5. 所有者と権限を実行ユーザーに合わせ、WebSpec2Docを起動する。管理者ログイン、サイト一覧、最新レポート、スケジュール設定、監査ログを確認する。
6. 問題が無ければ退避データを所定の変更管理手順で削除する。問題がある場合はプロセスを再停止し、同じ手順で `*.pre-restore-*` を戻す。

### 5.3 復旧確認チェックリスト

- [ ] 管理者がログインできる
- [ ] 期待するワークスペースとメンバーが表示される
- [ ] サイトと最新スナップショット件数が一致する
- [ ] レポートを開ける
- [ ] 保持ポリシーとスケジュール／通知設定が一致する
- [ ] 管理監査ログを閲覧できる
- [ ] 次回のスケジュール実行が成功する

少なくとも四半期ごとに、隔離環境でリストア演習を行い、実測した復旧時間と欠落データの有無を記録すること。

## 6. データ保持・削除

出典: `web/services/retention.py`、呼び出し元 `web/services/scheduler.py`、設定API `web/routes/admin.py`。

### 6.1 保持ポリシー

`RetentionPolicy` は3モードを持つ。

| mode | 意味 | パラメータ |
|---|---|---|
| `unlimited`（既定） | 削除しない | — |
| `generations` | 直近N世代のスナップショットのみ残す | `generations`（1〜10,000） |
| `days` | 指定日数より古いスナップショットを削除（最新1件は必ず残す） | `days`（1〜3,650） |

設定ファイルが存在しない・壊れている場合は **安全側の `unlimited`** を返す（`load_retention_policy`。誤って全削除する事故を防ぐフェイルセーフ）。

### 6.2 保存場所とスコープ

- グローバル既定: `instance/retention.json`
- テナント別: `instance/tenants/<tenant>/retention.json`（`web/services/scheduler.py` がテナントごとに個別のポリシーを読む）
- 設定API: `web/routes/admin.py` が保持ポリシーの取得・更新エンドポイントを公開し、`_retention_path()` 経由でテナントスコープを解決する。

### 6.3 実行タイミング

**スケジューラ（`web/services/scheduler.py`）が、スケジュール実行の一環として自動的に `load_retention_policy` → `prune_snapshots` を呼び出す。** 管理者が手動で都度実行する運用ではなく、定期実行スケジュールに組み込まれている（具体的な実行間隔・トリガー条件は本書では未確認）。

### 6.4 削除の挙動

- `generations` モード: 新しい順に並べたスナップショットのうち先頭 `generations` 件を残し、それ以降を削除する。
- `days` モード: 最新1件は無条件に残し、それ以外は `cutoff = 現在時刻 - days日` より古いものを削除する。
- 削除対象のスナップショットJSONに対応する **世代別スクリーンショット格納ディレクトリ**（`*-shots/`）も合わせて削除する（片方だけ残ると参照されないまま容量が単調増加するため）。
- シンボリックリンク・`snapshots/`の外を指すパスは削除対象にしない（パストラバーサル対策）。

### 6.5 保持ポリシー対象外のデータ整理

保持ポリシーが対象にするのはスナップショット（`output/{domain}/snapshots/`）のみ。以下は対象外であり、別に整理が必要。

- サイト自体の削除: UIから、または `DELETE /api/site/<domain>`。
- 完全アーカイブ（本書§9）: 保持ポリシーでは消えない。

## 7. アカウント・テナント管理運用

出典: `web/routes/tenant_admin.py`（管理コンソール・全テナント横断操作）、`web/routes/account.py`（テナントスコープの操作・APIトークン）。

### 7.1 管理コンソール（`/admin/console`、要 `ROLE_ADMIN`）

| 操作 | エンドポイント | 備考 |
|---|---|---|
| テナント作成 | `POST /api/admin/tenancy/tenants` | name, slug を指定 |
| テナント名変更 | `PATCH /api/admin/tenancy/tenants/<id>` | |
| テナント削除 | `DELETE /api/admin/tenancy/tenants/<id>` | **`output/tenants/<slug>` 配下のファイルは削除されない**（コード内の明示コメント）。生成物は別途整理が必要 |
| ユーザー作成 | `POST /api/admin/tenancy/users` | 任意でtenant_idを指定 |
| 所属・ロール設定 | `PUT /api/admin/tenancy/users/<id>/memberships` | テナントごとに member/admin を使い分け可能 |
| アカウント有効/無効化 | `PATCH /api/admin/tenancy/users/<id>` | `is_active` 真偽値。**全テナントに効く** |
| ユーザー削除 | `DELETE /api/admin/tenancy/users/<id>` | 自分自身は削除不可 |

### 7.2 テナント内管理（`/auth/account`、要ログイン。管理者操作は要 `ROLE_ADMIN`）

| 操作 | エンドポイント | 備考 |
|---|---|---|
| ユーザー一覧 | `GET /api/auth/users` | 現テナントのみ |
| ユーザー作成 | `POST /api/auth/users` | 現テナントに所属 |
| ロール/有効化更新 | `PATCH /api/auth/users/<id>` | |
| パスワード変更 | `POST /api/auth/password` | 変更後は全セッション失効・再ログインが必要 |

### 7.3 APIトークンの発行・失効

`/api/v1/*`（`web/routes/api_v1.py`）は Bearer APIトークンでもテナントが解決される（コード先頭のコメントに明記）。トークンの発行・一覧・失効は管理者操作。

| 操作 | エンドポイント |
|---|---|
| 一覧 | `GET /api/auth/api-tokens` |
| 発行 | `POST /api/auth/api-tokens`（`name` を指定） |
| 失効 | `DELETE /api/auth/api-tokens/<token_id>` |

いずれも `ROLE_ADMIN` 必須。発行済みトークンは `/auth/account` 画面（`api_tokens` 一覧）でも確認できる。**トークン値そのものの再表示可否は本書では未確認**。失効したトークンで `/api/v1/*` へアクセスした場合の挙動も未確認（想定は401/403）。

## 8. 定期メンテナンス

| 作業 | コマンド | 頻度目安 |
|---|---|---|
| 依存脆弱性監査（Python） | `make audit`（`venv/bin/python -m pip_audit -r requirements.txt -r requirements-dev.txt`） | 月次 |
| 依存脆弱性監査（AutoRun npm環境） | `make audit` が `output/.playwright_env/node_modules` 存在時に `npm audit --audit-level=high` を実行 | 月次 |
| セキュリティスキャン | `make security`（bandit + pip-audit） | 月次、または依存更新時 |
| Playwrightブラウザ更新 | `make setup-runtime` | Playwrightバージョン更新時・月次確認 |
| 静的解析 | `make lint`（ruff + mypy + 独自チェック） | リリース前 |

## 9. 長期保管（規制業種向け）

保持ポリシー（`instance/retention.json`）が「古いものを消す」仕組みであるのに対し、完全アーカイブは「消さずに固めて残す」。監査で後から提出する用途。

```python
from archive.full_archive import create_full_archive, verify_archive
result = create_full_archive(Path("output/example.com"), Path("output/example.com/archives"))
verify_archive(result.archive_path)   # {'ok': True, ...}
```

- 書庫には `MANIFEST.json`（各ファイルのSHA-256）を同梱する。受け取った側が改竄を検知できる。
- **アーカイブは元データを消さない**。削除は保持ポリシー側の責務で、経路を二重化しない。

## 10. 障害対応

事象別の切り分け・エスカレーション・恒久対策プロセスは `docs/sdlc/50_operation/WS2D-TS-001_障害対応手順書.md` を正とする。

## 11. 改訂履歴

| 版 | 日付 | 内容 | 作成者 |
|---|---|---|---|
| 2.0 | 2026-07-16 | 初版 | 開発チーム |
| 2.0 | 2026-07-19 | 最終更新（旧版） | 開発チーム |
| 3.0 | 2026-08-02 | 全面改訂。定常運用作業表、データ保持・削除、アカウント・テナント管理運用、定期メンテナンスを新設。環境構築の詳細はWS2D-EN-001へ、障害対応はWS2D-TS-001へ分離 | 開発チーム |
