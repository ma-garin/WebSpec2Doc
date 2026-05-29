from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import sync_playwright

PDF_PAGE_FORMAT = "A4"
_MERMAID_SELECTOR = "svg[id^='mermaid']"
_MERMAID_TIMEOUT_MS = 3_000

logger = logging.getLogger(__name__)


def generate_pdf(html_path: Path, pdf_path: Path) -> Path:
    """Render report.html to PDF via Playwright headless Chromium."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            _wait_for_mermaid(page)
            page.pdf(path=str(pdf_path), format=PDF_PAGE_FORMAT, print_background=True)
        finally:
            browser.close()

    logger.info("PDF 出力完了: %s", pdf_path)
    return pdf_path


def _wait_for_mermaid(page: object) -> None:
    try:
        page.wait_for_selector(_MERMAID_SELECTOR, timeout=_MERMAID_TIMEOUT_MS)  # type: ignore[union-attr]
    except Exception:
        logger.warning(
            "Mermaid SVG が検出できませんでした。遷移図が PDF に含まれない可能性があります"
        )
