"""OpenAPI 仕様生成の契約。

最重要は「実装済みのルートだけを載せること」。載っているのに動かない
エンドポイントは利用者にとって嘘になる。
"""

from __future__ import annotations

from web.services.openapi_docs import render_openapi_docs
from web.services.openapi_spec import build_openapi_spec


def _app():
    import app as appmod

    return appmod.app


def _spec() -> dict:
    return build_openapi_spec(_app())


# ─────────────────── 仕様の妥当性 ───────────────────


def test_spec_declares_openapi_version_info_and_paths() -> None:
    spec = _spec()

    assert spec["openapi"].startswith("3.0")
    assert spec["info"]["title"] == "WebSpec2Doc API"
    assert spec["info"]["version"]
    assert spec["paths"]


def test_every_listed_path_is_actually_registered() -> None:
    """仕様に載るパスは、すべてアプリに実在すること。"""
    registered = {
        str(rule.rule).replace("<domain>", "{domain}").replace("<job_id>", "{job_id}")
        for rule in _app().url_map.iter_rules()
    }

    for path in _spec()["paths"]:
        assert path in registered, f"仕様に未実装パスが載っている: {path}"


def test_only_api_v1_routes_are_included() -> None:
    assert all(path.startswith("/api/v1") for path in _spec()["paths"])


def test_flask_converters_are_rendered_as_openapi_placeholders() -> None:
    paths = _spec()["paths"]

    assert any("{domain}" in path for path in paths)
    assert all("<" not in path for path in paths)


def test_path_parameters_are_declared_as_required() -> None:
    spec = _spec()
    path = next(p for p in spec["paths"] if "{domain}" in p)
    operation = next(iter(spec["paths"][path].values()))

    names = {param["name"] for param in operation["parameters"]}
    assert "domain" in names
    assert all(param["required"] for param in operation["parameters"])


def test_head_and_options_are_not_exposed_as_operations() -> None:
    for methods in _spec()["paths"].values():
        assert "head" not in methods
        assert "options" not in methods


def test_mutating_operations_document_forbidden_response() -> None:
    spec = _spec()
    schedule = spec["paths"]["/api/v1/sites/{domain}/schedule"]

    assert "403" in schedule["put"]["responses"]
    assert "403" in schedule["delete"]["responses"]
    assert "403" not in schedule["get"]["responses"]


def test_write_operations_declare_json_request_body() -> None:
    put = _spec()["paths"]["/api/v1/sites/{domain}/schedule"]["put"]

    assert put["requestBody"]["required"] is True
    assert "application/json" in put["requestBody"]["content"]


def test_summary_comes_from_view_docstring() -> None:
    get = _spec()["paths"]["/api/v1/sites/{domain}/schedule"]["get"]

    assert "定期クロール設定" in get["summary"]


def test_operation_ids_are_unique() -> None:
    ids = [
        operation["operationId"]
        for methods in _spec()["paths"].values()
        for operation in methods.values()
    ]

    assert len(ids) == len(set(ids))


# ─────────────────── リファレンスHTML ───────────────────


def test_docs_html_is_self_contained_and_offline_safe() -> None:
    document = render_openapi_docs(_spec())

    assert "<script" not in document
    assert "https://" not in document
    assert "cdn" not in document.lower()


def test_docs_html_lists_methods_and_paths() -> None:
    document = render_openapi_docs(_spec())

    assert "/api/v1/sites/{domain}/schedule" in document
    assert "PUT" in document
    assert "DELETE" in document
