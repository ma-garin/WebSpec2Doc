# WS2D-SD-001 画面設計書

- 版数: 2.0 / 作成日: 2026-07-16 / 最終更新: 2026-07-19 / 準拠: IPA 共通フレーム（画面設計）
- UI フローの用語は `CONTEXT.md`、刷新方針は `docs/design/ui-redesign-plan.md`。

## 1. 画面構成（シェル）

サイドバー（`nav.html`）＋トップバー（`topbar.html`）＋コンテンツ（SPA ビュー切替）。
クライアント側 `switchView(name)`（`static/js/core.js`）でビューを出し分ける。

- トップバー: パンくず・タイトル・**クイック検索**（⌘K・画面/サイト横断）・
  テーマ切替・ショートカット・**アバター**（認証 ON 時のみ）。
- 状態表示は `ui-states.js`（空 / ローディング / エラー＋再試行）に統一。

## 2. 画面一覧（SPA ビュー）

| ビューID (`data-view`) | 名称 | パス | 主な機能 |
|---|---|---|---|
| dashboard | ホーム | `/` | KPI カード＋解析履歴（`history.js`）／新規解析導線 |
| generate | サイトを追加 / 再クロール | `/generate` | 4 ステップウィザード（解析→条件→実行→レポート） |
| auto-run | AutoRun | `/auto-run` | URL→全自動テスト。**生成モード（URL駆動/文書駆動）**を切替。文書駆動時のみ「要件・仕様文書」「パス選定基準」「入力検証の観測」を表示。承認モーダル（実行対象/デバイス/制限時間、文書駆動時は要件数・対応画面数・選定パス数・カバー率） |
| run-history | 実行履歴 | `/run-history` | 種別タブ＋データテーブル＋ページネーション |
| testcases | テストケース | `/testcases` | 6 列表＋テキスト/自動化フィルタ＋ページネーション |
| qa-quality | 品質観点 | `/qa-quality` | ISTQB ベースの観点カード |
| viewpoints | 観点管理 | `/viewpoints` | 3 ペイン（ツリー＋フィルタ＋インライン表） |
| user-guide | ユーザーガイド | `/user-guide` | 使い方（`GUIDE_ja.md` と分担） |
| settings | 設定 | `/settings` | API キー・接続・ローカル許可・テスト設計設定 |
| traceability | トレーサビリティ | `/traceability/view` | 要件⇔テストのマトリクス（単独描画） |
| usage | ROIダッシュボード | `/usage` | 利用実績→削減工数の推定表示 |

レポートは generate 内のタブ構成（概要 / 画面別仕様 / テスト条件 / 設計 / 技法詳細 /
画面遷移図 / 遷移表 / 履歴・差分＝計 8 タブ、`CONTEXT.md`）。

## 3. 認証画面（商用/共有サーバ向け・`WEBSPEC2DOC_AUTH_MODE` が `auto`/`required`）

| 画面 | パス | 項目 |
|---|---|---|
| 初期セットアップ | `/auth/setup` | 最初のワークスペース＋オーナー作成（ユーザー0人時のみ） |
| ログイン | `/auth/login` | メールアドレス＋パスワード（ロックアウトあり） |
| マイページ | `/auth/account` | プロフィール・パスワード変更、管理者はメンバー管理・APIトークン |

`templates/auth/{login,setup,account}.html` ＋ `static/css/auth.css`。
既定 `auto` はユーザー未作成の間は認証なし（現行のローカル利用を維持）。詳細は `docs/AUTH_TENANCY.md`。
topbar のアバターはログイン時に `auth_user` として表示。

## 4. デザインシステム

- トークン: `static/tokens.css`（色・間隔・角丸・影・ライト/ダーク）。
- 主色 `#1976D2` / `#0D47A1`、地色 `#F4F6F9`。バッジは `--c` 基準色＋`color-mix`
  の soft パターンでダーク自動追従。
- 生 hex はエクスポート下地の白のみ（テーマ非依存）。UI のダーク gap ゼロ。

## 5. 付録: ドッグフーディング証跡

WebSpec2Doc 自身を WebSpec2Doc でクロールした生成物（画面仕様・遷移図）を
`WS2D-ST-001` のシステムテスト証跡として採用する（自製品での自己検証）。
