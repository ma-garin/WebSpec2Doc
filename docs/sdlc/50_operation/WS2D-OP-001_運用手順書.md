# WS2D-OP-001 運用手順書（管理者向け）

- 版数: 1.0 / 作成日: 2026-07-16
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
| `VIEWPOINTS_DB` / `OUTPUT_DIR` 他 | `web/config.py` 参照 | データ配置の上書き |
| `OPENAI_API_KEY` | （未設定） | LLM 補完（未設定時はルールベース） |

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
