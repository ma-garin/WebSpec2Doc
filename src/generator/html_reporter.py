from __future__ import annotations

import base64
import html
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import networkx as nx

from analyzer.html_analyzer import AnalyzedPage
from analyzer.test_conditions import derive_conditions
from crawler.page_crawler import FormData

REPORT_TITLE = "WebSpec2Doc テスト分析インプット"
TOOL_NAME = "WebSpec2Doc"
NAVY = "#00285E"
CYAN = "#009FCA"
GRAY = "#F5F5F5"
TEXT = "#333333"
SCREENSHOT_EXT = ".png"
MAX_SCREENSHOT_BYTES = 500_000


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
    buttons_count = sum(len(p.page_data.buttons) for p in pages)

    return "\n".join([
        _html_head(),
        "<body>",
        _header(target_url, now),
        '<main class="container">',
        _summary_cards(len(pages), forms_count, fields_count, buttons_count),
        _section("目次", _toc(pages)),
        _section("画面遷移図", _mermaid_block(mermaid_content)),
        _section("画面カタログ", _screen_cards(pages, graph, screenshots_dir)),
        _meta_section(),
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
body{{font-family:"Noto Sans JP","Meiryo",sans-serif;color:var(--text);background:var(--gray);line-height:1.6}}
.site-header{{background:var(--navy);color:#fff;padding:1.2rem 2rem}}
.site-header h1{{font-size:1.4rem;font-weight:700}}
.site-header .meta{{font-size:.85rem;opacity:.85;margin-top:.3rem}}
.container{{max-width:1200px;margin:2rem auto;padding:0 1.5rem}}
.cards{{display:flex;gap:1rem;margin-bottom:2rem;flex-wrap:wrap}}
.card{{flex:1;min-width:130px;background:#fff;border:2px solid var(--cyan);border-radius:8px;padding:1rem 1.5rem;text-align:center}}
.card .num{{font-size:2rem;font-weight:700;color:var(--navy)}}
.card .label{{font-size:.85rem;color:#666;margin-top:.2rem}}
section{{background:#fff;border-radius:8px;margin-bottom:2rem;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
section>h2{{background:var(--navy);color:#fff;padding:.8rem 1.2rem;font-size:1rem}}
.section-body{{padding:1.2rem;overflow-x:auto}}
.toc{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:.5rem}}
.toc a{{display:block;padding:.5rem .7rem;border:1px solid #ddd;border-radius:6px;text-decoration:none;color:var(--navy);font-size:.85rem}}
.toc a:hover{{border-color:var(--cyan);background:#f0fafe}}
.toc a b{{color:var(--cyan)}}
table{{border-collapse:collapse;width:100%;font-size:.85rem}}
th{{background:var(--navy);color:#fff;padding:.5rem .7rem;text-align:left;white-space:nowrap}}
td{{padding:.5rem .7rem;border-bottom:1px solid #eee;vertical-align:top}}
tr:nth-child(even) td{{background:#f9f9f9}}
.badge-yes{{color:#c00;font-weight:600}}
.mermaid-wrap{{overflow-x:auto;padding:.5rem}}
.screen{{border:1px solid #e2e2e2;border-radius:8px;margin-bottom:1.5rem;overflow:hidden}}
.screen-head{{display:flex;align-items:baseline;gap:.8rem;background:#eef4fb;padding:.7rem 1rem;border-bottom:1px solid #dde;flex-wrap:wrap}}
.screen-head .pid{{font-weight:700;color:var(--navy);font-size:1rem}}
.screen-head .title{{font-weight:600}}
.screen-head .url{{color:#777;font-size:.8rem;margin-left:auto;word-break:break-all}}
.screen-body{{display:grid;grid-template-columns:300px 1fr;gap:1rem;padding:1rem}}
.screen-shot img{{width:100%;border:1px solid #eee;border-radius:6px;display:block}}
.screen-shot .noshot{{color:#999;font-size:.8rem;padding:1rem;border:1px dashed #ccc;border-radius:6px;text-align:center}}
.screen-info{{min-width:0}}
.subhead{{font-size:.8rem;font-weight:700;color:var(--navy);margin:.8rem 0 .3rem;border-left:3px solid var(--cyan);padding-left:.5rem}}
.subhead:first-child{{margin-top:0}}
.chips{{display:flex;flex-wrap:wrap;gap:.4rem}}
.chip{{background:#eef4fb;border:1px solid #cfe0f0;border-radius:4px;padding:.15rem .5rem;font-size:.78rem}}
.muted{{color:#999;font-size:.8rem}}
.cond{{color:#0a6b3a;font-size:.78rem;white-space:pre-line}}
.form-meta{{font-size:.78rem;color:#666;margin-bottom:.3rem}}
.site-footer{{text-align:center;color:#999;font-size:.8rem;padding:1.5rem}}
.meta-table td{{white-space:normal}}
@media(max-width:760px){{.screen-body{{grid-template-columns:1fr}}}}
"""


def _header(target_url: str, now: str) -> str:
    escaped = html.escape(target_url)
    return (
        '<header class="site-header">'
        f"<h1>{REPORT_TITLE}</h1>"
        f'<div class="meta">対象システム: <a href="{escaped}" style="color:#7dcfea">{escaped}</a>'
        f" &nbsp;|&nbsp; 生成日時: {now}</div>"
        "</header>"
    )


def _summary_cards(pages: int, forms: int, fields: int, buttons: int) -> str:
    def card(num: int, label: str) -> str:
        return f'<div class="card"><div class="num">{num}</div><div class="label">{label}</div></div>'

    return (
        '<div class="cards">'
        + card(pages, "画面数")
        + card(forms, "フォーム数")
        + card(fields, "入力項目数")
        + card(buttons, "操作要素数")
        + "</div>"
    )


def _section(title: str, body: str) -> str:
    return f'<section><h2>{html.escape(title)}</h2><div class="section-body">{body}</div></section>'


def _toc(pages: list[AnalyzedPage]) -> str:
    links = []
    for page in pages:
        pid = html.escape(page.page_id)
        title = html.escape(page.page_data.title or _url_path(page.page_data.url))
        links.append(f'<a href="#{pid}"><b>{pid}</b> {title}</a>')
    return '<div class="toc">' + "".join(links) + "</div>"


def _mermaid_block(content: str) -> str:
    return f'<div class="mermaid-wrap"><pre class="mermaid">{html.escape(content)}</pre></div>'


def _screen_cards(pages: list[AnalyzedPage], graph: nx.DiGraph, screenshots_dir: Path | None) -> str:
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
    return f'<img src="data:image/png;base64,{b64}" alt="{html.escape(page.page_id)}" loading="lazy">'


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
            "<th>項目名</th><th>型</th><th>必須</th><th>制約</th><th>既定/選択肢</th><th>導出テスト条件</th>"
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


def _field_row(field) -> str:
    name = html.escape(field.name or "(無名)")
    ftype = html.escape(field.field_type)
    req = '<span class="badge-yes">必須</span>' if field.required else "-"
    constraints = html.escape(_constraints_text(field)) or "-"
    default_opts = html.escape(_default_options_text(field)) or "-"
    conditions = html.escape("\n".join(derive_conditions(field)))
    return (
        f"<tr><td>{name}</td><td>{ftype}</td><td>{req}</td>"
        f"<td>{constraints}</td><td>{default_opts}</td>"
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


def _meta_section() -> str:
    body = (
        '<table class="meta-table"><tbody>'
        "<tr><th>改訂履歴</th><td>（レビュー時に追記）</td></tr>"
        "<tr><th>実行環境</th><td>クロール: Chromium (Playwright) / 本文書は稼働システムから自動生成</td></tr>"
        "<tr><th>レビュー</th><td>レビュー者・承認日（第三者レビュー記入欄）</td></tr>"
        "<tr><th>制約</th><td>ログイン後ページは --auth 指定時のみ取得。JS動的生成リンクは取得漏れの可能性あり。"
        "テスト条件は制約からの機械導出候補であり、要件に基づく精査が必要。</td></tr>"
        "</tbody></table>"
    )
    return _section("メタ情報・トレーサビリティ", body)


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
