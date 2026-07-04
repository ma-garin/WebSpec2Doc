"""ビジネスアイデア大会・実機デモ用の同梱デモサイト（DemoMart）。

外部サイトに依存せず、WebSpec2Doc の見せ場（認証・決済・必須フォーム・
モーダル等の画面状態・SPA遷移・robots 礼儀）が確実に再現できる構成の
静的サイトをローカル（既定ポート 8766）で配信する。

起動:
    python demo/demo_site.py            # http://127.0.0.1:8766
    make demo                           # 本体と同時起動（推奨）
"""

from __future__ import annotations

import argparse
from pathlib import Path

from flask import Flask, Response, send_from_directory

DEFAULT_PORT = 8766
SITE_DIR = Path(__file__).parent / "site"

app = Flask(__name__, static_folder=None)


@app.get("/")
def index() -> Response:
    """トップページを返す。"""
    return send_from_directory(SITE_DIR, "index.html")


@app.get("/robots.txt")
def robots() -> Response:
    """robots.txt（Crawl-Delay / Disallow のデモ用）を返す。"""
    return send_from_directory(SITE_DIR, "robots.txt", mimetype="text/plain")


@app.get("/<path:name>")
def page(name: str) -> Response:
    """静的ページを返す。拡張子なしのパスは .html を補完する。"""
    target = name if "." in name else f"{name}.html"
    return send_from_directory(SITE_DIR, target)


def main() -> None:
    global SITE_DIR
    parser = argparse.ArgumentParser(description="WebSpec2Doc デモサイト（DemoMart）")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="待受ポート")
    parser.add_argument(
        "--site-dir",
        default="site",
        help=(
            "配信するサイトディレクトリ名（demo/ 配下）。既定は 'site'（現行）。"
            "現新比較デモでは新側に 'site_v2' を指定する"
        ),
    )
    args = parser.parse_args()
    SITE_DIR = Path(__file__).parent / str(args.site_dir)
    print(f"DemoMart デモサイト（{SITE_DIR.name}）: http://127.0.0.1:{args.port}/")
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
