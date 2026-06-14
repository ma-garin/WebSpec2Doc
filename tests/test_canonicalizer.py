from __future__ import annotations

import json

from analyzer.canonicalizer import group_canonical_screens
from analyzer.html_analyzer import analyze_pages
from crawler.page_crawler import FieldData, FormData, PageData
from generator.json_reporter import generate_json_report
from graph.transition_graph import build_graph


def _field(name: str, field_type: str = "text", required: bool = False) -> FieldData:
    return FieldData(
        field_type=field_type,
        name=name,
        placeholder="",
        required=required,
    )


def _form(
    *,
    action: str = "/reserve/confirm",
    method: str = "POST",
    fields: tuple[FieldData, ...] | None = None,
) -> FormData:
    return FormData(
        action=action,
        method=method,
        fields=fields or (_field("email", field_type="email", required=True), _field("name")),
    )


def _page(url: str, forms: tuple[FormData, ...]) -> PageData:
    return PageData(
        url=url,
        title="Reserve",
        headings=("Reserve",),
        links=(),
        forms=forms,
        screenshot_path=None,
        buttons=("submit",),
    )


def test_group_canonical_screens_merges_query_only_variations() -> None:
    pages = analyze_pages(
        [
            _page("https://example.com/reserve.html?plan-id=4", (_form(),)),
            _page("https://example.com/reserve.html?plan-id=0", (_form(),)),
            _page("https://example.com/reserve.html?plan-id=2", (_form(),)),
        ]
    )

    grouped = group_canonical_screens(pages)

    assert grouped["P001"].canonical_key == "P001"
    assert grouped["P001"].is_canonical is True
    assert grouped["P001"].variation_count == 3
    assert grouped["P001"].variation_urls == (
        "https://example.com/reserve.html?plan-id=0",
        "https://example.com/reserve.html?plan-id=2",
    )
    assert grouped["P002"].canonical_key == "P001"
    assert grouped["P002"].is_canonical is False
    assert grouped["P002"].variation_count == 3
    assert grouped["P002"].variation_urls == ()
    assert grouped["P003"].canonical_key == "P001"


def test_group_canonical_screens_keeps_different_paths_separate() -> None:
    pages = analyze_pages(
        [
            _page("https://example.com/reserve.html?plan-id=1", (_form(),)),
            _page("https://example.com/confirm.html?plan-id=1", (_form(),)),
        ]
    )

    grouped = group_canonical_screens(pages)

    assert grouped["P001"].canonical_key == "P001"
    assert grouped["P001"].variation_count == 1
    assert grouped["P002"].canonical_key == "P002"
    assert grouped["P002"].variation_count == 1


def test_group_canonical_screens_keeps_different_form_structures_separate() -> None:
    pages = analyze_pages(
        [
            _page("https://example.com/reserve.html?plan-id=1", (_form(),)),
            _page(
                "https://example.com/reserve.html?plan-id=2",
                (_form(fields=(_field("email", field_type="email", required=True),)),),
            ),
        ]
    )

    grouped = group_canonical_screens(pages)

    assert grouped["P001"].canonical_key == "P001"
    assert grouped["P001"].variation_count == 1
    assert grouped["P002"].canonical_key == "P002"
    assert grouped["P002"].variation_count == 1


def test_generate_json_report_adds_screen_count_without_dropping_raw_screens() -> None:
    duplicate_pages = [
        _page(f"https://hotel.example.com/reserve.html?plan-id={plan_id}", (_form(),))
        for plan_id in range(7)
    ]
    distinct_page = _page(
        "https://hotel.example.com/confirm.html?step=1",
        (_form(action="/confirm", fields=(_field("token", required=True),)),),
    )
    analyzed = analyze_pages([*duplicate_pages, distinct_page])
    graph = build_graph(analyzed)

    report = json.loads(generate_json_report(analyzed, graph, duplicate_pages[0].url))

    assert report["meta"]["page_count"] == 8
    assert report["meta"]["screen_count"] == 2
    assert len(report["screens"]) == 8
    assert sum(1 for screen in report["screens"] if screen["is_canonical"]) == 2

    canonical_reserve = next(screen for screen in report["screens"] if screen["page_id"] == "P001")
    assert canonical_reserve["canonical_key"] == "P001"
    assert canonical_reserve["variation_count"] == 7
    assert canonical_reserve["variation_urls"] == [
        "https://hotel.example.com/reserve.html?plan-id=1",
        "https://hotel.example.com/reserve.html?plan-id=2",
        "https://hotel.example.com/reserve.html?plan-id=3",
        "https://hotel.example.com/reserve.html?plan-id=4",
        "https://hotel.example.com/reserve.html?plan-id=5",
        "https://hotel.example.com/reserve.html?plan-id=6",
    ]
