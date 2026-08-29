from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from analyzer.html_analyzer import AnalyzedPage
from crawler.page_crawler import FieldData, FormData

logger = logging.getLogger(__name__)


# fingerprint バージョン:
#   v1: 正規化URL＋フォーム構造
#   v2: 正規化URL＋DOM状態シグネチャ（landmark構造＋開閉状態）＋フォーム構造
FINGERPRINT_VERSION_STRUCTURE = 1
FINGERPRINT_VERSION_STATE = 2
DEFAULT_FINGERPRINT_VERSION = FINGERPRINT_VERSION_STATE


@dataclass(frozen=True)
class CanonicalInfo:
    canonical_key: str
    is_canonical: bool
    variation_count: int
    variation_urls: tuple[str, ...]
    fingerprint: str = ""
    fingerprint_version: int = DEFAULT_FINGERPRINT_VERSION


def screen_fingerprint(
    page: AnalyzedPage,
    version: int = DEFAULT_FINGERPRINT_VERSION,
) -> str:
    """画面同定用の fingerprint を計算する。

    version=1 は旧来の「正規化URL＋フォーム構造」、version=2 は状態ベース
    （DOM 状態シグネチャを追加）。既存スナップショット（state_id="default"）でも
    v2 は v1 と同等の粒度に退化するため後方互換が保たれる。
    """
    normalized_url = _normalize_url(page.page_data.url)
    structure_signature = _structure_signature(page.page_data.forms)
    if version == FINGERPRINT_VERSION_STRUCTURE:
        raw_fingerprint = f"{normalized_url}\n{structure_signature}"
    else:
        state_id = page.page_data.state_id or "default"
        raw_fingerprint = f"{normalized_url}\nstate:{state_id}\n{structure_signature}"
    fingerprint = hashlib.sha1(raw_fingerprint.encode("utf-8"), usedforsecurity=False).hexdigest()[
        :16
    ]  # noqa: S324
    logger.debug("Computed fingerprint (v%d) for %s: %s", version, page.page_id, fingerprint)
    return fingerprint


def group_canonical_screens(
    pages: Sequence[AnalyzedPage],
    version: int = DEFAULT_FINGERPRINT_VERSION,
) -> dict[str, CanonicalInfo]:
    grouped_pages: dict[str, list[AnalyzedPage]] = defaultdict(list)
    for page in pages:
        grouped_pages[screen_fingerprint(page, version)].append(page)

    canonical_map: dict[str, CanonicalInfo] = {}
    for fingerprint, members in grouped_pages.items():
        sorted_members = sorted(members, key=lambda page: page.page_id)
        canonical_page = sorted_members[0]
        variation_urls = tuple(page.page_data.url for page in sorted_members[1:])
        variation_count = len(sorted_members)

        for page in sorted_members:
            canonical_map[page.page_id] = CanonicalInfo(
                canonical_key=canonical_page.page_id,
                is_canonical=page.page_id == canonical_page.page_id,
                variation_count=variation_count,
                variation_urls=variation_urls if page.page_id == canonical_page.page_id else (),
                fingerprint=fingerprint,
                fingerprint_version=version,
            )

        logger.debug(
            "Grouped fingerprint %s into canonical page %s with %d variations",
            fingerprint,
            canonical_page.page_id,
            variation_count,
        )

    logger.info(
        "Grouped %d pages into %d canonical screens",
        len(pages),
        sum(1 for info in canonical_map.values() if info.is_canonical),
    )
    return canonical_map


def _normalize_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _structure_signature(forms: tuple[FormData, ...]) -> str:
    normalized_forms = [
        {
            "action": _normalize_url(form.action),
            "method": form.method.lower(),
            "fields": [
                (field.field_type, field.name, field.required)
                for field in sorted(form.fields, key=_field_sort_key)
            ],
        }
        for form in forms
    ]
    return json.dumps(normalized_forms, ensure_ascii=False, separators=(",", ":"))


def _field_sort_key(field: FieldData) -> tuple[str, str, bool]:
    return (field.name, field.field_type, field.required)
