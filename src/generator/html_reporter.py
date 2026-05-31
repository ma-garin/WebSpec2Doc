from __future__ import annotations

import base64
import html
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import networkx as nx

from analyzer.html_analyzer import AnalyzedPage
from analyzer.test_conditions import derive_conditions
from crawler.page_crawler import DEFAULT_DEPTH, DEFAULT_MAX_PAGES, FieldData, FormData

REPORT_TITLE = "WebSpec2Doc テスト分析インプット"
TOOL_NAME = "WebSpec2Doc"
SCREENSHOT_EXT = ".png"
MAX_SCREENSHOT_BYTES = 500_000
SIDEBAR_TITLE_LIMIT = 22


def generate_html_report(
    pages: list[AnalyzedPage],
    graph: nx.DiGraph,
    form_summary: list[dict],
    target_url: str,
    mermaid_content: str,
    screenshots_dir: Path | None = None,
    crawl_depth: int = DEFAULT_DEPTH,
    crawl_max_pages: int = DEFAULT_MAX_PAGES,
    crawled_at: str = "",
) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    forms_count = sum(len(p.page_data.forms) for p in pages)
    fields_count = len(form_summary)
    buttons_count = sum(len(p.page_data.buttons) for p in pages)

    return "\n".join(
        [
            _html_head(),
            '<body class="app-page"><div class="app-shell">',
            _sidebar(pages),
            '<div class="app-main">',
            _topbar(target_url, now),
            '<main class="app-content">',
            _section(
                "サマリー",
                _summary_cards(len(pages), forms_count, fields_count, buttons_count),
                "summary",
            ),
            _section("画面遷移図", _mermaid_block(mermaid_content), "transition"),
            _section("画面カタログ", _screen_cards(pages, graph, screenshots_dir), "screens"),
            _meta_section(target_url, crawl_depth, crawl_max_pages, crawled_at, len(pages)),
            _footer(now),
            "</main></div></div>",
            _scrollspy_script(),
            _mermaid_script(),
            "</body></html>",
        ]
    )


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
    return """
*{box-sizing:border-box;margin:0;padding:0}
:root{--primary:#0F62FE;--primary-dark:#0043CE;--text:#161616;--text-muted:#525252;
--bg:#F4F8FF;--surface:#fff;--surface-soft:#F7FBFF;--border:#C9D9EE;--ok:#198038;
--critical:#DA1E28;--info-bg:#EDF5FF;--info-border:#A6C8FF;--radius:8px}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Hiragino Sans','Noto Sans JP',sans-serif;
color:var(--text);background:var(--bg);line-height:1.6;font-size:15px}
body.app-page{overflow:hidden}
.app-shell{height:100vh;display:grid;grid-template-columns:260px minmax(0,1fr)}
.app-sidebar{height:100vh;overflow:auto;padding:20px 14px;background:#EDF5FF;border-right:1px solid var(--border)}
.app-brand{font-size:19px;font-weight:700;color:var(--text)}
.brand-sub{font-size:11px;color:var(--text-muted);margin-bottom:16px}
.app-nav{display:grid;gap:3px}
.nav-item{display:block;padding:.4rem .6rem;border-radius:6px;color:var(--text);text-decoration:none;
font-size:13px;border:1px solid transparent}
.nav-item:hover{background:#fff;border-color:var(--info-border)}
.nav-item.is-active{background:#fff;border-color:var(--info-border);color:var(--primary-dark);
box-shadow:inset 3px 0 0 var(--primary);font-weight:600}
.nav-sub{padding-left:1.1rem;font-size:12px;color:var(--text-muted)}
.nav-sub.is-active{color:var(--primary-dark)}
.nav-group{font-size:10px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;
color:var(--text-muted);padding:.6rem .6rem .2rem}
.app-main{min-width:0;height:100vh;display:flex;flex-direction:column}
.app-topbar{display:flex;align-items:center;justify-content:space-between;gap:16px;
padding:16px 28px;border-bottom:1px solid var(--border);background:rgba(247,251,255,.96);flex-shrink:0}
.kicker{font-size:11px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:var(--text-muted)}
.topbar-title{font-size:21px;font-weight:700;line-height:1.2}
.topbar-meta{font-size:12px;color:var(--text-muted);text-align:right}
.topbar-meta a{color:var(--primary)}
.app-content{flex:1;overflow:auto;padding:24px 28px;scroll-behavior:smooth}
.block{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
margin-bottom:20px;box-shadow:0 1px 2px rgba(22,22,22,.05);overflow:hidden}
.block>h2{font-size:14px;font-weight:700;padding:.7rem 1.1rem;border-bottom:1px solid var(--border);
background:var(--surface-soft);color:var(--primary-dark)}
.block-body{padding:1.1rem;overflow-x:auto}
.cards{display:flex;gap:1rem;flex-wrap:wrap}
.card{flex:1;min-width:120px;background:var(--surface-soft);border:1px solid var(--info-border);
border-radius:var(--radius);padding:1rem;text-align:center}
.card .num{font-size:1.9rem;font-weight:700;color:var(--primary-dark)}
.card .label{font-size:.8rem;color:var(--text-muted);margin-top:.2rem}
table{border-collapse:collapse;width:100%;font-size:.85rem}
th{background:var(--primary);color:#fff;padding:.5rem .7rem;text-align:left;white-space:nowrap}
td{padding:.5rem .7rem;border-bottom:1px solid #eef;vertical-align:top}
tr:nth-child(even) td{background:var(--surface-soft)}
.badge-yes{color:var(--critical);font-weight:600}
.mermaid-wrap{overflow-x:auto;padding:.5rem}
.screen{border:1px solid var(--border);border-radius:var(--radius);margin-bottom:1.3rem;overflow:hidden}
.screen-head{display:flex;align-items:baseline;gap:.8rem;background:var(--info-bg);
padding:.6rem 1rem;border-bottom:1px solid var(--border);flex-wrap:wrap}
.screen-head .pid{font-weight:700;color:var(--primary-dark)}
.screen-head .title{font-weight:600}
.screen-head .url{color:var(--text-muted);font-size:.8rem;margin-left:auto;word-break:break-all}
.screen-body{display:grid;grid-template-columns:300px 1fr;gap:1rem;padding:1rem}
.screen-shot img{width:100%;border:1px solid var(--border);border-radius:6px;display:block}
.screen-shot .noshot{color:var(--text-muted);font-size:.8rem;padding:1rem;border:1px dashed var(--border);
border-radius:6px;text-align:center}
.screen-info{min-width:0}
.subhead{font-size:.8rem;font-weight:700;color:var(--primary-dark);margin:.8rem 0 .3rem;
border-left:3px solid var(--primary);padding-left:.5rem}
.subhead:first-child{margin-top:0}
.chips{display:flex;flex-wrap:wrap;gap:.4rem}
.chip{background:var(--info-bg);border:1px solid var(--info-border);border-radius:4px;
padding:.15rem .5rem;font-size:.78rem}
.muted{color:var(--text-muted);font-size:.8rem}
.cond{color:#0a6b3a;font-size:.78rem;white-space:pre-line}
.locator{color:#5a3d8a;font-size:.72rem;font-family:monospace;word-break:break-all}
.form-meta{font-size:.78rem;color:var(--text-muted);margin-bottom:.3rem}
.site-footer{text-align:center;color:var(--text-muted);font-size:.78rem;padding:1rem 0 2rem}
.meta-table td{white-space:normal}
@media(max-width:760px){.screen-body{grid-template-columns:1fr}}
@media print{
body.app-page{overflow:visible}
.app-shell{display:block;height:auto}
.app-sidebar{display:none}
.app-main{height:auto}
.app-topbar{position:static}
.app-content{overflow:visible;height:auto;padding:0}
.screen{break-inside:avoid}
.block{box-shadow:none}
}
"""


