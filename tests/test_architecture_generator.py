from __future__ import annotations

"""architecture_generator のユニットテスト。"""

from analyzer.stack_detector import StackInfo
from crawler.page_crawler import ApiEndpoint
from generator.architecture_generator import (
    UNKNOWN,
    _backend_label,
    _edge_label,
    _frontend_label,
    _representative_paths,
    generate_architecture_mermaid,
    merge_api_endpoints,
    merge_stack_infos,
)


def _stack(
    frontend: str = UNKNOWN,
    rendering: str = UNKNOWN,
    css: str = UNKNOWN,
    state: str = UNKNOWN,
    backend: tuple[str, ...] = (),
    libs: tuple[str, ...] = (),
) -> StackInfo:
    return StackInfo(
        frontend_framework=frontend,
        rendering_mode=rendering,
        css_framework=css,
        state_management=state,
        backend_hints=backend,
        detected_libraries=libs,
    )


def _ep(method: str = "GET", path: str = "/api/test", status: int = 200) -> ApiEndpoint:
    return ApiEndpoint(method=method, path=path, status_code=status, content_type="application/json", sample_fields=())


def test_generate_contains_mermaid_header() -> None:
    result = generate_architecture_mermaid("example.com", None, ())
    assert result.startswith("graph TD")


def test_generate_with_react_next() -> None:
    stack = _stack(frontend="React / Next.js", rendering="SSR / Next.js")
    result = generate_architecture_mermaid("example.com", stack, ())
    assert "Next.js" in result
    assert "SSR" in result


def test_generate_with_api_endpoints() -> None:
    endpoints = (_ep(path="/api/users"), _ep(method="POST", path="/api/login"))
    result = generate_architecture_mermaid("example.com", None, endpoints)
    assert "/api/users" in result
    assert "/api/login" in result
    assert "APIGROUP" in result


def test_generate_without_endpoints_no_subgraph() -> None:
    result = generate_architecture_mermaid("example.com", None, ())
    assert "APIGROUP" not in result


def test_generate_css_framework_shown() -> None:
    stack = _stack(css="Tailwind CSS")
    result = generate_architecture_mermaid("example.com", stack, ())
    assert "Tailwind CSS" in result


def test_representative_paths_dedup() -> None:
    endpoints = (_ep(path="/api/x"), _ep(path="/api/x"), _ep(path="/api/y"))
    paths = _representative_paths(endpoints)
    assert paths[0] == "/api/x"  # most frequent
    assert "/api/y" in paths


def test_merge_stack_infos_picks_best() -> None:
    s1 = _stack(frontend=UNKNOWN)
    s2 = _stack(frontend="React", rendering="SPA", css="Tailwind CSS")
    result = merge_stack_infos([s1, s2])
    assert result is not None
    assert result.frontend_framework == "React"


def test_merge_stack_infos_empty() -> None:
    assert merge_stack_infos([]) is None


def test_merge_api_endpoints_dedup() -> None:
    ep1 = _ep(path="/api/users")
    ep2 = _ep(path="/api/users")  # duplicate
    ep3 = _ep(path="/api/items")
    result = merge_api_endpoints([[ep1], [ep2, ep3]])
    paths = {ep.path for ep in result}
    assert paths == {"/api/users", "/api/items"}


def test_frontend_label_unknown() -> None:
    label = _frontend_label(None)
    assert "フロントエンド" in label
    assert "不明" in label


def test_backend_label_with_hint() -> None:
    stack = _stack(backend=("Server: nginx",))
    label = _backend_label(stack)
    assert "nginx" in label


def test_edge_label_shows_count() -> None:
    endpoints = (_ep("GET", "/api/a"), _ep("POST", "/api/b"), _ep("PUT", "/api/c"))
    label = _edge_label(endpoints)
    assert "3" in label
    assert "GET" in label
