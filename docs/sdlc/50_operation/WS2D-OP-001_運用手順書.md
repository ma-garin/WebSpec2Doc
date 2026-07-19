# WS2D-OP-001 運用手順書（管理者向け）

- 版数: 2.0 / 作成日: 2026-07-16 / 最終更新: 2026-07-19
- エンドユーザー向けの使い方は `docs/userguide.md` / `docs/GUIDE_ja.md`（役割分担）。

## 1. 起動 / 停止

```bash
python app.py                    # 127.0.0.1:8765 で起動しブラウザを自動起動
# または
./run.sh                         # 環境チェック込みの起動スクリプト
```

停止は Ctrl-C。Playwright ランタイム未整備時は `make setup-runtime`（Chromium 導入）。

## 2. 環境変数一覧

| 変数 | 既定 | 用途 |
|---|---|---|
| `WEBSPEC2DOC_PORT` | 8765 | 待受ポート |
| `WEBSPEC2DOC_TRUSTED_HOSTS` | （未設定） | 社内サーバ展開時の許可ホスト（0.0.0.0 待受＋ガード） |
| `WEBSPEC2DOC_AUTH_MODE` | `auto` | 認証モード（`auto`＝ユーザー作成後に必須／`required`／`off`） |
| `WEBSPEC2DOC_SESSION_HOURS` | 12 | セッション有効時間 |
| `WEBSPEC2DOC_SECURE_COOKIES` | OFF | HTTPS 終端の背後では 1 を設定（Secure クッキー） |
| `WEBSPEC2DOC_SECRET_KEY` | 自動生成 | セッション署名鍵（未設定時 `instance/secret_key`・0600） |
| `WEBSPEC2DOC_ALLOW_LOCAL` | OFF | ローカル URL クロールの許可（SSRF 保護のバイパス。信頼環境のみ） |
| `WEBSPEC2DOC_ALLOW_FORM_SUBMIT` | OFF | **フォーム到達クロール（送信を伴う）の解禁**。二重オプトインの片方で、明示フラグとホスト許可リストも必須。**テスト環境限定**。破壊的文言ボタン（削除/購入/決済等）は自動スキップし、全送信を値なしで監査ログへ記録する |
| `VIEWPOINTS_DB` / `OUTPUT_DIR` 他 | `web/config.py` 参照 | データ配置の上書き |
| `OPENAI_API_KEY` | （未設定） | LLM 補完（未設定時はルールベース） |
| `WEBSPEC2DOC_OIDC_PROVIDER` | （未設定） | SSO を使う場合のみ `entra` / `google`。**未設定なら SSO は完全に無効**で、既存のID/パスワード認証に影響しない |
| `WEBSPEC2DOC_OIDC_CLIENT_ID` / `_CLIENT_SECRET` / `_REDIRECT_URI` | — | SSO 有効時に必須。不足時は不足変数名を挙げて起動時に失敗する |
| `WEBSPEC2DOC_OIDC_TENANT` | `common` | Entra ID のテナント（issuer 組み立て用） |
| `WEBSPEC2DOC_OIDC_ALLOWED_DOMAINS` | （未設定） | SSO を許可するメールドメイン（カンマ区切り） |

## 3. 認証の有効化手順（社内共有時）

```bash
export WEBSPEC2DOC_TRUSTED_HOSTS="webspec2doc.example.internal"
export WEBSPEC2DOC_AUTH_MODE=required           # または auto
export WEBSPEC2DOC_SECRET_KEY="<32+ 文字のランダム値>"
export WEBSPEC2DOC_SECURE_COOKIES=1             # HTTPS 終端の背後
python app.py
```
ブラウザで `/auth/setup` を開き、最初のワークスペースとオーナーを作成する。
以降は全 route がログイン必須になる。詳細は `docs/AUTH_TENANCY.md`。

## 4. バックアップ / リストア

- 対象: `instance/`（`viewpoints.db`, `auth/*`, 設定）と `output/`（成果物）。
- いずれも gitignore（環境ローカル）。定期的にディレクトリごと退避する。
- サイト削除: UI から、または `DELETE /api/site/<domain>`。

## 5. トラブルシュート

- `make doctor` で環境診断（venv / Chromium / 依存）。
- クロールがローカル URL で 403 → `WEBSPEC2DOC_ALLOW_LOCAL=1`（信頼環境のみ）。
- サイト認証のセッション失効 → 再ログインを促す（クロール中に検出）。
- 依存脆弱性 → `make audit`（pip-audit ＋ npm audit）。

## 6. 監視・ログ
- クロール礼儀・遮断は `output/{domain}/audit.jsonl`。
- AutoRun ジョブ状態はポーリング API（`/api/autorun/status`）。
- **メトリクス**: `GET /metrics`（Prometheus 形式）。公開する値は次のとおり。

  | 指標 | 型 | 見るべき理由 |
  |---|---|---|
  | `webspec2doc_crawl_total{result}` | Counter | 失敗が増えていないか |
  | `webspec2doc_crawl_duration_seconds` | Histogram | 所要時間の悪化 |
  | `webspec2doc_schedule_delay_seconds` | Gauge | 予定どおり動いているか |
  | `webspec2doc_job_queue_depth` | Gauge | ジョブが滞留していないか |
  | `webspec2doc_notification_total{result,channel}` | Counter | 通知が届いているか |

  成功数だけでなく失敗・遅延・滞留を対で公開している。「動いているか」ではなく
  **「静かに壊れていないか」**を見るための値。公開するのは本プロセスが観測した値のみで、
  対象サイトの品質や SLA 達成度は含まない。

- **構造化ログ**: `web.services.metrics.configure_json_logging()` で1行1JSONへ切り替え可。

## 7. 長期保管（規制業種向け）

保持ポリシー（`instance/retention.json`）が「古いものを消す」仕組みなのに対し、
完全アーカイブは「消さずに固めて残す」。監査で後から提出する用途。

```python
from archive.full_archive import create_full_archive, verify_archive
result = create_full_archive(Path("output/example.com"), Path("output/example.com/archives"))
verify_archive(result.archive_path)   # {'ok': True, ...}
```

- 書庫には `MANIFEST.json`（各ファイルの SHA-256）を同梱する。受け取った側が改竄を検知できる。
- **アーカイブは元データを消さない**。削除は保持ポリシー側の責務で、経路を二重化しない。