def _sidebar(pages: list[AnalyzedPage]) -> str:
    items = [
        '<a href="#summary" class="nav-item">サマリー</a>',
        '<a href="#transition" class="nav-item">画面遷移図</a>',
        '<div class="nav-group">画面一覧</div>',
    ]
    for page in pages:
        pid = html.escape(page.page_id)
        raw = page.page_data.title or _url_path(page.page_data.url)
        title = html.escape(raw[:SIDEBAR_TITLE_LIMIT])
        items.append(f'<a href="#{pid}" class="nav-item nav-sub">{pid} {title}</a>')
    items.append('<a href="#meta" class="nav-item">メタ情報</a>')
    return (
        '<aside class="app-sidebar"><div class="app-brand">WebSpec2Doc</div>'
        '<div class="brand-sub">テスト分析インプット</div>'
        '<nav class="app-nav">' + "".join(items) + "</nav></aside>"
    )


def _topbar(target_url: str, now: str) -> str:
    esc = html.escape(target_url)
    return (
        '<header class="app-topbar"><div>'
        '<div class="kicker">Test Analysis Input</div>'
        f'<div class="topbar-title">{REPORT_TITLE}</div></div>'
        f'<div class="topbar-meta"><a href="{esc}" target="_blank">{esc}</a><br><span>{now}</span></div>'
        "</header>"
    )


