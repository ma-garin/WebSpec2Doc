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
_FORMULA_FALLBACK_MAX = 20 * 1024 * 1024  # 式の文字列で補うためにブックを再度開く上限


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


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _w_text(el) -> str:
    """w:p 直下の文字（テキストボックス内は除く。ボックスは別の断片として出す）。"""
    out = []
    for t in el.iter(f"{_W}t", f"{_W}tab", f"{_W}br"):
        a = t.getparent()
        while a is not None and a is not el and a.tag != f"{_W}txbxContent":
            a = a.getparent()
        if a is not None and a is not el:
            continue  # el の内側にあるテキストボックスの文字
        out.append(t.text or "" if t.tag == f"{_W}t" else ("\t" if t.tag == f"{_W}tab" else "\n"))
    return "".join(out).strip()


def _docx_table(tbl, name: str, counter: list) -> Iterator[Passage]:
    """表をセル単位で読む。結合セルは 1 回だけ出し（番地は結合の左上）、入れ子の表は「表N-M」として続けて読む。"""
    for r_no, tr in enumerate(tbl.iterchildren(f"{_W}tr"), start=1):
        col = 0
        for tc in tr.iterchildren(f"{_W}tc"):
            c_no = col
            span = tc.find(f"{_W}tcPr/{_W}gridSpan")
            col += int(span.get(f"{_W}val", "1")) if span is not None else 1
            vm = tc.find(f"{_W}tcPr/{_W}vMerge")
            if vm is not None and vm.get(f"{_W}val") != "restart":
                continue  # 縦結合の続き（上のセルで出した）
            text = "\n".join(t for t in (_w_text(p) for p in tc.iterchildren(f"{_W}p")) if t)
            if text:
                yield Passage(text, Locator("cell", r_no, name, f"{_col(c_no)}{r_no}"))
            for inner in tc.iterchildren(f"{_W}tbl"):
                counter[0] += 1
                yield from _docx_table(inner, f"{name}-{counter[0]}", counter)


def _docx_boxes(el, no: int) -> Iterator[Passage]:
    for k, box in enumerate(el.iter(f"{_W}txbxContent"), start=1):
        text = "\n".join(t for t in (_w_text(p) for p in box.iter(f"{_W}p")) if t)
        if text:
            yield Passage(text, Locator("cell", no, "図形", f"段落{no}-{k}"))


def _docx(path: Path) -> Iterator[Passage]:
    """本文を文書の順に読む（段落と表が混在しても順序を保つ）。テキストボックス・ヘッダー/フッターも読む。"""
    from docx import Document
    doc = Document(str(path))
    p_no = t_no = 0
    for el in doc.element.body.iterchildren():
        if el.tag == f"{_W}p":
            p_no += 1
            text = _w_text(el)
            if text:
                yield Passage(text, Locator("paragraph", p_no))
            yield from _docx_boxes(el, p_no)
        elif el.tag == f"{_W}tbl":
            t_no += 1
            yield from _docx_table(el, f"表{t_no}", [0])
    done: set = set()
    for s_no, sec in enumerate(doc.sections, start=1):
        for label, part in (("ヘッダー", sec.header), ("フッター", sec.footer)):
            if part.is_linked_to_previous and s_no > 1:
                continue
            key = str(part.part.partname)  # 節をまたいで同じヘッダーを共有することがある
            if key in done:
                continue
            done.add(key)
            for k, p in enumerate(part._element.iter(f"{_W}p"), start=1):
                text = _w_text(p)
                if text:
                    yield Passage(text, Locator("cell", k, label, f"節{s_no}-{k}"))


def _col(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _xlsx_shapes(path: Path) -> Iterator[Passage]:
    """図形・テキストボックス内の文字（xl/drawings/*.xml の a:t）。openpyxl は読まないため zip から直接読む。"""
    import zipfile
    from xml.etree import ElementTree as ET
    a_ns = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if re.fullmatch(r"xl/drawings/drawing\d+\.xml", n))
        for d_no, name in enumerate(names, start=1):
            raw = z.read(name)
            if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:  # 実体展開による膨張を拒否する
                raise _corrupt(path)
            root = ET.fromstring(raw)
            for k, para in enumerate(root.iter(f"{a_ns}p"), start=1):
                text = "".join(t.text or "" for t in para.iter(f"{a_ns}t")).strip()
                if text:
                    yield Passage(text, Locator("cell", k, "図形", f"図{d_no}-{k}"))


def _xlsx(path: Path) -> Iterator[Passage]:
    from openpyxl import load_workbook
    wb = load_workbook(str(path), read_only=True, data_only=True)
    formulas = None  # 計算結果が保存されていないセルだけ、式の文字列で補う
    try:
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    value = getattr(cell, "value", None)
                    coord = getattr(cell, "coordinate", None)
                    if coord is None:
                        continue
                    if value is None:
                        if path.stat().st_size > _FORMULA_FALLBACK_MAX:
                            continue  # 大きなブックは全展開しない（メモリ保護）。保存値の無い式は読まない
                        if formulas is None:
                            formulas = load_workbook(str(path), read_only=False, data_only=False)
                        raw = formulas[ws.title][coord].value
                        if not (isinstance(raw, str) and raw.startswith("=")):
                            continue
                        value = raw
                    if not str(value).strip():
                        continue
                    row_no = int(_CELL_ROW.search(coord).group(1))
                    yield Passage(str(value).strip(), Locator("cell", row_no, ws.title, coord))
    finally:
        wb.close()
        if formulas is not None:
            formulas.close()
    yield from _xlsx_shapes(path)


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
