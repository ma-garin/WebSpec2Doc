from __future__ import annotations

from dataclasses import dataclass

from diff.impact_analyzer import (
    ImpactedTest,
    analyze_impact,
    format_impact_report,
)

# ─────────────────────── フィクスチャ用スタブ ───────────────────────


@dataclass(frozen=True)
class _FieldChange:
    page_url: str
    field_name: str
    change_type: str
    before: object = None
    after: object = None


@dataclass(frozen=True)
class _PageChange:
    url: str
    title: str
    change_type: str


@dataclass(frozen=True)
class _FieldAttributeDiff:
    page_url: str
    field_name: str
    attribute: str
    before: str
    after: str
    severity: str


@dataclass(frozen=True)
class _DiffResult:
    field_changes: tuple = ()
    added_pages: tuple = ()
    removed_pages: tuple = ()
    attribute_diffs: tuple = ()
    link_changes: tuple = ()
    title_changes: tuple = ()
    has_changes: bool = False


def _candidate(
    test_id: str = "TC001",
    title: str = "ログイン画面",
    steps: list[str] | None = None,
) -> dict:
    return {
        "id": test_id,
        "title": title,
        "steps": steps or ["page.goto('https://example.com/login')"],
    }


# ─────────────────────── テスト: analyze_impact ───────────────────────


class TestAnalyzeImpactFieldChanges:
    def test_detects_field_change_for_matching_url(self) -> None:
        fc = _FieldChange(
            page_url="https://example.com/login",
            field_name="email",
            change_type="modified",
        )
        diff = _DiffResult(field_changes=(fc,))
        candidates = [_candidate("TC001", steps=["page.goto('https://example.com/login')"])]

        results = analyze_impact(diff, candidates)

        assert len(results) == 1
        assert results[0].test_id == "TC001"
        assert "email" in results[0].reason
        assert results[0].page_url == "https://example.com/login"
        assert results[0].severity == "warning"

    def test_field_removed_gives_breaking_severity(self) -> None:
        fc = _FieldChange(
            page_url="https://example.com/form",
            field_name="password",
            change_type="removed",
        )
        diff = _DiffResult(field_changes=(fc,))
        candidates = [_candidate("TC002", steps=["page.goto('https://example.com/form')"])]

        results = analyze_impact(diff, candidates)

        assert results[0].severity == "breaking"

    def test_field_added_gives_info_severity(self) -> None:
        fc = _FieldChange(
            page_url="https://example.com/form",
            field_name="phone",
            change_type="added",
        )
        diff = _DiffResult(field_changes=(fc,))
        candidates = [_candidate("TC003", steps=["page.goto('https://example.com/form')"])]

        results = analyze_impact(diff, candidates)

        assert results[0].severity == "info"


class TestAnalyzeImpactEmptyWhenNoMatch:
    def test_empty_when_url_does_not_match(self) -> None:
        fc = _FieldChange(
            page_url="https://example.com/other",
            field_name="email",
            change_type="modified",
        )
        diff = _DiffResult(field_changes=(fc,))
        candidates = [_candidate("TC001", steps=["page.goto('https://example.com/login')"])]

        results = analyze_impact(diff, candidates)

        assert results == []

    def test_empty_when_no_diff(self) -> None:
        diff = _DiffResult()
        candidates = [_candidate("TC001")]

        results = analyze_impact(diff, candidates)

        assert results == []

    def test_empty_when_no_candidates(self) -> None:
        fc = _FieldChange(
            page_url="https://example.com/form",
            field_name="name",
            change_type="modified",
        )
        diff = _DiffResult(field_changes=(fc,))

        results = analyze_impact(diff, [])

        assert results == []


