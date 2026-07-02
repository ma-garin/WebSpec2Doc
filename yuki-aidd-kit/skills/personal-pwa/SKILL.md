---
name: personal-pwa
description: 個人用PWA（家計簿・キャッシュフロー・日記・スケジュール管理等）の開発スキル。GitHub Pages（ma-garin）へのデプロイ、localStorage永続化、無料枠APIの利用、スマホ向けUIの作成が絡む場合は必ずこのスキルを使用すること。「PWAにしたい」「スマホで使えるアプリ」「nichijo_app」「my-accounting-app」「家計簿」「乃木坂スケジュール」等への言及にも適用する。
---

# 個人PWA開発規約

ゼロランニングコストが大前提。サーバレス・無料枠のみで構成する。

## 構成の既定
- ホスティング: GitHub Pages（リポジトリ: ma-garin配下）
- 構成: index.html + manifest.json + sw.js（最小3ファイル、ビルドなし）
- Service Worker: cache-first戦略、バージョン文字列でキャッシュ更新を制御
- データ: localStorage（キー `{appName}:{type}`、スキーマversion付与、export/import機能を必ず付ける）

## AI連携（必要な場合のみ）
- 既定は **Gemini API 無料枠**（Claude APIの代替としてコストゼロ運用）
- APIキーはlocalStorage保存＋設定画面入力。リポジトリにコミットしない
- レート制限（無料枠RPM/RPD）を超えないようUI側でリクエスト抑制（debounce、手動実行ボタン）
- 応答はJSON強制＋フェンス除去フォールバック

## デバイス対応
- **メインターゲット: Galaxy Z Fold5**。折りたたみ両状態で崩れないレスポンシブ（カバー画面 約344px幅〜メイン画面 約1812px幅）
- サブ: iPhone 13 Pro Safari。iOS PWAの制約（プッシュ通知の制限、ストレージevict）を前提に設計し、重要データはexport導線で担保
- タッチターゲット44px以上、片手操作で主要機能に届く下部配置

## 開発フロー
- 小規模なのでガバナンスは spec-first（sdd-ecc-workflowスキル参照）
- 1機能1コミット、GitHub Pagesへの反映確認まで含めて完了とする
- 既存PWAの改修時はlocalStorageマイグレーション関数を必ず用意
