from __future__ import annotations

import base64
import html
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import networkx as nx

from analyzer.html_analyzer import AnalyzedPage

REPORT_TITLE = "WebSpec2Doc レポート"
TOOL_NAME = "WebSpec2Doc"
NAVY = "#00285E"
CYAN = "#009FCA"
GRAY = "#F5F5F5"
TEXT = "#333333"
SCREENSHOT_EXT = ".png"
MAX_SCREENSHOT_BYTES = 500_000  # 500KB超は埋め込まずスキップ


def generate_html_report(
    pages: list[AnalyzedPage],
    graph: nx.DiGraph,
    form_summary: list[dict],
    target_url: str,
    mermaid_content: str,
    screenshots_dir: Path | None = None,
) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    forms_count = sum(len(p.page_data.forms) for p in pages)
    fields_count = len(form_summary)

    sections = [
        _section("画面遷移図", _mermaid_block(mermaid_content)),
        _section("画面一覧", _screens_table(pages, graph)),
        _section("フォーム・入力項目一覧", _forms_table(form_summary)),
    ]
    if screenshots_dir is not None:
        sections.append(_section("スクリーンショット", _screenshots_grid(pages, screenshots_dir)))

    return "\n".join([
        _html_head(),
        "<body>",
        _header(target_url, now),
        '<main class="container">',
        _summary_cards(len(pages), forms_count, fields_count),
        *sections,
        "</main>",
        _footer(now),
        _mermaid_script(),
        "</body></html>",
    ])


def _html_head() -> str:
    return (
        '<!doctype html><html lang="ja"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{REPORT_TITLE}</title>"
        f"<style>{_css()}</style>"
        "</head>"
    )


def _css() -> str:
    return f"""
:root{{--navy:{NAVY};--cyan:{CYAN};--gray:{GRAY};--text:{TEXT}}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:"Noto Sans JP","Meiryo",sans-serif;color:var(--text);background:var(--gray)}}
.site-header{{background:var(--navy);color:#fff;padding:1.2rem 2rem}}
.site-header h1{{font-size:1.4rem;font-weight:700}}
.site-header .meta{{font-size:.85rem;opacity:.8;margin-top:.3rem}}
.container{{max-width:1200px;margin:2rem auto;padding:0 1.5rem}}
.cards{{display:flex;gap:1rem;margin-bottom:2rem;flex-wrap:wrap}}
.card{{flex:1;min-width:150px;background:#fff;border:2px solid var(--cyan);border-radius:8px;padding:1rem 1.5rem;text-align:center}}
.card .num{{font-size:2rem;font-weight:700;color:var(--navy)}}
.card .label{{font-size:.85rem;color:#666;margin-top:.2rem}}
section{{background:#fff;border-radius:8px;margin-bottom:2rem;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
section h2{{background:var(--navy);color:#fff;padding:.8rem 1.2rem;font-size:1rem}}
.section-body{{padding:1.2rem;overflow-x:auto}}
table{{border-collapse:collapse;width:100%;font-size:.9rem}}
th{{background:var(--navy);color:#fff;padding:.6rem .8rem;text-align:left;white-space:nowrap}}
td{{padding:.55rem .8rem;border-bottom:1px solid #eee;vertical-align:top}}
tr:last-child td{{border-bottom:none}}
tr:nth-child(even) td{{background:#f9f9f9}}
.badge-yes{{color:#c00;font-weight:600}}
.mermaid-wrap{{overflow-x:auto;padding:.5rem}}
.ss-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1rem}}
.ss-card{{border:1px solid #ddd;border-radius:6px;overflow:hidden;background:#fff}}
.ss-card img{{width:100%;display:block;border-bottom:1px solid #eee}}
.ss-card .ss-info{{padding:.5rem .7rem;font-size:.8rem;line-height:1.5}}
.ss-card .ss-info strong{{color:var(--navy)}}
.site-footer{{text-align:center;color:#999;font-size:.8rem;padding:1.5rem;margin-top:1rem}}
"""


def _header(target_url: str, now: str) -> str:
    escaped = html.escape(target_url)
    return (
        '<header class="site-header">'
        f"<h1>{REPORT_TITLE}</h1>"
        f'<div class="meta">対象URL: <a href="{escaped}" style="color:#7dcfea">{escaped}</a>'
        f" &nbsp;|&nbsp; 生成日時: {now}</div>"
        "</header>"
    )