def _summary_cards(pages: int, forms: int, fields: int, buttons: int) -> str:
    def card(num: int, label: str) -> str:
        return (
            f'<div class="card"><div class="num">{num}</div><div class="label">{label}</div></div>'
        )

    return (
        '<div class="cards">'
        + card(pages, "画面数")
        + card(forms, "フォーム数")
        + card(fields, "入力項目数")
        + card(buttons, "操作要素数")
        + "</div>"
    )


def _section(title: str, body: str, anchor: str = "") -> str:
    aid = f' id="{anchor}"' if anchor else ""
    return f'<section class="block"{aid}><h2>{html.escape(title)}</h2><div class="block-body">{body}</div></section>'


def _mermaid_block(content: str) -> str:
    return f'<div class="mermaid-wrap"><pre class="mermaid">{html.escape(content)}</pre></div>'


def _screen_cards(
    pages: list[AnalyzedPage], graph: nx.DiGraph, screenshots_dir: Path | None
) -> str:
    return "".join(_screen_card(page, graph, screenshots_dir) for page in pages)


def _screen_card(page: AnalyzedPage, graph: nx.DiGraph, screenshots_dir: Path | None) -> str:
    pid = html.escape(page.page_id)
    title = html.escape(page.page_data.title or "")
    url_path = html.escape(_url_path(page.page_data.url))
    info = (
        _headings_block(page.page_data.headings)
        + _forms_block(page.page_data.forms)
        + _buttons_block(page.page_data.buttons)
        + _transitions_block(page.page_id, graph)
    )
    return (
        f'<div class="screen" id="{pid}">'
        f'<div class="screen-head"><span class="pid">{pid}</span>'
        f'<span class="title">{title}</span><span class="url">{url_path}</span></div>'
        f'<div class="screen-body"><div class="screen-shot">{_screenshot_img(page, screenshots_dir)}</div>'
        f'<div class="screen-info">{info}</div></div>'
        "</div>"
    )


def _screenshot_img(page: AnalyzedPage, screenshots_dir: Path | None) -> str:
    if screenshots_dir is None:
        return '<div class="noshot">スクリーンショットなし</div>'
    png = screenshots_dir / f"{page.page_id}{SCREENSHOT_EXT}"
    if not png.exists() or png.stat().st_size > MAX_SCREENSHOT_BYTES:
        return '<div class="noshot">スクリーンショットなし</div>'
    b64 = base64.b64encode(png.read_bytes()).decode("ascii")
    return (
        f'<img src="data:image/png;base64,{b64}" alt="{html.escape(page.page_id)}" loading="lazy">'
    )


def _headings_block(headings: tuple[str, ...]) -> str:
    if not headings:
        return ""
    chips = "".join(f'<span class="chip">{html.escape(h)}</span>' for h in headings[:12])
    return f'<div class="subhead">画面構成（見出し）</div><div class="chips">{chips}</div>'


def _forms_block(forms: tuple[FormData, ...]) -> str:
    if not forms:
        return '<div class="subhead">入力項目</div><div class="muted">フォームなし</div>'
    blocks = ['<div class="subhead">入力項目・テスト条件</div>']
    for i, form in enumerate(forms, 1):
        action = html.escape(form.action or "(同一URL)")
        method = html.escape(form.method.upper())
        blocks.append(f'<div class="form-meta">フォーム{i}: {method} → {action}</div>')
        blocks.append(
            "<table><thead><tr>"
            "<th>項目名</th><th>型</th><th>必須</th><th>制約</th><th>既定/選択肢</th>"
            "<th>ロケータ候補</th><th>導出テスト条件</th>"
            "</tr></thead><tbody>" + _field_rows(form) + "</tbody></table>"
        )
    return "".join(blocks)


def _field_rows(form: FormData) -> str:
    radio_values: dict[str, list[str]] = {}
    for field in form.fields:
        if field.field_type == "radio" and field.name:
            radio_values.setdefault(field.name, []).append(field.default)
    rendered: set[str] = set()
    rows: list[str] = []
    for field in form.fields:
        if field.field_type == "radio" and field.name:
            if field.name in rendered:
                continue
            rendered.add(field.name)
            field = replace(field, options=tuple(radio_values[field.name]))
        rows.append(_field_row(field))
    return "".join(rows)


def _field_row(field: FieldData) -> str:
    name = html.escape(field.name or "(無名)")
    ftype = html.escape(field.field_type)
    req = '<span class="badge-yes">必須</span>' if field.required else "-"
    constraints = html.escape(_constraints_text(field)) or "-"
    default_opts = html.escape(_default_options_text(field)) or "-"
    locators = html.escape(" / ".join(_locator_candidates(field))) or "-"
    conditions = html.escape("\n".join(derive_conditions(field)))
    return (
        f"<tr><td>{name}</td><td>{ftype}</td><td>{req}</td>"
        f"<td>{constraints}</td><td>{default_opts}</td>"
        f'<td class="locator">{locators}</td>'
        f'<td class="cond">{conditions}</td></tr>'
    )