class TestAnalyzeImpactPageChanges:
    def test_added_page_gives_info_severity(self) -> None:
        page = _PageChange(
            url="https://example.com/new",
            title="新機能",
            change_type="added",
        )
        diff = _DiffResult(added_pages=(page,))

        results = analyze_impact(diff, [])

        assert len(results) == 1
        assert results[0].severity == "info"
        assert results[0].reason == "新規画面追加"
        assert results[0].page_url == "https://example.com/new"

    def test_removed_page_gives_breaking_severity(self) -> None:
        page = _PageChange(
            url="https://example.com/login",
            title="ログイン",
            change_type="removed",
        )
        diff = _DiffResult(removed_pages=(page,))
        candidates = [_candidate("TC001", steps=["page.goto('https://example.com/login')"])]

        results = analyze_impact(diff, candidates)

        assert len(results) == 1
        assert results[0].severity == "breaking"
        assert results[0].reason == "画面削除"
        assert results[0].test_id == "TC001"


class TestAnalyzeImpactAttributeDiffs:
    def test_breaking_attribute_diff_detected(self) -> None:
        ad = _FieldAttributeDiff(
            page_url="https://example.com/login",
            field_name="email",
            attribute="required",
            before="True",
            after="False",
            severity="breaking",
        )
        diff = _DiffResult(attribute_diffs=(ad,))
        candidates = [_candidate("TC001", steps=["page.goto('https://example.com/login')"])]

        results = analyze_impact(diff, candidates)

        assert any(r.severity == "breaking" for r in results)
        assert any("required" in r.reason for r in results)

    def test_warning_attribute_diff_not_included(self) -> None:
        ad = _FieldAttributeDiff(
            page_url="https://example.com/form",
            field_name="q",
            attribute="maxlength",
            before="100",
            after="200",
            severity="warning",
        )
        diff = _DiffResult(attribute_diffs=(ad,))
        candidates = [_candidate("TC001", steps=["page.goto('https://example.com/form')"])]

        # attribute_diffs からは breaking のみが追加される
        # field_changes なしなので field_changes 由来の impacts も 0
        results = analyze_impact(diff, candidates)
        attr_results = [r for r in results if "maxlength" in r.reason]

        assert attr_results == []


class TestAnalyzeImpactDeduplicate:
    def test_duplicate_impacts_are_deduplicated(self) -> None:
        fc = _FieldChange(
            page_url="https://example.com/form",
            field_name="email",
            change_type="modified",
        )
        diff = _DiffResult(field_changes=(fc, fc))  # 同じ変更が2回
        candidates = [_candidate("TC001", steps=["page.goto('https://example.com/form')"])]

        results = analyze_impact(diff, candidates)

        assert len(results) == 1


# ─────────────────────── テスト: format_impact_report ───────────────────────


class TestFormatImpactReport:
    def test_counts_correctly(self) -> None:
        impacted = [
            ImpactedTest("TC001", "画面削除", "https://example.com/a", "breaking"),
            ImpactedTest("TC002", "フィールド変更", "https://example.com/b", "warning"),
            ImpactedTest("TC003", "新規画面追加", "https://example.com/c", "info"),
            ImpactedTest("TC004", "フィールド削除", "https://example.com/d", "breaking"),
        ]

        report = format_impact_report(impacted)

        assert report["total"] == 4
        assert report["breaking"] == 2
        assert report["warning"] == 1
        assert report["info"] == 1

    def test_empty_list_gives_zeros(self) -> None:
        report = format_impact_report([])

        assert report["total"] == 0
        assert report["breaking"] == 0
        assert report["warning"] == 0
        assert report["info"] == 0
        assert report["tests"] == []

    def test_report_contains_test_details(self) -> None:
        impacted = [
            ImpactedTest(
                test_id="TC001",
                reason="フィールド 'email' が変化",
                page_url="https://example.com/login",
                severity="warning",
            )
        ]

        report = format_impact_report(impacted)

        assert len(report["tests"]) == 1
        test_entry = report["tests"][0]
        assert test_entry["test_id"] == "TC001"
        assert test_entry["reason"] == "フィールド 'email' が変化"
        assert test_entry["page_url"] == "https://example.com/login"
        assert test_entry["severity"] == "warning"

    def test_result_is_json_serializable(self) -> None:
        import json

        impacted = [
            ImpactedTest("TC001", "理由", "https://example.com/", "info"),
        ]

        report = format_impact_report(impacted)
        serialized = json.dumps(report)

        assert isinstance(serialized, str)
