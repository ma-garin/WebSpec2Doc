from __future__ import annotations

from pathlib import Path

from crawler.playwright_runtime import (
    DEFAULT_BROWSERS_PATH,
    PLAYWRIGHT_BROWSERS_PATH_ENV,
    configure_playwright_browsers_path,
)


def test_configure_playwright_browsers_path_uses_project_runtime(monkeypatch) -> None:
    monkeypatch.delenv(PLAYWRIGHT_BROWSERS_PATH_ENV, raising=False)

    actual = configure_playwright_browsers_path()

    assert actual == DEFAULT_BROWSERS_PATH.resolve()
    assert actual.name == "ms-playwright"
    assert actual.parent.name == ".runtime"


def test_configure_playwright_browsers_path_respects_explicit_path(
    monkeypatch, tmp_path: Path
) -> None:
    configured = tmp_path / "browsers"
    monkeypatch.setenv(PLAYWRIGHT_BROWSERS_PATH_ENV, str(configured))

    actual = configure_playwright_browsers_path()

    assert actual == configured.resolve()
