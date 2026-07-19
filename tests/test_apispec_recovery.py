"""API仕様逆生成の契約。

守るべきは「観測していないことを書かないこと」。パラメータの必須性や型を
推測で埋めると、雛形が誤った仕様書として独り歩きする。
"""

from __future__ import annotations

from apispec.recovery import (
    CLAIM_NOTICE,
    build_openapi_draft,
    build_screen_api_map,
    templatize_path,
)
from crawler.page_crawler import ApiEndpoint, PageData


def _page(url: str, calls=()) -> PageData:
    return PageData(
        url=url,
        title="画面",
        headings=(),
        links=(),
        forms=(),
        screenshot_path="",
        api_calls=tuple(calls),
    )


def _call(method="GET", path="/api/users", status=200, fields=("id", "name")) -> ApiEndpoint:
    return ApiEndpoint(
        method=method,
        path=path,
        status_code=status,
        content_type="application/json",
        sample_fields=tuple(fields),
    )


# ─────────────────── パスの正規化 ───────────────────


def test_numeric_segment_becomes_id_parameter() -> None:
    assert templatize_path("/api/users/42/orders/7") == "/api/users/{id}/orders/{id}"


def test_uuid_segment_is_parameterized() -> None:
    path = "/api/items/6f0e2b3c-1a2b-4c3d-8e9f-0a1b2c3d4e5f"

    assert templatize_path(path) == "/api/items/{uuid}"


def test_date_segment_is_parameterized() -> None:
    assert templatize_path("/api/reports/2026-07-19") == "/api/reports/{date}"


def test_static_segments_are_preserved() -> None:
    assert templatize_path("/api/users/profile") == "/api/users/profile"


def test_query_string_is_dropped_from_template() -> None:
    assert templatize_path("/api/search?q=hotel&page=2") == "/api/search"


# ─────────────────── 画面↔API 対応表 ───────────────────


def test_map_links_calls_to_the_screen_that_fired_them() -> None:
    pages = [_page("https://e.com/list", [_call(path="/api/users")])]

    result = build_screen_api_map(pages)

    assert result["screens"][0]["page_url"] == "https://e.com/list"
    assert result["screens"][0]["calls"][0]["template"] == "/api/users"


def test_screens_without_api_calls_are_omitted() -> None:
    pages = [_page("https://e.com/static"), _page("https://e.com/list", [_call()])]

    result = build_screen_api_map(pages)

    assert [screen["page_url"] for screen in result["screens"]] == ["https://e.com/list"]
    assert result["summary"]["screens_with_api"] == 1


def test_summary_counts_observed_calls() -> None:
    pages = [
        _page("https://e.com/a", [_call(path="/api/x"), _call(path="/api/y")]),
        _page("https://e.com/b", [_call(path="/api/z")]),
    ]

    assert build_screen_api_map(pages)["summary"]["observed_calls"] == 3


def test_claim_scope_is_declared_on_the_map() -> None:
    result = build_screen_api_map([])

    assert result["meta"]["claim_scope"] == "observed_calls_only"
    assert result["meta"]["claim_notice"] == CLAIM_NOTICE


# ─────────────────── OpenAPI 雛形 ───────────────────


def test_draft_declares_openapi_version_and_claim_notice() -> None:
    draft = build_openapi_draft([_page("https://e.com/", [_call()])])

    assert draft["openapi"].startswith("3.0")
    assert draft["info"]["description"] == CLAIM_NOTICE
    assert draft["info"]["version"] == "draft"


def test_draft_groups_calls_under_templated_paths() -> None:
    pages = [
        _page("https://e.com/a", [_call(path="/api/users/1")]),
        _page("https://e.com/b", [_call(path="/api/users/2")]),
    ]

    draft = build_openapi_draft(pages)

    assert list(draft["paths"]) == ["/api/users/{id}"]


def test_draft_records_which_screens_observed_the_call() -> None:
    pages = [
        _page("https://e.com/a", [_call(path="/api/users")]),
        _page("https://e.com/b", [_call(path="/api/users")]),
    ]

    operation = build_openapi_draft(pages)["paths"]["/api/users"]["get"]

    assert operation["x-observed-from"] == ["https://e.com/a", "https://e.com/b"]


def test_response_schema_lists_only_observed_keys_without_guessing_types() -> None:
    draft = build_openapi_draft([_page("https://e.com/", [_call(fields=("name", "id"))])])

    schema = draft["paths"]["/api/users"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]

    assert schema["type"] == "object"
    assert sorted(schema["properties"]) == ["id", "name"]
    assert all(value == {} for value in schema["properties"].values())


def test_multiple_status_codes_are_kept_separately() -> None:
    pages = [_page("https://e.com/", [_call(status=200), _call(status=404, fields=("error",))])]

    responses = build_openapi_draft(pages)["paths"]["/api/users"]["get"]["responses"]

    assert sorted(responses) == ["200", "404"]


def test_path_parameters_are_declared_required() -> None:
    draft = build_openapi_draft([_page("https://e.com/", [_call(path="/api/users/9")])])

    parameters = draft["paths"]["/api/users/{id}"]["get"]["parameters"]

    assert parameters[0]["name"] == "id"
    assert parameters[0]["required"] is True


def test_summary_is_left_blank_rather_than_invented() -> None:
    operation = build_openapi_draft([_page("https://e.com/", [_call()])])["paths"]["/api/users"][
        "get"
    ]

    assert operation["summary"] == ""
    assert "未観測" in operation["description"]


def test_methods_are_separated_per_path() -> None:
    pages = [_page("https://e.com/", [_call(method="GET"), _call(method="POST")])]

    assert sorted(build_openapi_draft(pages)["paths"]["/api/users"]) == ["get", "post"]
