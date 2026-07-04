"""フォーマット非依存の表構造化。

Excel・Word・Markdown など、どのフォーマット由来の表も ExtractedTable に
落とし、列名シノニムで DocumentedScreen / DocumentedField へ正規化する。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ingest.models import DocumentedField, DocumentedScreen, DocumentEvidence

# 列名シノニム（正規化後の完全一致を優先し、次に部分一致で判定する）
SCREEN_NAME_KEYS = ("画面名", "画面名称", "スクリーン名", "ページ名", "screen", "screenname")
SCREEN_ID_KEYS = ("画面id", "画面no", "画面番号", "id", "no")
URL_KEYS = ("url", "パス", "path")
FIELD_NAME_KEYS = ("項目名", "項目名称", "論理名", "ラベル", "フィールド名", "field", "label")
PHYSICAL_KEYS = ("物理名", "name", "name属性", "フィールドid", "項目id")
TYPE_KEYS = ("型", "データ型", "タイプ", "種別", "type")
REQUIRED_KEYS = ("必須", "必須区分", "必須有無", "required")
LENGTH_KEYS = ("桁", "桁数", "最大桁数", "文字数", "最大文字数", "最大長", "maxlength")
NOTE_KEYS = ("備考", "説明", "摘要", "note", "remarks")
FIELD_SCREEN_REF_KEYS = ("画面名", "画面", "画面id")

_TRUE_MARKS = frozenset({"○", "◯", "●", "✓", "レ", "必須", "yes", "y", "true", "1", "済"})
_FALSE_MARKS = frozenset({"×", "✕", "－", "-", "任意", "no", "n", "false", "0", ""})


@dataclass(frozen=True)
class ExtractedRow:
    """位置情報付きの表 1 行。"""

    location: str
    cells: tuple[str, ...]


@dataclass(frozen=True)
class ExtractedTable:
    """フォーマット非依存の表（ヘッダ＋行）。"""

    source_file: str
    headers: tuple[str, ...]
    rows: tuple[ExtractedRow, ...]


def normalize_header(value: str) -> str:
    """列名を比較用に正規化する（空白・記号除去、小文字化）。"""
    return re.sub(r"[\s＊*※:：()（）]", "", value).strip().lower()


def find_column(headers: tuple[str, ...], keys: tuple[str, ...]) -> int | None:
    """シノニムに一致する列番号を返す（完全一致優先、次に部分一致）。"""
    normalized = [normalize_header(h) for h in headers]
    for index, header in enumerate(normalized):
        if header in keys:
            return index
    for index, header in enumerate(normalized):
        if any(key in header for key in keys if len(key) >= 2):
            return index
    return None


def looks_like_header(cells: tuple[str, ...]) -> bool:
    """行がヘッダ行らしいか（既知シノニムに 2 列以上一致するか）を判定する。"""
    all_keys = (
        SCREEN_NAME_KEYS
        + SCREEN_ID_KEYS
        + URL_KEYS
        + FIELD_NAME_KEYS
        + PHYSICAL_KEYS
        + TYPE_KEYS
        + REQUIRED_KEYS
        + LENGTH_KEYS
    )
    hits = sum(1 for cell in cells if normalize_header(cell) in all_keys)
    return hits >= 2


def parse_required(value: str) -> bool | None:
    """必須欄の記載（○/×/必須/任意 等）を bool に解釈する。未記載・不明は None。"""
    mark = value.strip().lower()
    if mark in _TRUE_MARKS:
        return True
    if mark in _FALSE_MARKS:
        return None if mark == "" else False
    return None


def parse_max_length(value: str) -> int | None:
    """桁数欄の記載（"20"・"全角20"・"20桁" 等）から数値を抽出する。"""
    match = re.search(r"(\d+)", value)
    if not match:
        return None
    return int(match.group(1))


def structure_table(
    table: ExtractedTable,
) -> tuple[list[DocumentedScreen], list[DocumentedField]]:
    """1 つの表を画面一覧または項目定義として解釈する。

    項目名列があれば項目定義表、なければ画面名列があれば画面一覧として扱う。
    どちらにも該当しない表は無視する（無理に解釈しない）。
    """
    field_name_col = find_column(table.headers, FIELD_NAME_KEYS)
    if field_name_col is not None:
        return [], _structure_field_table(table, field_name_col)
    screen_name_col = find_column(table.headers, SCREEN_NAME_KEYS)
    if screen_name_col is not None:
        return _structure_screen_table(table, screen_name_col), []
    return [], []


def _cell(row: ExtractedRow, col: int | None) -> str:
    if col is None or col >= len(row.cells):
        return ""
    return row.cells[col].strip()


def _structure_screen_table(table: ExtractedTable, name_col: int) -> list[DocumentedScreen]:
    id_col = find_column(table.headers, SCREEN_ID_KEYS)
    url_col = find_column(table.headers, URL_KEYS)
    note_col = find_column(table.headers, NOTE_KEYS)
    screens: list[DocumentedScreen] = []
    for row in table.rows:
        name = _cell(row, name_col)
        if not name:
            continue
        screens.append(
            DocumentedScreen(
                screen_id=_cell(row, id_col),
                name=name,
                url_hint=_cell(row, url_col),
                note=_cell(row, note_col),
                evidence=DocumentEvidence(
                    file=table.source_file, location=row.location, quote=name
                ),
            )
        )
    return screens


def _structure_field_table(table: ExtractedTable, name_col: int) -> list[DocumentedField]:
    # 画面参照列は項目名列と別の列であること（「画面名」列が項目名を兼ねる誤検出を防ぐ）
    screen_col = find_column(table.headers, FIELD_SCREEN_REF_KEYS)
    if screen_col == name_col:
        screen_col = None
    physical_col = find_column(table.headers, PHYSICAL_KEYS)
    type_col = find_column(table.headers, TYPE_KEYS)
    required_col = find_column(table.headers, REQUIRED_KEYS)
    length_col = find_column(table.headers, LENGTH_KEYS)
    note_col = find_column(table.headers, NOTE_KEYS)
    fields: list[DocumentedField] = []
    for row in table.rows:
        name = _cell(row, name_col)
        if not name:
            continue
        required = parse_required(_cell(row, required_col)) if required_col is not None else None
        length = parse_max_length(_cell(row, length_col)) if length_col is not None else None
        fields.append(
            DocumentedField(
                name=name,
                physical_name=_cell(row, physical_col),
                screen_name=_cell(row, screen_col),
                field_type=_cell(row, type_col),
                required=required,
                max_length=length,
                note=_cell(row, note_col),
                evidence=DocumentEvidence(
                    file=table.source_file, location=row.location, quote=name
                ),
            )
        )
    return fields


_SCREEN_LINE_RE = re.compile(r"([^\s。、:：/｜|]{1,30}?(?:画面|ページ|スクリーン))")
_MAX_SCREEN_LINE_LENGTH = 40


def screens_from_lines(
    lines: list[tuple[str, str]],
    source_file: str,
    headings_only: bool = False,
) -> list[DocumentedScreen]:
    """テキスト行から画面名の候補を抽出する（見出し・短い行のみ対象）。

    lines は (location, text) のリスト。headings_only=True の場合は
    呼び出し側で見出しに絞ってあることを前提にそのまま評価する。
    自由文からの深い意味抽出は行わない（Phase 2 の LLM 抽出で扱う）。
    """
    seen: set[str] = set()
    screens: list[DocumentedScreen] = []
    for location, text in lines:
        line = text.strip()
        if not line:
            continue
        if not headings_only and len(line) > _MAX_SCREEN_LINE_LENGTH:
            continue
        match = _SCREEN_LINE_RE.search(line)
        if not match:
            continue
        name = match.group(1)
        # 「一覧画面」のような一般語だけの候補や重複は除外する
        if len(name) <= 2 or name in seen:
            continue
        seen.add(name)
        screens.append(
            DocumentedScreen(
                screen_id="",
                name=name,
                note="テキスト見出しから抽出",
                evidence=DocumentEvidence(file=source_file, location=location, quote=line[:80]),
            )
        )
    return screens
