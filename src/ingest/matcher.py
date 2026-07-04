"""文書由来仕様と実測クロール結果の突合（Doc Fusion の中核）。

突合結果は 3 分類で報告する:
- 文書のみ（実装から消えた／未実装の疑い）
- 実測のみ（文書化漏れ）
- 両方にあるが記載が矛盾（必須・桁数の不一致）

矛盾は隠さず両方の根拠（文書 evidence / 実測 evidence）とともに提示する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from urllib.parse import urlparse

from analyzer.canonicalizer import group_canonical_screens
from analyzer.html_analyzer import AnalyzedPage
from crawler.page_crawler import FieldData
from ingest.models import DocumentBundle, DocumentedField, DocumentedScreen

_SCREEN_NAME_THRESHOLD = 0.6
_FIELD_NAME_THRESHOLD = 0.6


@dataclass(frozen=True)
class ScreenMatch:
    """文書上の画面と実測画面の対応。"""

    page_id: str
    page_url: str
    page_title: str
    screen: DocumentedScreen
    score: float
    method: str  # "url" / "name"


@dataclass(frozen=True)
class FieldGap:
    """項目レベルのギャップ（文書のみ / 実測のみ / 矛盾）。"""

    kind: str  # "doc_only" / "crawl_only" / "mismatch"
    page_id: str
    field_name: str
    detail: str
    doc_field: DocumentedField | None = None
    crawl_selector: str = ""


@dataclass(frozen=True)
class FusionResult:
    """突合結果一式。official_names は page_id → 文書上の正式画面名。"""

    screen_matches: tuple[ScreenMatch, ...]
    doc_only_screens: tuple[DocumentedScreen, ...]
    crawl_only_page_ids: tuple[str, ...]
    field_gaps: tuple[FieldGap, ...]
    official_names: dict[str, str] = field(default_factory=dict)


def fuse(pages: list[AnalyzedPage], bundle: DocumentBundle) -> FusionResult:
    """実測ページ一覧と文書一式を突合する。"""
    canonical_info = group_canonical_screens(pages)
    canonical_pages = [p for p in pages if canonical_info[p.page_id].is_canonical]

    matches = _match_screens(canonical_pages, bundle.screens)
    matched_page_ids = {m.page_id for m in matches}
    matched_screen_names = {m.screen.name for m in matches}

    doc_only = tuple(s for s in bundle.screens if s.name not in matched_screen_names)
    crawl_only = tuple(p.page_id for p in canonical_pages if p.page_id not in matched_page_ids)

    gaps: list[FieldGap] = []
    for match in matches:
        page = next(p for p in canonical_pages if p.page_id == match.page_id)
        doc_fields = _fields_for_screen(bundle, match.screen)
        gaps.extend(_match_fields(page, doc_fields))

    official_names = {m.page_id: m.screen.name for m in matches}
    return FusionResult(
        screen_matches=tuple(matches),
        doc_only_screens=doc_only,
        crawl_only_page_ids=crawl_only,
        field_gaps=tuple(gaps),
        official_names=official_names,
    )


def _normalize_path(url_or_path: str) -> str:
    parsed = urlparse(url_or_path)
    path = parsed.path or url_or_path
    return path.rstrip("/").lower() or "/"


def _name_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _screen_score(page: AnalyzedPage, screen: DocumentedScreen) -> tuple[float, str]:
    """画面同士の対応スコアを返す（URL 一致を最優先、次に名称類似）。"""
    if screen.url_hint and _normalize_path(screen.url_hint) == _normalize_path(page.page_data.url):
        return 1.0, "url"
    title_score = _name_similarity(screen.name, page.page_data.title)
    heading_score = max(
        (_name_similarity(screen.name, h) for h in page.page_data.headings), default=0.0
    )
    return max(title_score, heading_score), "name"


def _match_screens(
    pages: list[AnalyzedPage], screens: tuple[DocumentedScreen, ...]
) -> list[ScreenMatch]:
    """スコア降順の貪欲法で 1 対 1 の画面対応を作る。"""
    candidates: list[tuple[float, str, AnalyzedPage, DocumentedScreen]] = []
    for page in pages:
        for screen in screens:
            score, method = _screen_score(page, screen)
            if score >= _SCREEN_NAME_THRESHOLD:
                candidates.append((score, method, page, screen))
    candidates.sort(key=lambda item: item[0], reverse=True)
    used_pages: set[str] = set()
    used_screens: set[str] = set()
    matches: list[ScreenMatch] = []
    for score, method, page, screen in candidates:
        if page.page_id in used_pages or screen.name in used_screens:
            continue
        used_pages.add(page.page_id)
        used_screens.add(screen.name)
        matches.append(
            ScreenMatch(
                page_id=page.page_id,
                page_url=page.page_data.url,
                page_title=page.page_data.title,
                screen=screen,
                score=round(score, 3),
                method=method,
            )
        )
    return matches


def _fields_for_screen(bundle: DocumentBundle, screen: DocumentedScreen) -> list[DocumentedField]:
    """文書上でこの画面に属する項目を集める。

    画面参照が空の項目は、文書全体の画面が 1 つだけの場合に限りその画面に帰属させる。
    """
    keys = {screen.name, screen.screen_id} - {""}
    fields = [f for f in bundle.fields if f.screen_name in keys]
    if not fields and len(bundle.screens) == 1:
        fields = [f for f in bundle.fields if not f.screen_name]
    return fields


def _crawled_fields(page: AnalyzedPage) -> list[FieldData]:
    return [field for form in page.page_data.forms for field in form.fields]


def _field_score(doc_field: DocumentedField, crawled: FieldData) -> float:
    """項目同士の対応スコア（物理名の完全一致を最優先、次に論理名の類似）。"""
    physical = doc_field.physical_name.strip().lower()
    if physical and physical in (crawled.name.lower(), crawled.element_id.lower()):
        return 1.0
    return max(
        _name_similarity(doc_field.name, crawled.aria_label),
        _name_similarity(doc_field.name, crawled.placeholder),
        _name_similarity(doc_field.name, crawled.name),
    )


def _match_fields(page: AnalyzedPage, doc_fields: list[DocumentedField]) -> list[FieldGap]:
    crawled_fields = _crawled_fields(page)
    candidates: list[tuple[float, DocumentedField, FieldData]] = []
    for doc_field in doc_fields:
        for crawled in crawled_fields:
            score = _field_score(doc_field, crawled)
            if score >= _FIELD_NAME_THRESHOLD:
                candidates.append((score, doc_field, crawled))
    candidates.sort(key=lambda item: item[0], reverse=True)
    matched_doc: set[int] = set()
    matched_crawl: set[int] = set()
    pairs: list[tuple[DocumentedField, FieldData]] = []
    for _score, doc_field, crawled in candidates:
        if id(doc_field) in matched_doc or id(crawled) in matched_crawl:
            continue
        matched_doc.add(id(doc_field))
        matched_crawl.add(id(crawled))
        pairs.append((doc_field, crawled))

    gaps: list[FieldGap] = []
    for doc_field, crawled in pairs:
        gaps.extend(_mismatches(page.page_id, doc_field, crawled))
    for doc_field in doc_fields:
        if id(doc_field) not in matched_doc:
            gaps.append(
                FieldGap(
                    kind="doc_only",
                    page_id=page.page_id,
                    field_name=doc_field.name,
                    detail="文書に記載があるが実測画面に見つからない（実装から消えた/未実装の疑い）",
                    doc_field=doc_field,
                )
            )
    for crawled in crawled_fields:
        if id(crawled) not in matched_crawl:
            selector = crawled.evidence.selector if crawled.evidence else ""
            gaps.append(
                FieldGap(
                    kind="crawl_only",
                    page_id=page.page_id,
                    field_name=crawled.name or crawled.element_id or crawled.field_type,
                    detail="実測画面に存在するが文書に記載がない（文書化漏れ）",
                    crawl_selector=selector,
                )
            )
    return gaps


def _mismatches(page_id: str, doc_field: DocumentedField, crawled: FieldData) -> list[FieldGap]:
    """対応づいた項目の記載と実測の矛盾を検出する（文書未記載の属性は比較しない）。"""
    gaps: list[FieldGap] = []
    selector = crawled.evidence.selector if crawled.evidence else ""
    if doc_field.required is not None and doc_field.required != crawled.required:
        doc_label = "必須" if doc_field.required else "任意"
        crawl_label = "必須" if crawled.required else "任意"
        gaps.append(
            FieldGap(
                kind="mismatch",
                page_id=page_id,
                field_name=doc_field.name,
                detail=f"必須区分が矛盾: 文書では{doc_label}、実測では{crawl_label}",
                doc_field=doc_field,
                crawl_selector=selector,
            )
        )
    if (
        doc_field.max_length is not None
        and crawled.maxlength is not None
        and doc_field.max_length != crawled.maxlength
    ):
        gaps.append(
            FieldGap(
                kind="mismatch",
                page_id=page_id,
                field_name=doc_field.name,
                detail=(
                    f"桁数が矛盾: 文書では {doc_field.max_length}、" f"実測では {crawled.maxlength}"
                ),
                doc_field=doc_field,
                crawl_selector=selector,
            )
        )
    return gaps
