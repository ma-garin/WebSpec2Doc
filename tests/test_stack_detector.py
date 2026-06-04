from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from analyzer.stack_detector import (
    UNKNOWN,
    StackInfo,
    _collect_libraries,
    detect_stack,
)


def _make_page(info: dict) -> MagicMock:
    page = MagicMock()
    page.evaluate.return_value = info
    return page


def test_detect_react_next() -> None:
    page = _make_page({"hasNext": True, "hasReact": True, "reactVersion": "18.2.0"})
    result = detect_stack(page, {})
    assert "Next.js" in result.frontend_framework
    assert "SSR" in result.rendering_mode


def test_detect_vue3() -> None:
    page = _make_page({"hasVue3": True})
    result = detect_stack(page, {})
    assert result.frontend_framework == "Vue 3"
    assert result.rendering_mode == "SPA"


def test_detect_angular_with_version() -> None:
    page = _make_page({"hasAngular": True, "angularVersion": "17"})
    result = detect_stack(page, {})
    assert "Angular" in result.frontend_framework
    assert "17" in result.frontend_framework


def test_detect_unknown_when_no_markers() -> None:
    page = _make_page({})
    result = detect_stack(page, {})
    assert result.frontend_framework == UNKNOWN


def test_detect_tailwind() -> None:
    page = _make_page({"hasTailwind": True})
    result = detect_stack(page, {})
    assert result.css_framework == "Tailwind CSS"


def test_detect_backend_from_headers() -> None:
    page = _make_page({})
    result = detect_stack(page, {"Server": "nginx/1.24", "X-Powered-By": "Express"})
    assert any("nginx" in h for h in result.backend_hints)
    assert any("Express" in h for h in result.backend_hints)


def test_collect_libraries_multiple() -> None:
    info = {"hasReact": True, "hasRedux": True, "hasTailwind": True}
    libs = _collect_libraries(info)
    assert "React" in libs
    assert "Redux" in libs
    assert "Tailwind CSS" in libs


def test_playwright_error_fallback() -> None:
    from playwright.sync_api import Error as PlaywrightError

    page = MagicMock()
    page.evaluate.side_effect = PlaywrightError("JS error")
    result = detect_stack(page, {})
    assert isinstance(result, StackInfo)
    assert result.frontend_framework == UNKNOWN


def test_stack_info_is_immutable() -> None:
    page = _make_page({"hasVue3": True})
    result = detect_stack(page, {})
    with pytest.raises(AttributeError):
        result.frontend_framework = "changed"  # type: ignore[misc]
