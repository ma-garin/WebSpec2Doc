"""OpenAPI 仕様を人が読めるHTMLへ変換する。

Swagger UI を同梱する案もあったが、この配布形態では外部からアセットを取得できず、
巨大なJSバンドルを抱えることになる。仕様はサーバ側でHTMLに描き切る方式にした。
JavaScript も外部ホストも使わないため、遮断された環境でもそのまま開ける。
"""

from __future__ import annotations

import html
from typing import Any

DOCS_TITLE = "WebSpec2Doc API リファレンス"

METHOD_COLORS = {
    "get": "#0F6E7E",
    "post": "#198038",
    "put": "#8D6B00",
    "delete": "#DA1E28",
    "patch": "#5C6875",
}


def render_openapi_docs(spec: dict[str, Any]) -> str:
    """仕様辞書から自己完結のリファレンスHTMLを生成する。"""
    info = spec.get("info", {})
    groups = _group_by_tag(spec.get("paths", {}))
    sections = "".join(_section(tag, entries) for tag, entries in groups)
    return f"""<!doctype html><html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(DOCS_TITLE)}</title>
<style>{_css()}</style>
</head><body>
<header>
<h1>{html.escape(str(info.get("title", DOCS_TITLE)))}</h1>
<p class="version">version {html.escape(str(info.get("version", "")))}
 &nbsp;|&nbsp; OpenAPI {html.escape(str(spec.get("openapi", "")))}</p>
<p class="desc">{html.escape(str(info.get("description", "")))}</p>
<p class="raw">機械可読な仕様: <a href="/api/v1/openapi.json">/api/v1/openapi.json</a></p>
</header>
<main>{sections}</main>
</body></html>"""


def _group_by_tag(paths: dict[str, Any]) -> list[tuple[str, list[tuple[str, str, dict]]]]:
    grouped: dict[str, list[tuple[str, str, dict]]] = {}
    for path, methods in paths.items():
        for method, operation in methods.items():
            tag = str((operation.get("tags") or ["api"])[0])
            grouped.setdefault(tag, []).append((path, method, operation))
    for entries in grouped.values():
        entries.sort(key=lambda item: (item[0], item[1]))
    return sorted(grouped.items())


def _section(tag: str, entries: list[tuple[str, str, dict]]) -> str:
    rows = "".join(_operation_block(path, method, operation) for path, method, operation in entries)
    return f"<section><h2>{html.escape(tag)}</h2>{rows}</section>"


def _operation_block(path: str, method: str, operation: dict[str, Any]) -> str:
    color = METHOD_COLORS.get(method, "#5C6875")
    params = operation.get("parameters") or []
    param_block = ""
    if params:
        items = "".join(
            f"<li><code>{html.escape(str(p.get('name', '')))}</code>"
            f" <span class='muted'>({html.escape(str(p.get('in', '')))}"
            f"{'・必須' if p.get('required') else ''})</span></li>"
            for p in params
        )
        param_block = f"<div class='sub'><b>パラメータ</b><ul>{items}</ul></div>"
    body_block = (
        "<div class='sub'><b>リクエストボディ</b> <span class='muted'>application/json</span></div>"
        if operation.get("requestBody")
        else ""
    )
    responses = operation.get("responses") or {}
    response_items = "".join(
        f"<li><code>{html.escape(str(code))}</code>"
        f" {html.escape(str(detail.get('description', '')))}</li>"
        for code, detail in sorted(responses.items())
    )
    return (
        "<article>"
        f"<div class='line'><span class='method' style='background:{color}'>"
        f"{html.escape(method.upper())}</span>"
        f"<code class='path'>{html.escape(path)}</code></div>"
        f"<p class='summary'>{html.escape(str(operation.get('summary', '')))}</p>"
        f"{param_block}{body_block}"
        f"<div class='sub'><b>応答</b><ul>{response_items}</ul></div>"
        "</article>"
    )


def _css() -> str:
    return """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif;color:#16202B;background:#f5f7f9;line-height:1.7}
header{background:#16202B;color:#fff;padding:1.6rem 2rem}
header h1{font-size:1.4rem}
.version{font-family:ui-monospace,Menlo,monospace;font-size:.8rem;opacity:.85;margin-top:.3rem}
.desc{margin-top:.6rem;font-size:.9rem;opacity:.92;max-width:70ch}
.raw{margin-top:.6rem;font-size:.85rem}
.raw a{color:#7FD4DE}
main{max-width:960px;margin:2rem auto;padding:0 1.5rem;display:flex;flex-direction:column;gap:1.5rem}
section{background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.08);overflow:hidden}
section h2{background:#eef2f5;padding:.7rem 1.2rem;font-size:.85rem;letter-spacing:.08em;text-transform:uppercase}
article{padding:1.1rem 1.2rem;border-bottom:1px solid #eef2f5}
article:last-child{border-bottom:none}
.line{display:flex;align-items:center;gap:.7rem;flex-wrap:wrap}
.method{color:#fff;font-family:ui-monospace,Menlo,monospace;font-size:.72rem;padding:2px 9px;border-radius:3px;letter-spacing:.05em}
.path{font-family:ui-monospace,Menlo,monospace;font-size:.9rem}
.summary{margin-top:.5rem;font-size:.92rem}
.sub{margin-top:.7rem;font-size:.86rem}
.sub ul{margin:.25rem 0 0 1.2rem}
.muted{color:#5C6875}
code{font-family:ui-monospace,Menlo,monospace}
"""
