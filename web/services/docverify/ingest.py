"""文書の取り込み。上限の検査と reverse_doc の読み取りを包む。"""
from __future__ import annotations

import re

import zipfile
from pathlib import Path

from web.vendor.reverse_doc.docs_ingest import readers

MAX_BYTES = 20 * 1024 * 1024
MAX_ZIP_TOTAL = 100 * 1024 * 1024
MAX_ZIP_ENTRIES = 2000
MAX_PDF_PAGES = 500
ALLOWED = (".txt", ".md", ".docx", ".xlsx", ".pdf")


class IngestError(Exception):
    """利用者向けの文（次の行動を 1 行含む）。"""


def unlock_pdf(path: Path) -> bool:
    """暗号化 PDF を空パスワードで解除し、同じ場所に書き戻す。解除したら True、暗号化なしは False。"""
    from pypdf import PdfReader, PdfWriter
    path = Path(path)
    try:
        reader = PdfReader(str(path))
        if not reader.is_encrypted:
            return False
        ok = reader.decrypt("")
    except Exception as exc:
        raise IngestError("PDF を開けませんでした。ファイルが壊れていないか確かめて取り込み直してください。") from exc
    if not ok:
        raise IngestError("この PDF は開くのにパスワードが要ります。パスワードを外したコピーを取り込んでください。")
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    tmp = path.with_suffix(".unlocked.pdf")
    with open(tmp, "wb") as fh:
        writer.write(fh)
    tmp.replace(path)
    return True


def _check_zip(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
    except (zipfile.BadZipFile, OSError) as exc:
        raise IngestError("文書が壊れているため読めませんでした。元のアプリで保存し直してから取り込んでください。") from exc
    if len(infos) > MAX_ZIP_ENTRIES:
        raise IngestError("文書の中身が多すぎます。分割してから取り込んでください。")
    if sum(i.file_size for i in infos) > MAX_ZIP_TOTAL:
        raise IngestError("文書を展開すると大きすぎます。画像を減らすか分割してから取り込んでください。")


def _check_pdf_pages(path: Path) -> None:
    from pypdf import PdfReader
    try:
        pages = len(PdfReader(str(path)).pages)
    except Exception as exc:
        raise IngestError("PDF を開けませんでした。ファイルが壊れていないか確かめて取り込み直してください。") from exc
    if pages > MAX_PDF_PAGES:
        raise IngestError(f"PDF が {MAX_PDF_PAGES} ページを超えています。必要な部分に分けてから取り込んでください。")


def _pdf_passages(path: Path) -> list[dict]:
    """PDF は pdfminer で 1 行ずつ読む。

    pypdf（reverse_doc の readers）は日本語の CID フォントを正しく文字に戻せず、文字化けした断片を作る
    （2026-10-06、POT_Specification_v6.pdf で確認）。
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer
    out: list[dict] = []
    try:
        for page_no, page in enumerate(extract_pages(str(path)), start=1):
            text = "".join(el.get_text() for el in page if isinstance(el, LTTextContainer))
            # PDF は表示幅で折り返されるので、行をつないでから「。」で文に分ける（文の途中で切ると規則が当たらない）
            joined = "".join(ln.strip() for ln in text.splitlines() if ln.strip())
            sentences = [x for x in re.split(r"(?<=。)", joined) if x.strip()]
            for no, sentence in enumerate(sentences, start=1):
                out.append({"id": f"P{len(out) + 1}", "text": sentence.strip(), "location": f"{page_no}頁 {no}文目"})
    except Exception as exc:
        raise IngestError("PDF を読み取れませんでした。別のコピーか、元の Word で取り込み直してください。") from exc
    return out


def ingest(filename: str, data: bytes, work_dir: Path) -> tuple[dict, list[dict]]:
    name = Path(filename or "").name
    suffix = Path(name).suffix.lower()
    if not name or suffix not in ALLOWED:
        raise IngestError("取り込めない形式です。txt / md / docx / xlsx / pdf のいずれかを選んでください。")
    if len(data) > MAX_BYTES:
        raise IngestError("ファイルが 20MB を超えています。分割してから取り込んでください。")
    if not data:
        raise IngestError("ファイルが空です。中身のある文書を選んでください。")
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / f"source{suffix}"
    path.write_bytes(data)
    if suffix in (".docx", ".xlsx"):
        _check_zip(path)
    if suffix == ".pdf":
        unlock_pdf(path)
        _check_pdf_pages(path)
    if suffix == ".pdf":
        passages = _pdf_passages(path)
    else:
        try:
            doc = readers.read_document(path)
        except readers.DocumentError as exc:
            raise IngestError(str(exc).replace(path.name, name)) from exc
        passages = [
            {"id": f"P{i}", "text": p.text, "location": p.locator.label()}
            for i, p in enumerate(doc.passages, start=1)
        ]
    if not passages:
        raise IngestError("文書から文章を読み取れませんでした。文字が画像になっていないか確かめてください。")
    document = {"name": name, "format": suffix.lstrip("."), "passages": len(passages), "version": 1}
    return document, passages
