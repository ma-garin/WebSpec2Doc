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

## app/ — インタラクティブ・サンプルデモ（バックエンド不要）

`app/` は **本物の WebSpec2Doc フロントエンド**（`static/` の実資産＋サーバ描画済みHTML）を
GitHub Pages 上でそのまま動かすための静的バンドル。バックエンド（Flask + Playwright）は
使わず、`mock-backend.js` が `fetch` / `<img>.src` / `innerHTML` を横取りして、実サーバから
採取済みの応答（`fixtures/`）を**サンプル値として再生**する。

- 対象データ: 同梱デモ DemoMart を実際に解析した実測記録（`_build/harvest.py` で採取）
- 再生範囲: URL入力 → 画面分析(SSE) → 条件設定 → 解析(ライブ進捗・プレビュー) → レポート全タブ
- 公開URL: `https://ma-garin.github.io/WebSpec2Doc/app/`

### 再生成（UI変更時）

```bash
make demo   # 本体(8765)+デモ(8766)を起動した状態で
python pages/app/_build/harvest.py <capture_dir>     # 実通信を採取
python pages/app/_build/build.py <capture_dir>       # pages/app/ を再生成
```

`mock-backend.js` は手書き（採取に依存しない）。`static/` は実資産の無改変コピー。
