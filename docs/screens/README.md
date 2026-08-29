# 画面カタログ（docs/screens/）

稼働中の WebSpec2Doc を実際に起動して撮影した、**全 91 画面**のスクリーンショット一覧。

- 一覧: [`index.html`](./index.html)（ブラウザで開く）
- 画像: `shots/*.webp`（1440px 幅・WebP q82。リサイズ以外の加工なし）
- 生成スクリプト: `scripts/screens/`

## 収録範囲

| 区分 | 件数 |
|---|---|
| 認証・オンボーディング | 8 |
| 入口（ルート / システム選択 / CLI） | 3 |
| System 01 ドキュメント作成 | 10 |
| System 01 / 実行結果タブ（3階層すべて展開） | 25 |
| System 01 / テスト観点タブ | 4 |
| System 02 テスト活動支援（12工程） | 12 |
| 共通（ガイド・参考・設定・アカウント・管理・フィードバック） | 7 |
| 共通 / 設定タブ | 8 |
| モーダル / オーバーレイ | 9 |
| 共通UI状態（ユーザーメニュー・サイドバー折りたたみ） | 2 |
| レスポンシブ（390×844） | 3 |
| **合計** | **91** |

## 収録していないもの（意図的な除外・未撮影）

- `demo/site/`・`demo/verify_site/` の 20 ページ — **解析対象**のサンプルサイトであり本システムの画面ではない
- `pages/` の GitHub Pages ショーケース — 製品 UI ではなく公開用 LP
- `/download`・`/download-zip`・`/open`・`/preview` — ファイルを返す経路（HTML 画面ではない）
- `/auth/account` → `/account`、`/admin/console` → `/user-management` — リダイレクト専用の旧 URL
- `/api/**`・`/metrics` — API エンドポイント
- **実行中・エラー中の動的状態**（クロール進行中の進捗、LLM 応答待ち、タイムアウト表示）— 外部サイトへの
  実クロールを伴うため **未撮影**。この一覧では確認していない

## 再生成手順

```bash
# 1) 表示用データ（同梱デモサイトの実解析結果）を output/ に置き、実行回を作る
mkdir -p output/demomart && cp -r docs/demo/sample_output/. output/demomart/
venv/bin/python - <<'PY'
from pathlib import Path
from datetime import datetime
from web.services.run_store import snapshot_run
print(snapshot_run(Path("output"), "demomart", event="crawl", status="complete",
                   summary={"pages": 9, "forms": 3},
                   now=datetime(2026, 8, 28, 14, 32, 10)))
PY

# 2) 本体アプリ（認証オフ）を 8765 で起動
kill $(lsof -ti:8765) 2>/dev/null; FLASK_TESTING=1 WEBSPEC2DOC_ALLOW_LOCAL=1 \
  WEBSPEC2DOC_AUTH_MODE=off nohup venv/bin/python app.py > /tmp/ws2d.log 2>&1 &
curl -s --retry 20 --retry-delay 1 --retry-connrefused -o /dev/null http://127.0.0.1:8765/

# 3) 認証画面用に、空の認証DBでログイン必須モードを 8766 で起動
rm -f /tmp/auth-demo.db
WEBSPEC2DOC_PORT=8766 WEBSPEC2DOC_AUTH_MODE=required WEBSPEC2DOC_AUTH_DB=/tmp/auth-demo.db \
  FLASK_TESTING=1 WEBSPEC2DOC_ALLOW_LOCAL=1 WEBSPEC2DOC_BOOTSTRAP_ADMIN=0 \
  nohup venv/bin/python app.py > /tmp/ws2d-auth.log 2>&1 &

# 4) 撮影 → カタログ生成（SHOTS は PNG の一時置き場）
SHOTS=/tmp/ws2d-shots
for s in 01_capture_app 02_capture_result_tabs 03_capture_auth 04_capture_ui_states 05_capture_deep_tabs; do
  venv/bin/python scripts/screens/$s.py $SHOTS
done
venv/bin/python scripts/screens/merge_and_convert.py $SHOTS   # manifest 統合 + WebP 変換
venv/bin/python scripts/screens/06_build_catalog.py $SHOTS    # docs/screens/index.html を生成
```

`03_capture_auth.py` は初回セットアップ（ユーザー 0 人の状態）から撮るため、
**空の認証DB**（手順 3 の `rm -f`）が前提。既存ユーザーがいると `/auth/setup` に到達できない。