def _constraints_text(field) -> str:
    parts: list[str] = []
    if field.maxlength is not None:
        parts.append(f"最大{field.maxlength}文字")
    if field.minlength is not None:
        parts.append(f"最小{field.minlength}文字")
    if field.min_value:
        parts.append(f"min={field.min_value}")
    if field.max_value:
        parts.append(f"max={field.max_value}")
    if field.pattern:
        parts.append(f"pattern={field.pattern}")
    if field.placeholder:
        parts.append(f"例: {field.placeholder}")
    return " / ".join(parts)


def _default_options_text(field) -> str:
    if field.options:
        shown = ", ".join(o for o in field.options if o)
        return shown[:120] or "(空の選択肢)"
    return field.default


def _buttons_block(buttons: tuple[str, ...]) -> str:
    if not buttons:
        return ""
    chips = "".join(f'<span class="chip">{html.escape(b)}</span>' for b in buttons[:20])
    return f'<div class="subhead">操作要素（ボタン）</div><div class="chips">{chips}</div>'


def _transitions_block(page_id: str, graph: nx.DiGraph) -> str:
    if not graph.has_node(page_id):
        return ""
    succ = [s for s in graph.successors(page_id) if s != page_id]
    pred = [p for p in graph.predecessors(page_id) if p != page_id]
    succ_text = html.escape(", ".join(succ)) if succ else "なし"
    pred_text = html.escape(", ".join(pred)) if pred else "なし"
    return (
        '<div class="subhead">画面遷移</div>'
        f'<div class="muted">遷移先: {succ_text}<br>遷移元: {pred_text}</div>'
    )


def _locator_candidates(field: FieldData) -> list[str]:
    candidates: list[str] = []
    if field.element_id:
        candidates.append(f"#{field.element_id}")
    if field.name:
        tag = (
            "select"
            if field.field_type == "select"
            else ("textarea" if field.field_type == "textarea" else "input")
        )
        candidates.append(f'{tag}[name="{field.name}"]')
    return candidates


def _meta_section(
    target_url: str,
    crawl_depth: int,
    crawl_max_pages: int,
    crawled_at: str,
    page_count: int,
) -> str:
    crawled_at_cell = html.escape(crawled_at) if crawled_at else "（記録なし）"
    body = (
        '<table class="meta-table"><tbody>'
        f"<tr><th>対象URL</th><td>{html.escape(target_url)}</td></tr>"
        f"<tr><th>クロール条件</th><td>深度: {crawl_depth} / 最大ページ数: {crawl_max_pages} / 取得ページ数: {page_count}</td></tr>"
        f"<tr><th>実行日時</th><td>{crawled_at_cell}</td></tr>"
        "<tr><th>実行環境</th><td>クロール: Chromium (Playwright) / 本文書は稼働システムから自動生成</td></tr>"
        "<tr><th>改訂履歴</th><td>（レビュー時に追記）</td></tr>"
        "<tr><th>レビュー</th><td>レビュー者・承認日（第三者レビュー記入欄）</td></tr>"
        "<tr><th>制約</th><td>ログイン後ページは --auth 指定時のみ取得。JS動的生成リンクは取得漏れの可能性あり。"
        "テスト条件は制約からの機械導出候補であり、要件に基づく精査が必要。</td></tr>"
        "</tbody></table>"
    )
    return _section("メタ情報・トレーサビリティ", body, "meta")


def _footer(now: str) -> str:
    return f'<footer class="site-footer">{html.escape(TOOL_NAME)} &mdash; {now}</footer>'


def _scrollspy_script() -> str:
    return (
        "<script>"
        "const obs=new IntersectionObserver((es)=>{es.forEach(e=>{if(e.isIntersecting){"
        "document.querySelectorAll('.nav-item').forEach(n=>"
        "n.classList.toggle('is-active',n.getAttribute('href')==='#'+e.target.id));}});},"
        "{root:document.querySelector('.app-content'),rootMargin:'-35% 0px -60% 0px'});"
        "document.querySelectorAll('section.block,.screen').forEach(s=>{if(s.id)obs.observe(s);});"
        "</script>"
    )


def _mermaid_script() -> str:
    return (
        '<script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>'
        "<script>mermaid.initialize({startOnLoad:true,theme:'default'});</script>"
    )


def _url_path(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path or "/"
