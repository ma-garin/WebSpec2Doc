from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from crawler.page_crawler import PageData

PAGE_ID_PREFIX = "P"
PAGE_ID_WIDTH = 3


@dataclass(frozen=True)
class AnalyzedPage:
    page_id: str
    page_data: PageData
    buttons: tuple[str, ...]
    nav_elements: tuple[str, ...]


def analyze_pages(pages: list[PageData]) -> list[AnalyzedPage]:
    page_ids = assign_page_ids(pages)
    return [
        AnalyzedPage(
            page_id=page_ids[page.url],
            page_data=page,
            buttons=(),
            nav_elements=tuple(_link_path(link) for link in page.links),
        )
        for page in pages
    ]


def assign_page_ids(pages: list[PageData]) -> dict[str, str]:
    return {
        page.url: f"{PAGE_ID_PREFIX}{index:0{PAGE_ID_WIDTH}d}"
        for index, page in enumerate(pages, start=1)
    }


def _link_path(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path or "/"
