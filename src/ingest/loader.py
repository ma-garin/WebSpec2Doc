"""参考文書の取り込みエントリポイント。

拡張子でリーダーを振り分け、全文書を単一の DocumentBundle に統合する。
対応形式: .xlsx/.xlsm（Excel）、.docx/.pptx（Office）、.pdf、.md、.txt、
.yaml/.yml/.json。旧バイナリ形式（.doc/.xls/.ppt）は変換を案内する。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from ingest.data_reader import read_structured_data
from ingest.excel_reader import read_excel_tables
from ingest.models import DocumentBundle, DocumentedField, DocumentedScreen
from ingest.office_reader import read_docx, read_pptx_lines
from ingest.tables import screens_from_lines, structure_table
from ingest.text_reader import read_markdown, read_pdf_lines, read_plain_text_lines

if TYPE_CHECKING:
    from ingest.tables import ExtractedTable

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = (
    ".xlsx",
    ".xlsm",
    ".docx",
    ".pptx",
    ".pdf",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".json",
)
_LEGACY_SUFFIXES = (".xls", ".doc", ".ppt")


def load_reference_documents(paths: list[Path]) -> DocumentBundle:
    """参考文書一式を読み込み、正規化された DocumentBundle を返す。"""
    screens: list[DocumentedScreen] = []
    fields: list[DocumentedField] = []
    source_files: list[str] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"参考文書が見つかりません: {path}")
        doc_screens, doc_fields = _load_one(path)
        screens.extend(doc_screens)
        fields.extend(doc_fields)
        source_files.append(path.name)
        logger.info(
            "参考文書を取り込みました: %s（画面 %d 件・項目 %d 件）",
            path.name,
            len(doc_screens),
            len(doc_fields),
        )
    return DocumentBundle(
        screens=tuple(screens), fields=tuple(fields), source_files=tuple(source_files)
    )


def _load_one(path: Path) -> tuple[list[DocumentedScreen], list[DocumentedField]]:
    suffix = path.suffix.lower()
    if suffix in _LEGACY_SUFFIXES:
        raise ValueError(
            f"旧バイナリ形式（{suffix}）は未対応です。"
            f" {suffix}x 形式に変換してから指定してください: {path.name}"
        )
    if suffix in (".xlsx", ".xlsm"):
        return _from_tables(read_excel_tables(path))
    if suffix == ".docx":
        tables, headings = read_docx(path)
        screens, fields = _from_tables(tables)
        screens.extend(
            _dedup_screens(screens_from_lines(headings, path.name, headings_only=True), screens)
        )
        return screens, fields
    if suffix == ".pptx":
        return screens_from_lines(read_pptx_lines(path), path.name), []
    if suffix == ".pdf":
        return screens_from_lines(read_pdf_lines(path), path.name), []
    if suffix == ".md":
        tables, headings = read_markdown(path)
        screens, fields = _from_tables(tables)
        screens.extend(
            _dedup_screens(screens_from_lines(headings, path.name, headings_only=True), screens)
        )
        return screens, fields
    if suffix == ".txt":
        return screens_from_lines(read_plain_text_lines(path), path.name), []
    if suffix in (".yaml", ".yml", ".json"):
        doc_screens, doc_fields = read_structured_data(path)
        return list(doc_screens), list(doc_fields)
    raise ValueError(
        f"未対応の文書形式です: {path.name}（対応形式: {', '.join(SUPPORTED_SUFFIXES)}）"
    )


def _from_tables(
    tables: list[ExtractedTable],
) -> tuple[list[DocumentedScreen], list[DocumentedField]]:
    screens: list[DocumentedScreen] = []
    fields: list[DocumentedField] = []
    for table in tables:
        table_screens, table_fields = structure_table(table)
        screens.extend(table_screens)
        fields.extend(table_fields)
    return screens, fields


def _dedup_screens(
    candidates: list[DocumentedScreen], existing: list[DocumentedScreen]
) -> list[DocumentedScreen]:
    """表から取れた画面と重複する見出し由来の候補を除外する。"""
    known_names = {screen.name for screen in existing}
    return [screen for screen in candidates if screen.name not in known_names]
