"""観点の根拠（規格・ガイドライン）を出典へ解決する。

観点の `standards` は「ISO/IEC 25010 機能正確性」「OWASP ASVS 4.1」のように
規格名＋条項の形で書かれている。利用者が「なぜこの観点が必要か」を確かめるには
原典へ辿れる必要があるため、prefix の前方一致で出典 URL を引けるようにする。

出典の一覧は data/viewpoint_sources.json が持つ（kanten の根拠カタログを基に整備）。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent.parent
_SOURCES_FILE = _ROOT / "data" / "viewpoint_sources.json"


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    """出典カタログを読む。壊れていても観点表示は止めない（根拠が出ないだけ）。"""
    try:
        data = json.loads(_SOURCES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"levels": {}, "sources": []}
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
        return {"levels": {}, "sources": []}
    return data


@lru_cache(maxsize=1)
def _by_prefix() -> list[tuple[str, dict[str, Any]]]:
    """prefix の長い順に並べた (prefix, source) の一覧。

    「ISO/IEC 25010」と「ISO/IEC 27001」のように接頭辞が似るものがあるため、
    長いものから照合する。短い方が先に当たると誤った出典を返す。
    """
    pairs = [(str(s.get("prefix", "")), s) for s in _catalog()["sources"] if s.get("prefix")]
    return sorted(pairs, key=lambda x: -len(x[0]))


def list_sources() -> list[dict[str, Any]]:
    """出典の一覧をそのまま返す。"""
    return list(_catalog()["sources"])


def resolve(standards: str) -> dict[str, Any] | None:
    """`standards` の文字列から出典を引く。該当が無ければ None。

    条項部分（"OWASP ASVS 4.1" の "4.1"）は clause として切り出す。
    原典のどこを見ればよいかを利用者に示すため。
    """
    text = (standards or "").strip()
    if not text:
        return None
    for prefix, source in _by_prefix():
        if not text.startswith(prefix):
            continue
        clause = text[len(prefix) :].strip()
        return {
            "id": source.get("id", ""),
            "title": source.get("title", ""),
            "issuer": source.get("issuer", ""),
            "level": source.get("level", ""),
            "url": source.get("url", ""),
            "clause": clause,
            "note": source.get("note", ""),
        }
    return None


def attach_sources(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """観点の一覧に `source` を足した新しいリストを返す（引数は変更しない）。"""
    return [dict(item, source=resolve(str(item.get("standards", "")))) for item in items]
