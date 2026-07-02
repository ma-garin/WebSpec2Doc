# /new-pwa — 新規個人PWA立ち上げ

引数: $ARGUMENTS（プロジェクト名 + 一言説明）

## 実行内容

以下の順で進めてください。

1. **spec.md を生成**（personal-pwaスキルの規約に従う）
   - ホスティング: GitHub Pages (ma-garin)
   - データ: localStorage、スキーマバージョン付き、export/import必須
   - AI連携: 必要か確認し、必要なら Gemini API 無料枠を採用
   - ターゲット: Galaxy Z Fold5（カバー〜メイン両画面）+ iPhone 13 Pro

2. **ディレクトリ構成を提示**
   - 最小3ファイル: index.html / manifest.json / sw.js
   - CLAUDE.md（プロジェクト用）を生成

3. **index.html のスキャフォールド生成**
   - Material Design 3 ライトテーマ
   - Noto Sans JP
   - localStorageの初期化コード + export/import関数のプレースホルダー
   - Service Workerの登録コード

4. **GitHub Pages 公開手順を提示**（リポジトリ作成〜Settings > Pages設定まで）

プロジェクト名が未指定の場合は確認してから進む。
