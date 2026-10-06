"""5 形式（txt・md・docx・xlsx・pdf）の読み取り。文書は読み取り専用で開く（REQ-F-008-01）。"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator, Literal

from web.vendor.reverse_doc.models import Evidence

MAX_BYTES = 200 * 1024 * 1024
SUPPORTED_SUFFIXES: tuple[str, ...] = (".txt", ".md", ".docx", ".xlsx", ".pdf")
LocatorKind = Literal["page", "line", "paragraph", "cell"]
_CELL_ROW = re.compile(r"(\d+)$")
_TEXT_ENCODINGS = ("utf-8-sig", "cp932")


class DocumentError(ValueError):
    """文書を取り込めない。メッセージは利用者向け（次の行動を 1 行添える）。"""


class UnsupportedFormatError(DocumentError):
    pass


class CorruptDocumentError(DocumentError):
    pass


class DocumentTooLargeError(DocumentError):
    pass


@dataclass(frozen=True)
class Locator:
    """文書内の位置。頁（pdf）・行（txt/md）・段落（docx）・シート名とセル（xlsx、docx の表）。"""
    kind: LocatorKind
    number: int                  # 頁番号・行番号・段落番号・セルの行番号（1 始まり）
    sheet: str = ""              # cell のときのシート名（docx の表は「表N」）
    cell: str = ""               # cell のときのセル番地（例 B2）

    def label(self) -> str:
        if self.kind == "page":
            return f"{self.number}頁"
        if self.kind == "line":
            return f"{self.number}行"
        if self.kind == "paragraph":
            return f"段落{self.number}"
        return f"{self.sheet}!{self.cell}"


@dataclass(frozen=True)
class Passage:
    text: str
    locator: Locator


@dataclass(frozen=True)
class DocumentIR:
    name: str                    # ファイル名（文書名）
    sha256: str                  # 読む前のファイルのハッシュ
    passages: tuple[Passage, ...]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_unchanged(path: Path, sha256: str) -> bool:
    """取り込み前に控えたハッシュと今のファイルが一致するか。消えていれば False。"""
    try:
        return file_sha256(Path(path)) == sha256
    except OSError:
        return False


def to_evidence(doc_name: str, passage: Passage) -> Evidence:
    """根拠（REQ-F-005-02）。文書名と位置だけを持ち、本文は写さない（REQ-F-005-03）。"""
    loc = passage.locator
    return Evidence(file=f"{doc_name}#{loc.label()}", line_start=loc.number, line_end=loc.number, snippet="")


def _corrupt(path: Path) -> CorruptDocumentError:
    return CorruptDocumentError(f"「{path.name}」を読めませんでした。ファイルが壊れていないか確認し、別のコピーを登録してください。")


def _lines(path: Path) -> Iterator[Passage]:
    raw = path.read_bytes()
    for enc in _TEXT_ENCODINGS:
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise CorruptDocumentError(f"「{path.name}」の文字コードを判別できません。UTF-8 で保存し直して登録してください。")
    for no, line in enumerate(text.splitlines(), start=1):
        if line.strip():
            yield Passage(line.strip(), Locator("line", no))


def _docx(path: Path) -> Iterator[Passage]:
    from docx import Document
    doc = Document(str(path))
    for no, para in enumerate(doc.paragraphs, start=1):
        if para.text.strip():
            yield Passage(para.text.strip(), Locator("paragraph", no))
    for t_no, table in enumerate(doc.tables, start=1):
        for r_no, row in enumerate(table.rows, start=1):
            for c_no, cell in enumerate(row.cells):
                if cell.text.strip():
                    yield Passage(cell.text.strip(), Locator("cell", r_no, f"表{t_no}", f"{_col(c_no)}{r_no}"))


def _col(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _xlsx(path: Path) -> Iterator[Passage]:
    from openpyxl import load_workbook
    wb = load_workbook(str(path), read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    value = getattr(cell, "value", None)
                    coord = getattr(cell, "coordinate", None)
                    if value is None or coord is None or not str(value).strip():
                        continue
                    row_no = int(_CELL_ROW.search(coord).group(1))
                    yield Passage(str(value).strip(), Locator("cell", row_no, ws.title, coord))
    finally:
        wb.close()


def _pdf(path: Path) -> Iterator[Passage]:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise CorruptDocumentError(f"「{path.name}」はパスワードで保護されています。保護を外したコピーを登録してください。")
    for no, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            yield Passage(text, Locator("page", no))


_READERS: dict[str, Callable[[Path], Iterator[Passage]]] = {
    ".txt": _lines, ".md": _lines, ".docx": _docx, ".xlsx": _xlsx, ".pdf": _pdf}


def _check(path: Path) -> None:
    if not path.is_file():
        raise DocumentError(f"「{path.name}」が見つかりません。パスを確認して登録し直してください。")
    if path.suffix.lower() not in _READERS:
        raise UnsupportedFormatError(
            f"「{path.name}」は取り込めない形式です。{' / '.join(SUPPORTED_SUFFIXES)} のいずれかで登録してください。")
    if path.stat().st_size > MAX_BYTES:
        raise DocumentTooLargeError(f"「{path.name}」は 200 MB を超えています。分割するか必要な部分だけにして登録してください。")


def read_document(path: Path) -> DocumentIR:
    """文書を読み、位置付きの断片にする。対応外・壊れた・大きすぎる文書は DocumentError。"""
    path = Path(path)
    _check(path)
    sha = file_sha256(path)
    try:
        passages = tuple(_READERS[path.suffix.lower()](path))
    except DocumentError:
        raise
    except Exception as exc:
        raise _corrupt(path) from exc
    return DocumentIR(name=path.name, sha256=sha, passages=passages)
