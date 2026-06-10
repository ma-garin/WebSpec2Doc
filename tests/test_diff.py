from __future__ import annotations

from pathlib import Path

from crawler.page_crawler import ApiEndpoint, FieldData, FormData, PageData
from diff.differ import (
    CHANGE_ADDED,
    CHANGE_MODIFIED,
    CHANGE_REMOVED,
    SEVERITY_BREAKING,
    SEVERITY_WARNING,
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


def test_snapshot_restores_all_field_attributes(tmp_path: Path) -> None:
    field = FieldData(
        field_type="text",
        name="username",
        placeholder="Enter name",
        required=True,
        maxlength=50,
        minlength=3,
        min_value="",
        max_value="",
        pattern=r"^[a-z]+$",
        default="alice",
        options=("a", "b", "c"),
        element_id="id-username",
    )
    pages = [_page("https://example.com/", "Top", fields=(field,))]

    snapshot_path = save_snapshot(pages, tmp_path)
    loaded = load_snapshot(snapshot_path)

    restored_field = loaded[0].forms[0].fields[0]
    assert restored_field.maxlength == 50
    assert restored_field.minlength == 3
    assert restored_field.pattern == r"^[a-z]+$"
    assert restored_field.default == "alice"
    assert restored_field.options == ("a", "b", "c")
    assert restored_field.element_id == "id-username"
    assert restored_field == field


def test_field_modified_detects_maxlength_change() -> None:
    url = "https://example.com/form"
    old = [_page(url, "Form", fields=(FieldData("text", "q", "", False, maxlength=100),))]
    new = [_page(url, "Form", fields=(FieldData("text", "q", "", False, maxlength=200),))]

    diff = compute_diff(old, new)

    assert len(diff.field_changes) == 1
    assert diff.field_changes[0].change_type == CHANGE_MODIFIED
    assert diff.field_changes[0].field_name == "q"


def test_field_modified_detects_pattern_change() -> None:
    url = "https://example.com/form"
    old = [_page(url, "Form", fields=(FieldData("text", "code", "", False, pattern=r"\d{4}"),))]
    new = [_page(url, "Form", fields=(FieldData("text", "code", "", False, pattern=r"\d{6}"),))]

    diff = compute_diff(old, new)

    assert len(diff.field_changes) == 1
    assert diff.field_changes[0].change_type == CHANGE_MODIFIED


def test_field_modified_detects_options_change() -> None:
    url = "https://example.com/form"
    old_field = FieldData("select", "color", "", False, options=("red", "blue"))
    new_field = FieldData("select", "color", "", False, options=("red", "blue", "green"))
    old = [_page(url, "Form", fields=(old_field,))]
    new = [_page(url, "Form", fields=(new_field,))]

    diff = compute_diff(old, new)

    assert len(diff.field_changes) == 1
    assert diff.field_changes[0].change_type == CHANGE_MODIFIED
    assert diff.field_changes[0].before == old_field
    assert diff.field_changes[0].after == new_field


def test_attribute_diffs_classify_severity() -> None:
    url = "https://example.com/form"
    before_field = FieldData("text", "email", "", required=True, maxlength=100, pattern="")
    after_field = FieldData("text", "email", "", required=False, maxlength=50, pattern=r".+@.+")
    old = [_page(url, "Form", fields=(before_field,))]
    new = [_page(url, "Form", fields=(after_field,))]

    diff = compute_diff(old, new)

    by_attr = {ad.attribute: ad for ad in diff.attribute_diffs}
    assert by_attr["required"].severity == SEVERITY_BREAKING
    assert by_attr["maxlength"].severity == SEVERITY_WARNING
    assert by_attr["pattern"].severity == SEVERITY_WARNING


def _page(
    url: str,
    title: str,
    links: tuple[str, ...] = (),
    fields: tuple[FieldData, ...] = (),
    api_calls: tuple[ApiEndpoint, ...] = (),
) -> PageData:
    forms = (FormData(action="/submit", method="post", fields=fields),) if fields else ()
    return PageData(
        url=url,
        title=title,
        headings=("Heading",),
        links=links,
        forms=forms,
        screenshot_path="/tmp/screenshot.png",
        api_calls=api_calls,
    )
