"""pdf_reporter.py のユニットテスト（Playwright をモック）"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from generator.pdf_reporter import _wait_for_mermaid, generate_pdf


class TestGeneratePdf:
    def test_returns_pdf_path(self, tmp_path: Path) -> None:
        html_file = tmp_path / "report.html"
        html_file.write_text("<html><body>test</body></html>")
        pdf_file = tmp_path / "report.pdf"

        mock_page, mock_browser, mock_pw = _make_playwright_mocks()
        with patch("generator.pdf_reporter.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__.return_value = mock_pw
            result = generate_pdf(html_file, pdf_file)

        assert result == pdf_file

    def test_pdf_called_with_a4_format(self, tmp_path: Path) -> None:
        html_file = tmp_path / "report.html"
        html_file.write_text("<html></html>")
        pdf_file = tmp_path / "report.pdf"

        mock_page, mock_browser, mock_pw = _make_playwright_mocks()
        with patch("generator.pdf_reporter.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__.return_value = mock_pw
            generate_pdf(html_file, pdf_file)

        call_kwargs = mock_page.pdf.call_args[1]
        assert call_kwargs.get("format") == "A4"

    def test_goto_uses_file_uri(self, tmp_path: Path) -> None:
        html_file = tmp_path / "report.html"
        html_file.write_text("<html></html>")
        pdf_file = tmp_path / "report.pdf"

        mock_page, mock_browser, mock_pw = _make_playwright_mocks()
        with patch("generator.pdf_reporter.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__.return_value = mock_pw
            generate_pdf(html_file, pdf_file)

        goto_url = mock_page.goto.call_args[0][0]
        assert goto_url.startswith("file://")

    def test_print_background_enabled(self, tmp_path: Path) -> None:
        html_file = tmp_path / "report.html"
        html_file.write_text("<html></html>")
        pdf_file = tmp_path / "report.pdf"

        mock_page, mock_browser, mock_pw = _make_playwright_mocks()
        with patch("generator.pdf_reporter.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__.return_value = mock_pw
            generate_pdf(html_file, pdf_file)

        call_kwargs = mock_page.pdf.call_args[1]
        assert call_kwargs.get("print_background") is True

    def test_browser_closed_after_success(self, tmp_path: Path) -> None:
        html_file = tmp_path / "report.html"
        html_file.write_text("<html></html>")
        pdf_file = tmp_path / "report.pdf"

        mock_page, mock_browser, mock_pw = _make_playwright_mocks()
        with patch("generator.pdf_reporter.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__.return_value = mock_pw
            generate_pdf(html_file, pdf_file)

        mock_browser.close.assert_called_once()

    def test_browser_closed_on_error(self, tmp_path: Path) -> None:
        html_file = tmp_path / "report.html"
        html_file.write_text("<html></html>")
        pdf_file = tmp_path / "report.pdf"

        mock_page, mock_browser, mock_pw = _make_playwright_mocks()
        mock_page.goto.side_effect = RuntimeError("nav error")

        with patch("generator.pdf_reporter.sync_playwright") as mock_sp:
            mock_sp.return_value.__enter__.return_value = mock_pw
            with pytest.raises(RuntimeError):
                generate_pdf(html_file, pdf_file)

        mock_browser.close.assert_called_once()


class TestWaitForMermaid:
    def test_proceeds_when_selector_found(self) -> None:
        mock_page = MagicMock()
        _wait_for_mermaid(mock_page)
        mock_page.wait_for_selector.assert_called_once()

    def test_does_not_raise_on_timeout(self) -> None:
        mock_page = MagicMock()
        mock_page.wait_for_selector.side_effect = Exception("timeout")
        _wait_for_mermaid(mock_page)

    def test_does_not_raise_on_any_exception(self) -> None:
        mock_page = MagicMock()
        mock_page.wait_for_selector.side_effect = RuntimeError("unexpected")
        _wait_for_mermaid(mock_page)


def _make_playwright_mocks() -> tuple[MagicMock, MagicMock, MagicMock]:
    mock_page = MagicMock()
    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page
    mock_chromium = MagicMock()
    mock_chromium.launch.return_value = mock_browser
    mock_pw = MagicMock()
    mock_pw.chromium = mock_chromium
    return mock_page, mock_browser, mock_pw
