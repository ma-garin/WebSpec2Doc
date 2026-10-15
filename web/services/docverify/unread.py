"""読めなかった要素（画像・コメント・非表示・図形）を数える。中身は読まない（FR-06-015）。"""
from __future__ import annotations

import io
import logging
import re
import zipfile
from pathlib import Path
from xml.etree.ElementTree import iterparse

log = logging.getLogger(__name__)

KEYS: tuple[str, ...] = ("images", "comments", "hidden_sheets", "hidden_cols", "shapes")

_UNSAFE = (b"<!DOCTYPE", b"<!ENTITY")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\(")
_DOCX_PARTS = re.compile(r"^word/(document|header\d*|footer\d*)\.xml$")


class _Unsafe(Exception):
    """DOCTYPE / ENTITY を含む XML。"""


def _empty(scanned: bool) -> dict:
    return {**{k: 0 for k in KEYS}, "scanned": scanned}


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attr(el, name: str) -> str | None:
    for key, value in el.attrib.items():
        if _local(key) == name:
            return value
    return None


def _safe_xml(raw: bytes):
    """DOCTYPE / ENTITY があれば _Unsafe。無ければ要素の終了イベントを順に返す。"""
    if any(mark in raw for mark in _UNSAFE):
        raise _Unsafe("DOCTYPE/ENTITY in XML")
    for _event, el in iterparse(io.BytesIO(raw), events=("end",)):
        yield el


def _has_text(el, name: str) -> bool:
    return any(_local(c.tag) == name and (c.text or "").strip() for c in el.iter())


def _is_true(value: str | None) -> bool:
    return (value or "").lower() in ("1", "true")


def _xlsx_drawing(raw: bytes) -> tuple[int, int]:
    images = shapes = 0
    for el in _safe_xml(raw):
        tag = _local(el.tag)
        if tag == "pic":
            images += 1
        elif tag == "graphicFrame":
            shapes += 1
        elif tag == "sp" and not _has_text(el, "t"):
            shapes += 1
    return images, shapes


def _xlsx_hidden_cols(raw: bytes) -> int:
    count = 0
    for el in _safe_xml(raw):
        tag = _local(el.tag)
        if tag == "col" and _is_true(el.get("hidden")):
            count += int(el.get("max", "0")) - int(el.get("min", "0")) + 1
        elif tag == "row" and _is_true(el.get("hidden")):
            count += 1
        if tag in ("row", "col"):
            el.clear()
    return count


def _xlsx_comments(zf: zipfile.ZipFile, names: list[str]) -> int:
    legacy = [n for n in names if re.match(r"^xl/comments.*\.xml$", n)]
    count = sum(1 for n in legacy for el in _safe_xml(zf.read(n)) if _local(el.tag) == "comment")
    if count:
        return count
    threaded = [n for n in names if re.match(r"^xl/threadedComments/[^/]+\.xml$", n)]
    return sum(
        1 for n in threaded for el in _safe_xml(zf.read(n))
        if _local(el.tag) == "threadedComment" and el.get("parentId") is None
    )


def _xlsx(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        images = shapes = 0
        for n in names:
            if re.match(r"^xl/drawings/drawing[^/]*\.xml$", n):
                i, s = _xlsx_drawing(zf.read(n))
                images, shapes = images + i, shapes + s
        hidden_sheets = 0
        if "xl/workbook.xml" in names:
            hidden_sheets = sum(
                1 for el in _safe_xml(zf.read("xl/workbook.xml"))
                if _local(el.tag) == "sheet" and el.get("state") in ("hidden", "veryHidden")
            )
        hidden_cols = sum(
            _xlsx_hidden_cols(zf.read(n)) for n in names
            if re.match(r"^xl/worksheets/sheet[^/]*\.xml$", n)
        )
        comments = _xlsx_comments(zf, names)
    return {"images": images, "comments": comments, "hidden_sheets": hidden_sheets,
            "hidden_cols": hidden_cols, "shapes": shapes, "scanned": True}


def _docx_part(raw: bytes) -> tuple[int, int]:
    images = shapes = 0
    for el in _safe_xml(raw):
        tag = _local(el.tag)
        if tag == "pic" and el.tag.startswith("{http://schemas.openxmlformats.org/drawingml/2006/picture}"):
            images += 1
        elif tag == "graphicData":
            uri = (el.get("uri") or "").lower()
            if "chart" in uri or "diagram" in uri:
                shapes += 1
        elif tag == "wsp" and not _has_text(el, "t"):
            shapes += 1
    return images, shapes


def _docx(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        images = shapes = 0
        for n in names:
            if _DOCX_PARTS.match(n):
                i, s = _docx_part(zf.read(n))
                images, shapes = images + i, shapes + s
        comments = 0
        if "word/comments.xml" in names:
            comments = sum(1 for el in _safe_xml(zf.read("word/comments.xml")) if _local(el.tag) == "comment")
    return {**_empty(True), "images": images, "comments": comments, "shapes": shapes}


def _pdf_images(items) -> int:
    from pdfminer.layout import LTFigure, LTImage
    count = 0
    for item in items:
        if isinstance(item, LTImage):
            count += 1
        elif isinstance(item, LTFigure):
            count += _pdf_images(item)
    return count


def _pdf(path: Path) -> dict:
    from pdfminer.high_level import extract_pages
    from pypdf import PdfReader
    images = sum(_pdf_images(page) for page in extract_pages(str(path)))
    comments = 0
    for page in PdfReader(str(path)).pages:
        for ref in page.get("/Annots") or []:
            subtype = ref.get_object().get("/Subtype")
            if subtype not in ("/Link", "/Widget", "/Popup"):
                comments += 1
    return {**_empty(True), "images": images, "comments": comments}


def _md(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {**_empty(True), "images": len(_MD_IMAGE.findall(text))}


_BY_SUFFIX = {".xlsx": _xlsx, ".docx": _docx, ".pdf": _pdf, ".md": _md}


def scan(path: Path, suffix: str) -> dict:
    """形式で振り分けて数える。例外は外へ出さず、失敗は全 0＋scanned False。"""
    key = (suffix or "").lower()
    key = key if key.startswith(".") else f".{key}"
    func = _BY_SUFFIX.get(key)
    if func is None:
        return _empty(True)
    try:
        if key in (".docx", ".xlsx"):
            from web.services.docverify.ingest import has_xml_declarations
            if has_xml_declarations(Path(path)):
                return _empty(False)  # 宣言付きの XML は数えずに読み取りを止める
        return func(Path(path))
    except Exception as exc:  # noqa: BLE001 — 数えられないことは利用者に M-05 で伝える
        log.warning("unread.scan failed: path=%s suffix=%s error=%r", path, suffix, exc)
        return _empty(False)


def _join(parts: list[tuple[str, int]]) -> str:
    return "・".join(f"{label} {n}" for label, n in parts if n)


def lines(u: dict | None) -> list[str]:
    """9 章 M-01〜M-05 の文。画面と xlsx の共通文。"""
    if u is None:
        return ["読めなかった要素は数えていません。文書を取り込み直すと数えます。"]
    if not u.get("scanned", False):
        return ["読めなかった要素を数えられませんでした。画像やコメントが無いか、元の文書で確かめてください。"]
    out: list[str] = []
    unread = _join([("画像", u.get("images", 0)), ("コメント", u.get("comments", 0)), ("図形", u.get("shapes", 0))])
    if unread:
        out.append(f"{unread} は読んでいません。")
    hidden = _join([("非表示シート", u.get("hidden_sheets", 0)), ("非表示の行・列", u.get("hidden_cols", 0))])
    if hidden:
        out.append(f"{hidden} は読み取りました（画面では見えない内容です）。")
    return out or ["読めなかった要素はありません。"]
