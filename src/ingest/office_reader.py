"""Office 文書（.docx/.pptx）からの表・見出し抽出。

外部依存を増やさないため、OOXML（zip + XML）を標準ライブラリで直接読む。
.doc / .ppt（旧バイナリ形式）は対象外（docx/pptx への変換を案内する）。
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree

from ingest.tables import ExtractedRow, ExtractedTable, looks_like_header

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def read_docx(path: Path) -> tuple[list[ExtractedTable], list[tuple[str, str]]]:
    """Word 文書から表と見出し行を抽出する。

    戻り値は (表のリスト, 見出し行 [(location, text)]) 。
    """
    with zipfile.ZipFile(path) as archive:
        xml_bytes = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml_bytes)  # noqa: S314  # ローカル文書の解析
    tables: list[ExtractedTable] = []
    headings: list[tuple[str, str]] = []
    body = root.find(f"{_W_NS}body")
    if body is None:
        return tables, headings
    paragraph_number = 0
    for element in body:
        if element.tag == f"{_W_NS}tbl":
            table = _docx_table(path.name, element, len(tables) + 1)
            if table is not None:
                tables.append(table)
        elif element.tag == f"{_W_NS}p":
            paragraph_number += 1
            text = _docx_paragraph_text(element)
            if text and _is_docx_heading(element):
                headings.append((f"paragraph {paragraph_number}", text))
    return tables, headings


def _docx_paragraph_text(paragraph: ElementTree.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(f"{_W_NS}t")).strip()


def _is_docx_heading(paragraph: ElementTree.Element) -> bool:
    style = paragraph.find(f"{_W_NS}pPr/{_W_NS}pStyle")
    if style is None:
        return False
    value = style.get(f"{_W_NS}val", "")
    return value.lower().startswith("heading") or value.startswith("見出し")


def _docx_table(
    file_name: str, table_element: ElementTree.Element, table_number: int
) -> ExtractedTable | None:
    rows: list[tuple[str, ...]] = []
    for row_element in table_element.findall(f"{_W_NS}tr"):
        cells = tuple(
            "".join(node.text or "" for node in cell.iter(f"{_W_NS}t")).strip()
            for cell in row_element.findall(f"{_W_NS}tc")
        )
        rows.append(cells)
    if not rows:
        return None
    # ヘッダ行を先頭数行から検出する（表タイトル行が先頭にある場合に対応）
    header_index = next(
        (index for index, cells in enumerate(rows[:3]) if looks_like_header(cells)), None
    )
    if header_index is None:
        return None
    data_rows = [
        ExtractedRow(location=f"table {table_number}, row {row_index + 1}", cells=cells)
        for row_index, cells in enumerate(rows)
        if row_index > header_index and any(cells)
    ]
    if not data_rows:
        return None
    return ExtractedTable(source_file=file_name, headers=rows[header_index], rows=tuple(data_rows))


def read_pptx_lines(path: Path) -> list[tuple[str, str]]:
    """PowerPoint からテキスト行を抽出する（スライド番号を位置情報とする）。"""
    lines: list[tuple[str, str]] = []
    with zipfile.ZipFile(path) as archive:
        slide_names = sorted(
            name
            for name in archive.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        for slide_name in slide_names:
            slide_number = slide_name.removeprefix("ppt/slides/slide").removesuffix(".xml")
            root = ElementTree.fromstring(archive.read(slide_name))  # noqa: S314
            for node in root.iter(f"{_A_NS}t"):
                text = (node.text or "").strip()
                if text:
                    lines.append((f"slide {slide_number}", text))
    return lines
