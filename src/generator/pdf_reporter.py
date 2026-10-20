from __future__ import annotations

import logging
from pathlib import Path

from browser_detect import launch_browser
from playwright.sync_api import sync_playwright

PDF_PAGE_FORMAT = "A4"
_DIAGRAM_SELECTOR = "svg.wsd-diagram"
_DIAGRAM_TIMEOUT_MS = 3_000

logger = logging.getLogger(__name__)


def generate_pdf(html_path: Path, pdf_path: Path) -> Path:
    """Render report.html to PDF via Playwright headless Chromium."""
    with sync_playwright() as pw:
        browser = launch_browser(pw)
        try:
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri(), wait_until="load")
            _check_static_diagrams(page)
            page.pdf(path=str(pdf_path), format=PDF_PAGE_FORMAT, print_background=True)
        finally:
            browser.close()

    logger.info("PDF 出力完了: %s", pdf_path)
    return pdf_path


def _check_static_diagrams(page: object) -> None:
    """図は生成時に静的 SVG として埋め込まれている。存在確認だけして待機はしない。"""
    try:
        found = page.query_selector(_DIAGRAM_SELECTOR)  # type: ignore[attr-defined]
    except Exception:
        found = None
    if found is None:
        logger.warning("図の SVG が検出できませんでした。遷移図が PDF に含まれない可能性があります")
