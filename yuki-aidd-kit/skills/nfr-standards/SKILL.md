---
name: nfr-standards
description: AIDDプロジェクト向けの非機能要件（NFR）定義スキル。spec.mdにNFRを書く時、パフォーマンス・アクセシビリティ・オフライン対応・セキュリティ・デバイス対応の要件を決める際は必ずこのスキルを使うこと。「非機能要件は」「パフォーマンスは」「アクセシビリティ対応」「オフラインで使えるか」「スマホ対応」という依頼にも適用する。
---

# NFR標準（AIDDプロジェクト用）

プロジェクト種別ごとにデフォルトNFRを定義する。spec.mdの非機能要求セクションにそのまま転記して使う。

## プロジェクト種別の判定

| 種別 | 条件 |
|---|---|
| **PWA** | GitHub Pages配置・Service Worker・localStorage使用 |
| **単一HTMLツール** | 社内配布・ブラウザで開くだけ・ビルドなし |
| **Streamlitアプリ** | business_agent系・ローカルまたはサーバ実行 |

---

## NFR: PWA（personal accounting PWA / nichijo系）

### 性能
- 初回ロード: 3G相当（1.6Mbps）で3秒以内に操作可能
- Lighthouse Performance: 80点以上（GitHub Pages CDN前提）
- 外部フォント（Noto Sans JP）は `display=swap` でレイアウトシフト抑制

### デバイス対応
- **折りたたみAndroid端末 カバー画面**: 360×820px で主要機能が使えること
- **折りたたみAndroid端末 メイン画面**: 768×1812px でレイアウトが崩れないこと
- **iPhone 13 Pro**: 390×844px（Safari PWA）。プッシュ通知は使用しない（iOS制約）
- タッチターゲット: 44×44px以上
- 下部タブ or FABで主要操作を片手で到達可能にする

### オフライン対応
- Service Worker: cache-firstでコアUIをキャッシュ（バージョン文字列で更新制御）
- データはlocalStorageに保存。ネットワーク不要で全機能動作すること
- iOSのlocalStorageは長期間未使用でevictされる可能性あり → 手動export/import機能を必ず実装

### アクセシビリティ
- WCAG 2.1 AA準拠（最低限: コントラスト比4.5:1以上、キーボード操作可能、alt属性付与）
- 日本語UI: lang="ja" 指定

### セキュリティ
- APIキー・認証情報はlocalStorage保存のみ（コードにハードコードしない）
- リポジトリはPublicでもAPIキーが混入しない構造にする（git-secrets推奨）
- 外部依存はCDN（cdnjs）のみ。npmパッケージをバンドルしない

### データ保全
- localStorageスキーマにversionフィールドを持たせ、マイグレーション関数を用意する
- export（JSON）/ import機能を必ず実装。データの外部バックアップを可能にする

---

## NFR: 単一HTMLツール（UX audit tool / QA Lens系）

### 配布・互換性
- Chrome / Edge 最新版で動作すること（Firefox・Safariはベストエフォート）
- ファイル1つをメールやSlack/Teamsで送れること（外部依存なし、または全CDN）
- ビルド不要: ダブルクリックで開くだけで動作

### 性能
- ファイルサイズ上限なし（単一HTMLの制約を守るため圧縮不可）
- AI処理（Claude/Gemini API）のレスポンス待ちにはローディング表示を必ず入れる

### セキュリティ
- APIキーはlocalStorage保存＋設定モーダルで入力
- XSSリスク: innerHTML への直接代入を避け、textContentまたはサニタイズ関数を使う

---

## NFR: Streamlitアプリ（business_agent系）

### 性能
- ページ初期表示: 3秒以内（LLM呼び出し除く）
- RAG検索レスポンス: 5秒以内（ローカル実行前提）
- LLM呼び出しはst.spinnerで待機状態を明示

### マルチテナント
- テナントIDを全DBクエリの第一キーとして強制フィルタ
- テナント間のデータ漏洩を単体テストで検証すること

### 保守性
- 1モジュール = 1責務。16モジュール構成を維持
- session_stateのキーは `{module}_{name}` 形式で衝突防止
- LLM呼び出しは1箇所のラッパー関数に集約（モデル切替・リトライを一元管理）

### セキュリティ
- APIキーは環境変数（.env）から読み込み。コードにハードコードしない
- .envは.gitignoreに必ず追加
