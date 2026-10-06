"""ドキュメント検証（System 06）。文書の読み取りと曖昧語の検出は reverse_doc を使う。

第 1 段は保存しない: 取り込み 1 回で指摘と質問票を返す（保存しないのでテナントをまたぐ漏れも起きない）。
Doc2AI-Friendly は新版ができてから接続する（旧 MVP は 2026-10-06 に退避された）。
reverse_doc の場所は WEBSPEC2DOC_REVERSE_DOC_SRC（既定はリポジトリと同じ階層の reverse_doc/src）。
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

bp = Blueprint("doc_verify", __name__)
log = logging.getLogger(__name__)

_MAX_BYTES = 20 * 1024 * 1024
_SUFFIXES = (".txt", ".md", ".docx", ".xlsx", ".pdf")
_DEFAULT_SRC = Path(__file__).resolve().parents[2].parent / "reverse_doc" / "src"
_VIEWPOINTS = ["曖昧な表現"]


def _reverse_doc():
    src = os.environ.get("WEBSPEC2DOC_REVERSE_DOC_SRC") or str(_DEFAULT_SRC)
    if src not in sys.path:
        sys.path.append(src)
    from reverse_doc.ambiguity import ambiguous_words
    from reverse_doc.docs_ingest.readers import DocumentError, read_document
    return ambiguous_words, DocumentError, read_document


def _err(message: str, status: int):
    return jsonify(error=message), status


def _findings(doc, ambiguous_words) -> list[dict]:
    out: list[dict] = []
    for p in doc.passages:
        for word in ambiguous_words(p.text):
            out.append({
                "id": f"F{len(out) + 1}", "severity": "warning", "viewpoint": "曖昧な表現",
                "certainty": "要確認", "word": word, "location": p.locator.label(),
                "message": f"「{word}」は合否を判定できない。具体的な条件や数値が要る",
                "quote": p.text[:400],
            })
    return out


def _questions(findings: list[dict]) -> list[dict]:
    return [{"id": f"Q{i}", "finding_id": f["id"], "location": f["location"],
             "question": f"{f['location']}の「{f['word']}」は、具体的にどの条件・数値を指しますか。"}
            for i, f in enumerate(findings, 1)]


@bp.route("/docverify")
def page() -> str:
    return render_template("doc_verify.html")


@bp.route("/api/docverify/inspect", methods=["POST"])
def inspect():
    f = request.files.get("file")
    if f is None or not f.filename:
        return _err("ファイルが選ばれていません。検証する文書を選んでください。", 400)
    display = Path(f.filename).name[:120]
    suffix = Path(display).suffix.lower()
    if suffix not in _SUFFIXES:
        return _err(f"「{display}」は取り込めない形式です。{' / '.join(_SUFFIXES)} のいずれかを選んでください。", 400)
    data = f.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        return _err(f"「{display}」は 20 MB を超えています。必要な部分だけにして取り込んでください。", 400)
    try:
        ambiguous_words, DocumentError, read_document = _reverse_doc()
    except ImportError:
        log.exception("reverse_doc を読み込めない")
        return _err("検証の部品を読み込めませんでした。管理者に連絡してください。", 503)
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / f"upload{suffix}"
        path.write_bytes(data)
        try:
            doc = read_document(path)
        except DocumentError as e:
            return _err(str(e).replace(path.name, display), 400)
        except Exception:
            log.exception("文書の読み取りに失敗")
            return _err(f"「{display}」を読み取れませんでした。別のコピーで取り込み直してください。", 500)
    if not doc.passages:
        return _err(f"「{display}」から文字を読み取れませんでした。文字を選択できる PDF か、元の Word で取り込み直してください。", 400)
    findings = _findings(doc, ambiguous_words)
    return jsonify(
        document={"name": display, "format": suffix[1:], "passages": len(doc.passages)},
        findings=findings, questions=_questions(findings),
        checked={"passages": len(doc.passages), "viewpoints": _VIEWPOINTS},
    )
