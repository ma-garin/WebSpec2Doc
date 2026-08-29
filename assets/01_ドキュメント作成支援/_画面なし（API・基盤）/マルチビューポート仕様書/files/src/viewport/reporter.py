"""ビューポート間差分の文書化（Markdown / 自己完結HTML）。"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from viewport.profiles import PROFILES

REPORT_TITLE = "マルチビューポート仕様書"

SECTION_LABELS = {
    "hidden_pages": "この画面幅では到達しなかった画面",
    "viewport_only_pages": "この画面幅だけで到達した画面",
    "hidden_fields": "この画面幅では出なかった入力項目",
    "viewport_only_fields": "この画面幅だけに出た入力項目",
    "hidden_links": "この画面幅では出なかった遷移",
    "viewport_only_links": "この画面幅だけに出た遷移",
}


def save_viewport_report(report: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    """viewport_report.{md,html,json} を書き出す。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "viewport_report_md": out_dir / "viewport_report.md",
        "viewport_report_html": out_dir / "viewport_report.html",
        "viewport_report_json": out_dir / "viewport_report.json",
    }
    paths["viewport_report_md"].write_text(render_markdown(report), encoding="utf-8")
    paths["viewport_report_html"].write_text(render_html(report), encoding="utf-8")
    paths["viewport_report_json"].write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return paths


def _label(name: str) -> str:
    profile = PROFILES.get(name)
    return profile.label if profile else name


def render_markdown(report: dict[str, Any]) -> str:
    meta = report.get("meta", {})
    summary = report.get("summary", {})
    lines = [
        f"# {REPORT_TITLE}",
        "",
        f"> {meta.get('claim_notice', '')}",
        "",
        f"- 基準: {_label(str(meta.get('baseline', '')))}",
        f"- 観測したビューポート: {', '.join(_label(v) for v in meta.get('viewports', []))}",
        f"- 主張範囲: `{meta.get('claim_scope', '')}`",
        "",
        "## 差分の総数",
        "",
        "| 種別 | 件数 |",
        "|---|---:|",
    ]
    for key, label in SECTION_LABELS.items():
        lines.append(f"| {label} | {summary.get(key, 0)} |")

    for comparison in report.get("comparisons", []):
        lines += ["", f"## {_label(str(comparison.get('viewport', '')))}", ""]
        for key, label in SECTION_LABELS.items():
            entries = comparison.get(key, [])
            lines.append(f"### {label}（{len(entries)}件）")
            lines.append("")
            if not entries:
                lines += ["なし", ""]
                continue
            for entry in entries:
                lines.append(f"- {_entry_text(entry)}")
            lines.append("")
    return "\n".join(lines) + "\n"


def _entry_text(entry: dict[str, Any]) -> str:
    if "field_name" in entry:
        return f"`{entry.get('field_name', '')}` — {entry.get('page_url', '')}"
    if "link" in entry:
        return f"{entry.get('page_url', '')} → {entry.get('link', '')}"
    title = str(entry.get("title", "")).strip()
    url = str(entry.get("url", ""))
    return f"{title}（{url}）" if title else url


def render_html(report: dict[str, Any]) -> str:
    meta = report.get("meta", {})
    summary = report.get("summary", {})
    summary_rows = "".join(
        f"<tr><td>{html.escape(label)}</td>" f'<td class="num">{int(summary.get(key, 0))}</td></tr>'
        for key, label in SECTION_LABELS.items()
    )
    sections = "".join(_html_section(c) for c in report.get("comparisons", []))
    sections += _layout_failures_html(report.get("layout_failures"))
    viewports = ", ".join(_label(v) for v in meta.get("viewports", []))
    return f"""<!doctype html><html lang="ja"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(REPORT_TITLE)}</title>
<style>{_css()}</style>
</head><body>
<header><h1>{html.escape(REPORT_TITLE)}</h1>
<p class="notice">{html.escape(str(meta.get('claim_notice', '')))}</p></header>
<main>
<section><h2>概要</h2><ul>
<li>基準: {html.escape(_label(str(meta.get('baseline', ''))))}</li>
<li>観測したビューポート: {html.escape(viewports)}</li>
<li>主張範囲: <code>{html.escape(str(meta.get('claim_scope', '')))}</code></li>
</ul>
<div class="scroll"><table><thead><tr><th>種別</th><th>件数</th></tr></thead>
<tbody>{summary_rows}</tbody></table></div></section>
{sections}
</main></body></html>"""


def _layout_failures_html(layout: dict[str, Any] | None) -> str:
    """レイアウト観測（はみ出し・重なり）。観測に留めバグ断定はしない。"""
    if not layout:
        return ""
    summary = layout.get("summary", {})
    if not summary.get("protrusions") and not summary.get("collisions"):
        return ""
    rows = []
    for vp in layout.get("viewports", []):
        for p in vp.get("protrusions", []):
            rows.append(
                f"<li>{html.escape(_label(str(vp.get('viewport', ''))))}: "
                f"<code>{html.escape(str(p.get('selector', '')))}</code> が "
                f"{p.get('overflow_px', 0):.0f}px はみ出して観測された</li>"
            )
        for c in vp.get("collisions", []):
            rows.append(
                f"<li>{html.escape(_label(str(vp.get('viewport', ''))))}: "
                f"<code>{html.escape(str(c.get('selector_a', '')))}</code> と "
                f"<code>{html.escape(str(c.get('selector_b', '')))}</code> が"
                "重なって観測された</li>"
            )
    note = html.escape(str(layout.get("meta", {}).get("claim_notice", "")))
    return (
        "<section><h2>レイアウト観測</h2>"
        f'<div class="body"><p class="muted">{note}</p><ul>{"".join(rows)}</ul></div></section>'
    )


def _html_section(comparison: dict[str, Any]) -> str:
    blocks = []
    for key, label in SECTION_LABELS.items():
        entries = comparison.get(key, [])
        if entries:
            items = "".join(f"<li>{html.escape(_entry_text(e))}</li>" for e in entries)
            body = f"<ul>{items}</ul>"
        else:
            body = '<p class="muted">なし</p>'
        blocks.append(f"<h3>{html.escape(label)}（{len(entries)}件）</h3>{body}")
    name = _label(str(comparison.get("viewport", "")))
    return (
        f"<section><h2>{html.escape(name)}</h2><div class='body'>{''.join(blocks)}</div></section>"
    )


def _css() -> str:
    return """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif;color:#16202B;background:#f5f7f9;line-height:1.7}
header{background:#00285E;color:#fff;padding:1.4rem 2rem}
header h1{font-size:1.35rem}
.notice{margin-top:.4rem;font-size:.85rem;opacity:.92}
main{max-width:1000px;margin:2rem auto;padding:0 1.5rem;display:flex;flex-direction:column;gap:1.5rem}
section{background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,.08);overflow:hidden}
section h2{background:#eef2f5;padding:.7rem 1.2rem;font-size:1rem}
section>ul,.body,.scroll{padding:1.2rem}
section>ul{list-style:none;display:flex;flex-direction:column;gap:.3rem;font-size:.9rem}
h3{font-size:.9rem;margin-top:1rem}
h3:first-child{margin-top:0}
.body ul{margin:.4rem 0 0 1.2rem;font-size:.88rem}
.muted{color:#888;font-size:.88rem;margin-top:.3rem}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th{background:#00285E;color:#fff;padding:.55rem .8rem;text-align:left}
td{padding:.5rem .8rem;border-bottom:1px solid #eee}
td.num{font-variant-numeric:tabular-nums;text-align:right}
code{font-family:ui-monospace,Menlo,monospace}
"""
