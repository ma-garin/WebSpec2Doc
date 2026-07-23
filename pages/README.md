# pages/ — GitHub Pages ショーケース

WebSpec2Doc の画面と動きを、インストールなしで（スマホからも）見られる静的ショーケースです。

公開URL: **https://ma-garin.github.io/WebSpec2Doc/**

## 構成

| パス | 内容 |
|---|---|
| `index.html` | ランディング。操作動画・5ステップウォークスルー・レポート紹介 |
| `assets/flow-desktop.mp4` | 実機フロー動画（36秒・H.264・無音） |
| `assets/shots/` | 実機UIスクリーンショット（デスクトップ1440×900 / iPhone 13） |
| `sample/` | `docs/demo/sample_output/` のコピー + モバイル閲覧用CSS追記（report.html のみ） |

画像・動画は、同梱デモサイト DemoMart（`make demo` の 8766）を実際に解析した際のキャプチャです。

## 公開手順（初回のみ）

1. リポジトリの **Settings → Pages → Build and deployment → Source** を **GitHub Actions** にする
2. `main` に `pages/**` の変更が push されると `.github/workflows/pages.yml` が自動デプロイする
   （手動実行は Actions → Deploy GitHub Pages → Run workflow）

## キャプチャの更新方法

UIが変わったら、ローカルで `make demo` を起動した状態で Playwright スクリプトを流して
`assets/shots/` と `assets/flow-desktop.mp4` を差し替えてください。
撮影対象: ホーム → 画面分析 → 条件設定 → 解析実行 → レポート各タブ（1440×900、モバイルは iPhone 13 相当）。

## 注意

- ここは**閲覧専用のショーケース**です。解析の実行はできません（本体は Flask + Playwright のためサーバ実行が必要）。
- `sample/report.html` は生成物のコピーに `<style>` を1ブロック追記しています（モバイル閲覧補正）。生成物本体（`docs/demo/sample_output/`）は無改変です。
