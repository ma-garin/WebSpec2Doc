from __future__ import annotations

from pathlib import Path

from crawler.page_crawler import FieldData, FormData, PageData
from diff.differ import (
    CHANGE_ADDED,
    CHANGE_MODIFIED,
    CHANGE_REMOVED,
    compute_diff,
)
from diff.snapshot import latest_snapshot, load_snapshot, save_snapshot
from generator.diff_reporter import generate_diff_report


def test_snapshot_round_trip(tmp_path: Path) -> None:
    pages = [_page("https://example.com/", "Top", links=("https://example.com/a",))]

    snapshot_path = save_snapshot(pages, tmp_path)
    loaded = load_snapshot(snapshot_path)

    assert loaded == pages
    assert latest_snapshot(tmp_path) == snapshot_path


def test_compute_diff_detects_page_added_and_removed() -> None:
    old = [_page("https://example.com/old", "Old")]
    new = [_page("https://example.com/new", "New")]

    diff = compute_diff(old, new)

    assert diff.added_pages[0].url == "https://example.com/new"
    assert diff.added_pages[0].change_type == CHANGE_ADDED
    assert diff.removed_pages[0].url == "https://example.com/old"
    assert diff.removed_pages[0].change_type == CHANGE_REMOVED
    assert diff.has_changes is True


def test_compute_diff_detects_field_added_removed_and_modified() -> None:
    old = [
        _page(
            "https://example.com/contact",
            "Contact",
            fields=(
                FieldData("text", "name", "Name", True),
                FieldData("email", "email", "Email", True),
            ),
        )
    ]
    new = [
        _page(
            "https://example.com/contact",
            "Contact",
            fields=(
                FieldData("text", "name", "Full name", True),
                FieldData("tel", "phone", "Phone", False),
            ),
        )
    ]

    diff = compute_diff(old, new)
    by_name = {change.field_name: change for change in diff.field_changes}

    assert by_name["phone"].change_type == CHANGE_ADDED
    assert by_name["email"].change_type == CHANGE_REMOVED
    assert by_name["name"].change_type == CHANGE_MODIFIED
    assert by_name["name"].before == FieldData("text", "name", "Name", True)
    assert by_name["name"].after == FieldData("text", "name", "Full name", True)


def test_compute_diff_detects_link_changes() -> None:
    old = [_page("https://example.com/", "Top", links=("https://example.com/a",))]
    new = [_page("https://example.com/", "Top", links=("https://example.com/b",))]

    diff = compute_diff(old, new)
    by_link = {change.link: change for change in diff.link_changes}

    assert by_link["https://example.com/b"].change_type == CHANGE_ADDED
    assert by_link["https://example.com/a"].change_type == CHANGE_REMOVED


def test_compute_diff_detects_title_change() -> None:
    old = [_page("https://example.com/", "Before")]
    new = [_page("https://example.com/", "After")]

    diff = compute_diff(old, new)

    assert diff.title_changes[0].before == "Before"
    assert diff.title_changes[0].after == "After"


def test_compute_diff_without_changes() -> None:
    pages = [_page("https://example.com/", "Top")]

    diff = compute_diff(pages, list(pages))

    assert diff.has_changes is False
    assert diff.added_pages == ()
    assert diff.removed_pages == ()
    assert diff.field_changes == ()
    assert diff.link_changes == ()
    assert diff.title_changes == ()


def test_generate_diff_report_escapes_values() -> None:
    old = [_page("https://example.com/", "<b>Before</b>")]
    new = [_page("https://example.com/", "<script>alert(1)</script>")]

    report = generate_diff_report(
        compute_diff(old, new),
        "old<script>",
        "new<script>",
        "https://example.com/?q=<script>",
    )

    assert "<script>alert" not in report
    assert "&lt;script&gt;" in report
    assert "仕様ドリフトレポート" in report


def _page(
    url: str,
    title: str,
    links: tuple[str, ...] = (),
    fields: tuple[FieldData, ...] = (),
) -> PageData:
    forms = (FormData(action="/submit", method="post", fields=fields),) if fields else ()
    return PageData(
        url=url,
        title=title,
        headings=("Heading",),
        links=links,
        forms=forms,
        screenshot_path="/tmp/screenshot.png",
    )
