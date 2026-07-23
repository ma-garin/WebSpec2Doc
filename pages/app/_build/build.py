"""静的アプリバンドルのビルド。

入力:
  - <repo>/static/                 実アプリの静的資産（本物・無改変で配置）
  - <capture_dir>/index.captured.html   GET / のサーバ描画HTML
  - <capture_dir>/fixtures.json         採取API応答（{ "METHOD /path": [ {status,ct,body?,blob?} ] }）
  - <capture_dir>/assets/               採取バイナリ（画像等）

出力（pages/app/ 配下）:
  - index.html                     絶対パス /static を相対化し mock-backend を先頭注入したもの
  - static/                        実資産のコピー
  - fixtures/manifest.js           window.__FIXTURES__ = {...}
  - fixtures/assets/               バイナリ資産

使い方:
  python pages/app/_build/build.py <capture_dir>
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
APP = REPO / "pages" / "app"
CAP = Path(sys.argv[1]).resolve()


def main() -> None:
    # 1) 実アプリ static/ をコピー（本物・無改変）
    dst_static = APP / "static"
    if dst_static.exists():
        shutil.rmtree(dst_static)
    shutil.copytree(REPO / "static", dst_static)

    # 2) fixtures 整形
    fx = json.loads((CAP / "fixtures.json").read_text(encoding="utf-8"))
    fx.pop("GET /", None)  # 画面HTMLは index.html として別配置するため不要
    (APP / "fixtures" / "assets").mkdir(parents=True, exist_ok=True)
    blob_count = 0
    for _key, entries in fx.items():
        for e in entries:
            if "blob" in e:
                src = CAP / e["blob"]
                name = Path(e["blob"]).name
                shutil.copy(src, APP / "fixtures" / "assets" / name)
                e["blob"] = f"fixtures/assets/{name}"
                blob_count += 1
    manifest = "window.__FIXTURES__ = " + json.dumps(fx, ensure_ascii=False) + ";\n"
    (APP / "fixtures" / "manifest.js").write_text(manifest, encoding="utf-8")

    # 3) 画面HTMLの絶対パス /static を相対化し、フックを先頭注入
    html = (CAP / "index.captured.html").read_text(encoding="utf-8")
    html = html.replace('="/static/', '="static/').replace("='/static/", "='static/")
    html = html.replace("url(/static/", "url(static/")
    html = html.replace('="/favicon', '="favicon').replace("href=\"/static", "href=\"static")
    inject = (
        '<script src="fixtures/manifest.js"></script>\n'
        '<script src="mock-backend.js"></script>\n'
    )
    if "<head>" in html:
        html = html.replace("<head>", "<head>\n" + inject, 1)
    else:
        html = inject + html
    (APP / "index.html").write_text(html, encoding="utf-8")

    # 検証: 相対化漏れ（残存する絶対 /static）を検出
    leftover = len(re.findall(r'["\'(]/static/', html))
    print(f"static files copied, fixtures endpoints={len(fx)}, blobs={blob_count}")
    print(f"index.html written ({len(html)} bytes), residual '/static' refs={leftover}")
    if leftover:
        print("WARNING: 絶対パス /static が残っています")


if __name__ == "__main__":
    main()
