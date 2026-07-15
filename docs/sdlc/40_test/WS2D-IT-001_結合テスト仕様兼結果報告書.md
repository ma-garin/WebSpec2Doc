# WS2D-IT-001 結合テスト仕様兼結果報告書（L2）

- 版数: 1.0 / 作成日: 2026-07-16 / 準拠: ISO/IEC/IEEE 29119 / ISTQB
- 定義: Flask ルート統合。`app.test_client()` / `create_app()` を用い、route → service →
  core → 永続化の結合経路を HTTP レベルで検証する（実ブラウザは L3）。

## 1. 対象と方針

- 対象: `web/routes/*`（17 Blueprint・121 EP）と `web/services/*`、`web/auth.py` /
  `web/services/auth_store.py` / `web/tenancy.py` の結合。
- 観点: 入力検証・正常/異常応答（JSON エラー整形）・CSRF/認証ガード・永続化副作用・
  ジョブ制御（AutoRun のキュー/承認/キャンセル）・テナント分離。

## 2. 実施結果（実測）

| 指標 | 値 |
|---|---|
| 結合テストファイル（test_client/create_app 使用） | 23 |
| L1/L2 合計（`make test`） | **1,831 passed** |
| 実行コマンド | `make test` |

## 3. 代表的な結合テスト（抜粋）

- 認証: `test_app_account.py` / `test_auth_store.py` — ログイン・セッション・パスワード・
  ロックアウト・ロール・アカウント管理・APIトークン。
- テナント分離: `test_tenancy.py` — 出力/観点DBのワークスペース分離・slug 検証。
- QA プロセス: `test_qa_process.py` — 生成・結果取得の経路。
- サイト/履歴/設定: `test_app_site.py` / `test_app_login.py` / `test_app_wizard.py` /
  各 `test_*` が route 経由の結合を検証。
- API v1: `test_api_v1.py` — 外部公開 API（`/sites/...`, `/healthz`・Bearer トークン）。

## 4. 認証結合の代表シナリオ（`WEBSPEC2DOC_AUTH_MODE`。詳細 `docs/AUTH_TENANCY.md`）

| # | シナリオ | 期待 |
|---|---|---|
| IT-A1 | 既定 `auto`・ユーザー0人 | 認証なしで `/` が開く（現行ローカル利用を維持） |
| IT-A2 | `/auth/setup` で初期作成 | ワークスペース＋オーナー作成後、全 route がログイン必須に |
| IT-A3 | 正しい資格でログイン | セッション確立（`ws2d_session`）→ 保護 route 到達 |
| IT-A4 | 5 回連続失敗 | 15 分ロックアウト（正しい PW でも拒否） |
| IT-A5 | 未ログインで保護 route | `/auth/login` へリダイレクト（`next` は相対のみ） |
| IT-A6 | パスワード変更 | 該当ユーザーの全セッション即時失効 |
| IT-A7 | テナント有効時のクロール | 成果物が `output/tenants/{slug}/` に分離保存 |
| IT-A8 | 権限（member が設定変更） | owner/admin 以外は拒否 |

## 5. 再現方法
```bash
make test    # 1,831 passed（L1 と合算）
```
