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
    """PageData 一覧に連番の page_id を付与して AnalyzedPage を返す。

    同一 URL でも別レコード（別の画面状態など）は別 ID になるよう、
    URL 辞書ではなく出現順の連番で採番する。
    """
    return [
        AnalyzedPage(
            page_id=f"{PAGE_ID_PREFIX}{index:0{PAGE_ID_WIDTH}d}",
            page_data=page,
            buttons=page.buttons,
            nav_elements=tuple(_link_path(link) for link in page.links),
        )
        for index, page in enumerate(pages, start=1)
    ]


def assign_page_ids(pages: list[PageData]) -> dict[str, str]:
    """URL → page_id のマップを返す（後方互換用）。

    同一 URL が複数ある場合は最初の出現の ID を保持する
    （遷移グラフのリンク解決は正規ページ＝初出を指すのが自然なため）。
    """
    page_ids: dict[str, str] = {}
    for index, page in enumerate(pages, start=1):
        page_ids.setdefault(page.url, f"{PAGE_ID_PREFIX}{index:0{PAGE_ID_WIDTH}d}")
    return page_ids


def _link_path(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path or "/"