def _summary_cards(pages: int, forms: int, fields: int) -> str:
    def card(num: int | str, label: str) -> str:
        return f'<div class="card"><div class="num">{num}</div><div class="label">{label}</div></div>'

    return (
        '<div class="cards">'
        + card(pages, "画面数")
        + card(forms, "フォーム数")
        + card(fields, "フィールド数")
        + "</div>"
    )


def _section(title: str, body: str) -> str:
    return (
        "<section>"
        f"<h2>{html.escape(title)}</h2>"
        f'<div class="section-body">{body}</div>'
        "</section>"
    )


def _mermaid_block(content: str) -> str:
    return f'<div class="mermaid-wrap"><pre class="mermaid">{html.escape(content)}</pre></div>'


def _screens_table(pages: list[AnalyzedPage], graph: nx.DiGraph) -> str:
    rows = [
        "<table><thead><tr>"
        "<th>#</th><th>画面ID</th><th>URL</th><th>タイトル</th><th>フォーム数</th><th>遷移先</th>"
        "</tr></thead><tbody>"
    ]
    for i, page in enumerate(pages, 1):
        page_id = html.escape(page.page_id)
        url_path = html.escape(_url_path(page.page_data.url))
        title = html.escape(page.page_data.title or "")
        forms_cnt = len(page.page_data.forms)
        successors = ", ".join(graph.successors(page.page_id)) if graph.has_node(page.page_id) else ""
        rows.append(
            f"<tr><td>{i}</td><td>{page_id}</td><td>{url_path}</td>"
            f"<td>{title}</td><td>{forms_cnt}</td><td>{html.escape(successors)}</td></tr>"
        )
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _forms_table(form_summary: list[dict]) -> str:
    if not form_summary:
        return "<p style='color:#999'>フォームはありません</p>"
    rows = [
        "<table><thead><tr>"
        "<th>画面ID</th><th>フィールド名</th><th>型</th><th>必須</th><th>placeholder</th>"
        "</tr></thead><tbody>"
    ]
    for item in form_summary:
        page_id = html.escape(str(item.get("page_id", "")))
        name = html.escape(str(item.get("name", "")))
        ftype = html.escape(str(item.get("field_type", "")))
        required = item.get("required", False)
        req_cell = '<span class="badge-yes">Yes</span>' if required else "No"
        placeholder = html.escape(str(item.get("placeholder", "") or "-"))
        rows.append(
            f"<tr><td>{page_id}</td><td>{name}</td><td>{ftype}</td>"
            f"<td>{req_cell}</td><td>{placeholder}</td></tr>"
        )
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _screenshots_grid(pages: list[AnalyzedPage], screenshots_dir: Path) -> str:
    items: list[str] = []
    for page in pages:
        png = screenshots_dir / f"{page.page_id}{SCREENSHOT_EXT}"
        if not png.exists():
            continue
        if png.stat().st_size > MAX_SCREENSHOT_BYTES:
            continue  # フルページキャプチャ等で肥大化したファイルはスキップ
        b64 = base64.b64encode(png.read_bytes()).decode("ascii")
        page_id = html.escape(page.page_id)
        url_path = html.escape(_url_path(page.page_data.url))
        title = html.escape(page.page_data.title or "")
        items.append(
            f'<div class="ss-card">'
            f'<img src="data:image/png;base64,{b64}" alt="{page_id}" loading="lazy">'
            f'<div class="ss-info"><strong>{page_id}</strong> {url_path}'
            f"<br><small>{title}</small></div>"
            f"</div>"
        )
    if not items:
        return "<p style='color:#999'>スクリーンショットはありません</p>"
    return '<div class="ss-grid">' + "".join(items) + "</div>"


def _footer(now: str) -> str:
    return f'<footer class="site-footer">{html.escape(TOOL_NAME)} &mdash; {now}</footer>'


def _mermaid_script() -> str:
    return (
        '<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>'
        "<script>mermaid.initialize({startOnLoad:true,theme:'default'});</script>"
    )


def _url_path(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path or "/"
