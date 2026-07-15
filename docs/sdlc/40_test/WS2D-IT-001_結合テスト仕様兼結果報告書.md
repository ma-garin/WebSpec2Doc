# WS2D-IT-001 結合テスト仕様兼結果報告書（L2）

- 版数: 1.0 / 作成日: 2026-07-16 / 準拠: ISO/IEC/IEEE 29119 / ISTQB
- 定義: Flask ルート統合。`app.test_client()` / `create_app()` を用い、route → service →
  core → 永続化の結合経路を HTTP レベルで検証する（実ブラウザは L3）。

## 1. 対象と方針

- 対象: `web/routes/*`（17 Blueprint・112 EP）と `web/services/*`、`web/auth/*` の結合。
- 観点: 入力検証・正常/異常応答（JSON エラー整形）・CSRF/ガード・永続化副作用・
  ジョブ制御（AutoRun のキュー/承認/キャンセル）。

## 2. 実施結果（実測）

| 指標 | 値 |
|---|---|
| 結合テストファイル（test_client/create_app 使用） | 22 |
| L1/L2 合計（`make test`） | **1,794 passed** |
| 実行コマンド | `make test` |

## 3. 代表的な結合テスト（抜粋）

- 認証: `test_auth_app.py` — ログイン/テナント選択/ガード/ログアウト/認証 OFF 非破壊
  （happy/failure/guard/logout）。
- QA プロセス: `test_qa_process.py` — 生成・結果取得の経路。
- サイト/履歴/設定: `test_app_site.py` / `test_app_login.py` / `test_app_wizard.py` /
  各 `test_*` が route 経由の結合を検証。
- API v1: `test_api_v1.py` — 外部公開 API（`/sites/...`, `/healthz`）。

## 4. 認証結合の代表シナリオ（`WEBSPEC2DOC_AUTH=1`）

| # | シナリオ | 期待 |
|---|---|---|
| IT-A1 | 正当メールでログイン | 既定 WS 自動作成→`/auth/tenants` |
| IT-A2 | 不正メール | 400＋エラー表示・非遷移 |
| IT-A3 | 未ログインで保護 route | `/auth/login` へリダイレクト |
| IT-A4 | ログイン済・WS 未選択 | `/auth/tenants` へ |
| IT-A5 | 非会員 WS を選択 | 拒否・`/auth/tenants` へ |
| IT-A6 | ログアウト | セッション破棄→保護 route 再リダイレクト |
| IT-A7 | 認証 OFF（既定） | `/` が無認証で開く（非破壊） |

## 5. 再現方法
```bash
make test    # 1,794 passed（L1 と合算）
```
