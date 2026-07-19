"""sitemap / PDF 文書の外形監視。

QA ユースケースに重なる範囲だけを扱う: 「テスト対象の画面が増減したか」
「参照している PDF が差し替わったか」を検知する。

主張境界: 検知できるのは**取得できた内容の変化**のみ。
変化が問題かどうかは判断しない。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any
from xml.etree.ElementTree import ParseError

# 外部から取得したXMLを解析するため、XXE・billion laughs に耐える実装を使う。
from defusedxml import ElementTree as SafeElementTree

CLAIM_SCOPE = "fetched_content_changes_only"

CLAIM_NOTICE = "本結果は取得できた内容の変化の記録であり、変化の是非は判定しない。"

_SITEMAP_NS = re.compile(r"^\{[^}]+\}")


@dataclass(frozen=True)
class SitemapDiff:
    added: tuple[str, ...]
    removed: tuple[str, ...]
    unchanged_count: int

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed)


def parse_sitemap(xml_text: str) -> list[str]:
    """sitemap.xml から URL を取り出す。壊れていれば空で返す（例外にしない）。"""
    try:
        root = SafeElementTree.fromstring(xml_text)
    except (ParseError, ValueError):
        return []
    urls: list[str] = []
    for element in root.iter():
        tag = _SITEMAP_NS.sub("", element.tag)
        if tag == "loc" and element.text:
            urls.append(element.text.strip())
    return urls


def diff_sitemaps(previous: list[str], current: list[str]) -> SitemapDiff:
    """前回と今回の sitemap を比較する。"""
    before, after = set(previous), set(current)
    return SitemapDiff(
        added=tuple(sorted(after - before)),
        removed=tuple(sorted(before - after)),
        unchanged_count=len(before & after),
    )


@dataclass(frozen=True)
class DocumentFingerprint:
    url: str
    sha256: str
    bytes: int


def fingerprint_document(url: str, content: bytes) -> DocumentFingerprint:
    """PDF等の文書を内容ハッシュで指紋化する。"""
    return DocumentFingerprint(
        url=url, sha256=hashlib.sha256(content).hexdigest(), bytes=len(content)
    )


def diff_documents(
    previous: list[DocumentFingerprint], current: list[DocumentFingerprint]
) -> dict[str, Any]:
    """文書の追加・削除・差し替えを検出する。"""
    before = {item.url: item for item in previous}
    after = {item.url: item for item in current}

    replaced = [
        {
            "url": url,
            "before_sha256": before[url].sha256,
            "after_sha256": after[url].sha256,
        }
        for url in sorted(before.keys() & after.keys())
        if before[url].sha256 != after[url].sha256
    ]
    return {
        "meta": {"claim_scope": CLAIM_SCOPE, "claim_notice": CLAIM_NOTICE},
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
        "replaced": replaced,
        "summary": {
            "added": len(after.keys() - before.keys()),
            "removed": len(before.keys() - after.keys()),
            "replaced": len(replaced),
        },
    }
