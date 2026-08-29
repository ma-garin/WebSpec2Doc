"""テキスト系文書（.md/.txt）と PDF からの抽出。

Markdown はテーブル（GFM 形式）と見出しを構造として扱う。
プレーンテキストと PDF は行の集まりとして扱い、画面名候補の抽出のみ行う
（自由文からの深い意味抽出は Phase 2 の LLM 抽出で扱う）。
"""

from __future__ import annotations

import re
from pathlib import Path

from ingest.tables import ExtractedRow, ExtractedTable, looks_like_header

_MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$")
_MD_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_MD_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?[\s:|-]+\|?\s*$")


def read_markdown(path: Path) -> tuple[list[ExtractedTable], list[tuple[str, str]]]:
    """Markdown からテーブルと見出しを抽出する。

    戻り値は (表のリスト, 見出し行 [(location, text)])。
    """
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    tables: list[ExtractedTable] = []
    headings: list[tuple[str, str]] = []
    row_buffer: list[tuple[int, tuple[str, ...]]] = []

    def _flush_table() -> None:
        if len(row_buffer) < 2:
            row_buffer.clear()
            return
        header_index = next(
            (i for i, (_, cells) in enumerate(row_buffer[:3]) if looks_like_header(cells)),
            None,
        )
        if header_index is not None:
            data_rows = tuple(
                ExtractedRow(location=f"line {line_number}", cells=cells)
                for line_number, cells in row_buffer[header_index + 1 :]
                if any(cells)
            )
            if data_rows:
                tables.append(
                    ExtractedTable(
                        source_file=path.name,
                        headers=row_buffer[header_index][1],
                        rows=data_rows,
                    )
                )
        row_buffer.clear()

    for line_number, line in enumerate(lines, start=1):
        heading_match = _MD_HEADING_RE.match(line)
        if heading_match:
            _flush_table()
            headings.append((f"line {line_number}", heading_match.group(1).strip()))
            continue
        table_match = _MD_TABLE_ROW_RE.match(line)
        if table_match:
            if _MD_TABLE_SEPARATOR_RE.match(line):
                continue
            cells = tuple(cell.strip() for cell in table_match.group(1).split("|"))
            row_buffer.append((line_number, cells))
            continue
        _flush_table()
    _flush_table()
    return tables, headings


def read_plain_text_lines(path: Path) -> list[tuple[str, str]]:
    """プレーンテキストを (location, text) の行リストとして読む。"""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [(f"line {number}", line) for number, line in enumerate(lines, start=1) if line.strip()]


def read_pdf_lines(path: Path) -> list[tuple[str, str]]:
    """PDF からテキスト行を抽出する（ページ番号を位置情報とする）。

    PDF の表はレイアウト依存で信頼できる構造抽出ができないため、
    Phase 1 では行テキストとしてのみ取り込む。
    """
    from pypdf import PdfReader

    reader = PdfReader(path)
    lines: list[tuple[str, str]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line.strip():
                lines.append((f"page {page_number}, line {line_number}", line))
    return lines
