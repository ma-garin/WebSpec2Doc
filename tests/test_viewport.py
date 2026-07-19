"""マルチビューポート観測の契約。

守るべきは「片方に無いことを不具合と断定しないこと」と、
基準→対象の向き（hidden か viewport_only か）を取り違えないこと。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from crawler.page_crawler import FieldData, FormData, PageData
from viewport.comparison import CLAIM_NOTICE, compare_viewports, has_differences
from viewport.profiles import DESKTOP, MOBILE, PROFILES, get_profile, resolve_profiles
from viewport.reporter import render_html, render_markdown, save_viewport_report


def _field(name: str) -> FieldData:
    return FieldData(field_type="text", name=name, placeholder="", required=False)


def _page(url: str, title: str = "T", links=(), fields=()) -> PageData:
    forms = (FormData(action="", method="get", fields=tuple(fields)),) if fields else ()
    return PageData(
        url=url,
        title=title,
        headings=(),
        links=tuple(links),
        forms=forms,
        screenshot_path="",
    )


# ─────────────────── プロファイル ───────────────────


def test_default_profiles_cover_pc_tablet_and_mobile() -> None:
    names = [profile.name for profile in resolve_profiles(None)]

    assert names == ["desktop", "tablet", "mobile"]


def test_mobile_profile_declares_touch_and_mobile_user_agent() -> None:
    mobile = get_profile(MOBILE)

    assert mobile.is_mobile is True
    assert "iPhone" in mobile.user_agent
    assert mobile.width < PROFILES[DESKTOP].width


def test_unknown_viewport_is_rejected_with_available_names() -> None:
    with pytest.raises(ValueError, match="未知のビューポート"):
        get_profile("watch")


def test_duplicate_selection_is_collapsed_preserving_order() -> None:
    names = [profile.name for profile in resolve_profiles(["mobile", "desktop", "mobile"])]

    assert names == ["mobile", "desktop"]


def test_profile_size_is_playwright_shaped() -> None:
    assert get_profile(DESKTOP).size == {"width": 1366, "height": 768}


# ─────────────────── 比較 ───────────────────


def test_page_missing_on_mobile_is_reported_as_hidden() -> None:
    observations = {
        "desktop": [_page("https://e.com/"), _page("https://e.com/help")],
        "mobile": [_page("https://e.com/")],
    }

    report = compare_viewports(observations, baseline="desktop")
    mobile = report["comparisons"][0]

    assert [item["url"] for item in mobile["hidden_pages"]] == ["https://e.com/help"]
    assert mobile["viewport_only_pages"] == []


def test_page_only_on_mobile_is_reported_as_viewport_only() -> None:
    observations = {
        "desktop": [_page("https://e.com/")],
        "mobile": [_page("https://e.com/"), _page("https://e.com/app-banner")],
    }

    mobile = compare_viewports(observations, baseline="desktop")["comparisons"][0]

    assert [item["url"] for item in mobile["viewport_only_pages"]] == ["https://e.com/app-banner"]
    assert mobile["hidden_pages"] == []


def test_field_hidden_on_mobile_is_detected() -> None:
    observations = {
        "desktop": [_page("https://e.com/", fields=[_field("keyword"), _field("area")])],
        "mobile": [_page("https://e.com/", fields=[_field("keyword")])],
    }

    mobile = compare_viewports(observations, baseline="desktop")["comparisons"][0]

    assert [item["field_name"] for item in mobile["hidden_fields"]] == ["area"]


def test_mobile_only_transition_is_detected() -> None:
    observations = {
        "desktop": [_page("https://e.com/", links=["/a"])],
        "mobile": [_page("https://e.com/", links=["/a", "/tel-call"])],
    }

    mobile = compare_viewports(observations, baseline="desktop")["comparisons"][0]

    assert [item["link"] for item in mobile["viewport_only_links"]] == ["/tel-call"]


def test_baseline_is_not_compared_against_itself() -> None:
    observations = {"desktop": [_page("https://e.com/")], "mobile": [_page("https://e.com/")]}

    report = compare_viewports(observations, baseline="desktop")

    assert [c["viewport"] for c in report["comparisons"]] == ["mobile"]


def test_missing_baseline_observation_is_rejected() -> None:
    with pytest.raises(ValueError, match="基準ビューポート"):
        compare_viewports({"mobile": [_page("https://e.com/")]}, baseline="desktop")


def test_summary_totals_across_viewports() -> None:
    observations = {
        "desktop": [_page("https://e.com/"), _page("https://e.com/help")],
        "tablet": [_page("https://e.com/")],
        "mobile": [_page("https://e.com/")],
    }

    report = compare_viewports(observations, baseline="desktop")

    assert report["summary"]["hidden_pages"] == 2
    assert has_differences(report) is True


def test_identical_observations_report_no_differences() -> None:
    page = _page("https://e.com/", fields=[_field("q")], links=["/a"])
    report = compare_viewports({"desktop": [page], "mobile": [page]}, baseline="desktop")

    assert has_differences(report) is False


def test_claim_scope_is_declared() -> None:
    report = compare_viewports({"desktop": [], "mobile": []}, baseline="desktop")

    assert report["meta"]["claim_scope"] == "observed_viewports_only"
    assert report["meta"]["claim_notice"] == CLAIM_NOTICE


# ─────────────────── 文書化 ───────────────────


def test_markdown_leads_with_claim_notice_and_uses_human_labels() -> None:
    observations = {
        "desktop": [_page("https://e.com/"), _page("https://e.com/help")],
        "mobile": [_page("https://e.com/")],
    }

    markdown = render_markdown(compare_viewports(observations, baseline="desktop"))

    assert CLAIM_NOTICE in markdown
    assert "スマートフォン（390×844）" in markdown
    assert "https://e.com/help" in markdown


def test_html_is_self_contained() -> None:
    document = render_html(
        compare_viewports({"desktop": [_page("https://e.com/")], "mobile": []}, baseline="desktop")
    )

    assert "<script" not in document
    assert "https://cdn" not in document


def test_save_writes_all_three_formats(tmp_path: Path) -> None:
    report = compare_viewports({"desktop": [_page("https://e.com/")], "mobile": []}, "desktop")

    paths = save_viewport_report(report, tmp_path)

    assert paths["viewport_report_md"].is_file()
    assert paths["viewport_report_html"].is_file()
    assert paths["viewport_report_json"].is_file()


# ─────────────────── オーケストレーション ───────────────────


def test_runner_crawls_each_viewport_and_writes_report(tmp_path: Path) -> None:
    from viewport.runner import run_multi_viewport

    seen: list[str] = []

    def fake_crawl(url, *, depth, max_pages, output_dir, auth_state, viewport):
        seen.append(viewport.name)
        pages = [_page("https://e.com/")]
        if viewport.name == "desktop":
            pages.append(_page("https://e.com/help"))
        return pages

    report = run_multi_viewport(
        "https://e.com/", tmp_path, viewports=["desktop", "mobile"], crawl_fn=fake_crawl
    )

    assert seen == ["desktop", "mobile"]
    assert report["summary"]["hidden_pages"] == 1
    assert Path(report["outputs"]["viewport_report_md"]).is_file()


def test_runner_records_failed_viewport_instead_of_hiding_it(tmp_path: Path) -> None:
    from viewport.runner import run_multi_viewport

    def flaky_crawl(url, *, depth, max_pages, output_dir, auth_state, viewport):
        if viewport.name == "mobile":
            raise RuntimeError("ブラウザ起動失敗")
        return [_page("https://e.com/")]

    report = run_multi_viewport(
        "https://e.com/", tmp_path, viewports=["desktop", "mobile"], crawl_fn=flaky_crawl
    )

    assert "mobile" in report["meta"]["failed_viewports"]
    assert "ブラウザ起動失敗" in report["meta"]["failed_viewports"]["mobile"]


def test_runner_fails_loudly_when_baseline_cannot_be_observed(tmp_path: Path) -> None:
    from viewport.runner import run_multi_viewport

    def broken_baseline(url, *, depth, max_pages, output_dir, auth_state, viewport):
        if viewport.name == "desktop":
            raise RuntimeError("起動失敗")
        return [_page("https://e.com/")]

    with pytest.raises(RuntimeError, match="基準ビューポート"):
        run_multi_viewport(
            "https://e.com/", tmp_path, viewports=["desktop", "mobile"], crawl_fn=broken_baseline
        )


def test_runner_rejects_baseline_outside_selected_viewports(tmp_path: Path) -> None:
    from viewport.runner import run_multi_viewport

    with pytest.raises(ValueError, match="観測対象に含まれていません"):
        run_multi_viewport(
            "https://e.com/",
            tmp_path,
            viewports=["mobile"],
            baseline="desktop",
            crawl_fn=lambda *a, **k: [],
        )
