"""軽量 Markdown → HTML 変換（依存なし・XSS安全）。

static/js/markdown-lite.js のサーバーサイド版。対応構文は同一に揃える:
見出し(#〜######) / 太字・斜体 / インラインコード / コードブロック(```)
/ テーブル(|a|b|) / 箇条書き(-,*,数字.) / リンク([text](https://...)) / 段落。

安全設計: まず全文を HTML エスケープしてから、エスケープ済みテキストに対して
自前で挿入するタグだけを正規表現で足していく（＝生成されるタグは全てこの
関数が書いたものだけであり、入力由来のタグは決して出現しない）。
"""

from __future__ import annotations

import html
import re

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"\*([^*]+)\*")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_ITEM = re.compile(r"^\s*[-*]\s+(.*)$")
_OL_ITEM = re.compile(r"^\s*\d+\.\s+(.*)$")
_TABLE_ROW = re.compile(r"^\|(.+)\|\s*$")
_TABLE_DIVIDER = re.compile(r"^\|[\s:|-]+\|\s*$")
_CODE_FENCE = re.compile(r"^```")


def _inline(escaped: str) -> str:
    text = _INLINE_CODE.sub(r"<code>\1</code>", escaped)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    text = _LINK.sub(r'<a href="\2" target="_blank" rel="noopener noreferrer">\1</a>', text)
    return text


def render_markdown_lite(source: str) -> str:
    """自前生成Markdown（見出し/箇条書き/テーブル/段落）をHTMLへ変換する。"""
    lines = html.escape(source or "").split("\n")
    out: list[str] = []
    para: list[str] = []
    list_kind: str | None = None
    table_header: list[str] | None = None
    table_rows: list[list[str]] = []

    def flush_para() -> None:
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para.clear()

    def flush_list() -> None:
        nonlocal list_kind
        if list_kind:
            out.append(f"</{list_kind}>")
            list_kind = None

    def flush_table() -> None:
        nonlocal table_header, table_rows
        if table_header is not None:
            thead = (
                "<thead><tr>"
                + "".join(f"<th>{_inline(cell.strip())}</th>" for cell in table_header)
                + "</tr></thead>"
            )
            tbody = (
                "<tbody>"
                + "".join(
                    "<tr>" + "".join(f"<td>{_inline(cell.strip())}</td>" for cell in row) + "</tr>"
                    for row in table_rows
                )
                + "</tbody>"
            )
            out.append(f'<table class="md-table">{thead}{tbody}</table>')
            table_header = None
            table_rows = []

    i = 0
    while i < len(lines):
        line = lines[i]

        if _CODE_FENCE.match(line.strip()):
            flush_para()
            flush_list()
            flush_table()
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not _CODE_FENCE.match(lines[i].strip()):
                code_lines.append(lines[i])
                i += 1
            out.append('<pre class="md-code"><code>' + "\n".join(code_lines) + "</code></pre>")
            i += 1
            continue

        table_match = _TABLE_ROW.match(line)
        next_is_divider = (
            bool(table_match) and i + 1 < len(lines) and bool(_TABLE_DIVIDER.match(lines[i + 1]))
        )
        if table_header is None and table_match and next_is_divider:
            flush_para()
            flush_list()
            table_header = table_match.group(1).split("|")
            i += 2
            continue
        if table_header is not None and table_match:
            table_rows.append(table_match.group(1).split("|"))
            i += 1
            continue
        if table_header is not None:
            flush_table()

        heading = _HEADING.match(line)
        if heading:
            flush_para()
            flush_list()
            level = len(heading.group(1))
            out.append(f'<h{level} class="md-h{level}">{_inline(heading.group(2))}</h{level}>')
            i += 1
            continue

        ul_item = _UL_ITEM.match(line)
        ol_item = _OL_ITEM.match(line)
        if ul_item or ol_item:
            flush_para()
            kind = "ul" if ul_item else "ol"
            if list_kind != kind:
                flush_list()
                out.append(f"<{kind}>")
                list_kind = kind
            content = (ul_item or ol_item).group(1)  # type: ignore[union-attr]
            out.append(f"<li>{_inline(content)}</li>")
            i += 1
            continue
        flush_list()

        if not line.strip():
            flush_para()
            i += 1
            continue

        para.append(line.strip())
        i += 1

    flush_para()
    flush_list()
    flush_table()
    return "\n".join(out)
