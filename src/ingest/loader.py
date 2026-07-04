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
from ingest.llm_extractor import extract_semantics
from ingest.models import DocumentBundle, DocumentedField, DocumentedRule, DocumentedScreen
from ingest.office_reader import read_docx, read_docx_body_lines, read_pptx_lines
from ingest.tables import screens_from_lines, structure_table
from ingest.text_reader import read_markdown, read_pdf_lines, read_plain_text_lines

if TYPE_CHECKING:
    from ingest.tables import ExtractedTable
    from llm.provider import LLMProvider

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


def load_reference_documents(
    paths: list[Path], use_llm: bool = False, api_key: str = ""
) -> DocumentBundle:
    """参考文書一式を読み込み、正規化された DocumentBundle を返す。

    use_llm=True の場合、自由文形式（pdf/pptx/txt/docx 本文）から
    LLM で画面・項目・業務ルールを追加抽出する（表由来の抽出は不変）。
    api_key が空、または LLM 呼び出しが失敗した場合は Phase 1 抽出のみで
    完走する（AC-4/AC-5）。
    """
    screens: list[DocumentedScreen] = []
    fields: list[DocumentedField] = []
    rules: list[DocumentedRule] = []
    source_files: list[str] = []
    provider = _build_provider(use_llm, api_key) if use_llm else None
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"参考文書が見つかりません: {path}")
        doc_screens, doc_fields = _load_one(path)
        screens.extend(doc_screens)
        fields.extend(doc_fields)
        if provider is not None:
            llm_screens, llm_fields, llm_rules = _load_llm_semantics(path, doc_screens, provider)
            screens.extend(llm_screens)
            fields.extend(llm_fields)
            rules.extend(llm_rules)
        source_files.append(path.name)
        logger.info(
            "参考文書を取り込みました: %s（画面 %d 件・項目 %d 件）",
            path.name,
            len(doc_screens),
            len(doc_fields),
        )
    return DocumentBundle(
        screens=tuple(screens),
        fields=tuple(fields),
        source_files=tuple(source_files),
        rules=tuple(rules),
    )


def _build_provider(use_llm: bool, api_key: str) -> LLMProvider:
    from llm.provider import OpenAIProvider, RulesProvider

    if not use_llm or not api_key:
        return RulesProvider()
    return OpenAIProvider(api_key)


def _free_text_lines(path: Path) -> list[tuple[str, str]] | None:
    """LLM 抽出向けの自由文行を返す（表構造中心の形式は None）。"""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return read_pdf_lines(path)
    if suffix == ".pptx":
        return read_pptx_lines(path)
    if suffix == ".txt":
        return read_plain_text_lines(path)
    if suffix == ".docx":
        return read_docx_body_lines(path)
    return None


def _load_llm_semantics(
    path: Path, table_screens: list[DocumentedScreen], provider: LLMProvider
) -> tuple[list[DocumentedScreen], list[DocumentedField], list[DocumentedRule]]:
    lines = _free_text_lines(path)
    if lines is None:
        return [], [], []
    llm_screens, llm_fields, llm_rules = extract_semantics(lines, path.name, provider)
    llm_screens = _dedup_screens(llm_screens, table_screens)
    return llm_screens, llm_fields, llm_rules


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
