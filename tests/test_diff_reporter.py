from __future__ import annotations

from crawler.page_crawler import ApiEndpoint, FieldData, FormData, PageData
from diff.differ import compute_diff
from generator.diff_reporter import generate_diff_report


def _page(
    url: str,
    title: str,
    fields: tuple[FieldData, ...] = (),
    api_calls: tuple[ApiEndpoint, ...] = (),
) -> PageData:
    forms = (FormData(action="/submit", method="post", fields=fields),) if fields else ()
    return PageData(
        url=url,
        title=title,
        headings=("Heading",),
        links=(),
        forms=forms,
        screenshot_path="/tmp/screenshot.png",
        api_calls=api_calls,
    )


def _diff_with_attribute_and_api_changes():
    """属性レベル変更（breaking+warning）と API追加を含む差分を生成する。"""
    url = "https://example.com/form"
    before_field = FieldData("text", "email", "", required=True, maxlength=255, pattern="")
    after_field = FieldData("text", "email", "", required=False, maxlength=50, pattern="")
    old = [_page(url, "Form", fields=(before_field,))]
    new = [
        _page(
            url,
            "Form",
            fields=(after_field,),
            api_calls=(ApiEndpoint("POST", "/api/reserve", 200, "application/json", ()),),
        )
    ]
    return compute_diff(old, new)


def test_diff_report_renders_attribute_section() -> None:
    diff = _diff_with_attribute_and_api_changes()
    assert diff.attribute_diffs, "前提: attribute_diffs が計算されていること"

    report = generate_diff_report(diff, "old", "new", "https://example.com/")

    assert "属性レベル変更" in report
    assert "email" in report
    # required の breaking 変更が表に出ること
    assert "required" in report


def test_diff_report_renders_api_section() -> None:
    diff = _diff_with_attribute_and_api_changes()
    assert diff.api_changes, "前提: api_changes が計算されていること"

    report = generate_diff_report(diff, "old", "new", "https://example.com/")

    assert "API変更" in report
    assert "/api/reserve" in report


def test_diff_report_shows_severity_badges() -> None:
    diff = _diff_with_attribute_and_api_changes()
    report = generate_diff_report(diff, "old", "new", "https://example.com/")

    # severity のラベルとクラスが出力されること
    assert "重大" in report  # breaking の日本語ラベル
    assert "sev-breaking" in report


def test_diff_report_breaking_count_card() -> None:
    diff = _diff_with_attribute_and_api_changes()
    breaking_count = sum(1 for ad in diff.attribute_diffs if ad.severity == "breaking")
    assert breaking_count >= 1

    report = generate_diff_report(diff, "old", "new", "https://example.com/")

    assert "重大な変更" in report


def test_diff_report_empty_attribute_and_api_sections() -> None:
    """属性変更・API変更がない場合でもセクションは空表示で壊れない（後方互換）。"""
    old = [_page("https://example.com/", "Top")]
    new = [_page("https://example.com/", "Top")]

    report = generate_diff_report(compute_diff(old, new), "old", "new", "https://example.com/")

    assert "属性レベル変更" in report
    assert "API変更" in report
    assert "変更は検出されませんでした" in report
