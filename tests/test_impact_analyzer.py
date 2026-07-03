"""impact_analyzer（メタデータ JSON 照合版）のユニット・受け入れテスト。"""

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


def _metadata(
    test_id: str = "PW-0001",
    page_id: str = "P001",
    fingerprint: str = "fp-login",
    url: str = "https://example.com/login",
    title: str = "ログイン画面",
) -> dict:
    return {
        "test_id": test_id,
        "title": title,
        "trace_id": page_id,
        "page_id": page_id,
        "fingerprint": fingerprint,
        "url": url,
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
        metadata = [_metadata("PW-0001")]

        results = analyze_impact(diff, metadata)

        assert len(results) == 1
        assert results[0].test_id == "PW-0001"
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
        metadata = [_metadata("PW-0002", url="https://example.com/form")]

        results = analyze_impact(diff, metadata)

        assert results[0].severity == "breaking"

    def test_field_added_gives_info_severity(self) -> None:
        fc = _FieldChange(
            page_url="https://example.com/form",
            field_name="phone",
            change_type="added",
        )
        diff = _DiffResult(field_changes=(fc,))
        metadata = [_metadata("PW-0003", url="https://example.com/form")]

        results = analyze_impact(diff, metadata)

        assert results[0].severity == "info"


class TestFingerprintMatching:
    """受け入れ条件: URL 文字列を変更しても fingerprint 一致で影響テストが特定される。"""

    def test_url_changed_but_fingerprint_matches(self) -> None:
        # テスト生成時の URL は /login、その後 /signin にリネームされたが
        # 画面構造（fingerprint）は同一というシナリオ
        fc = _FieldChange(
            page_url="https://example.com/signin",
            field_name="email",
            change_type="modified",
        )
        diff = _DiffResult(field_changes=(fc,))
        metadata = [_metadata("PW-0001", fingerprint="fp-login", url="https://example.com/login")]
        url_fingerprints = {"https://example.com/signin": "fp-login"}

        results = analyze_impact(diff, metadata, url_fingerprints)

        assert len(results) == 1
        assert results[0].test_id == "PW-0001"

    def test_fingerprint_mismatch_falls_back_to_url(self) -> None:
        fc = _FieldChange(
            page_url="https://example.com/login",
            field_name="email",
            change_type="modified",
        )
        diff = _DiffResult(field_changes=(fc,))
        metadata = [_metadata("PW-0001", fingerprint="fp-other", url="https://example.com/login")]
        url_fingerprints = {"https://example.com/login": "fp-login"}

        results = analyze_impact(diff, metadata, url_fingerprints)

        # fingerprint は不一致だが URL 完全一致でフォールバックする
        assert len(results) == 1
        assert results[0].test_id == "PW-0001"

    def test_no_match_when_neither_fingerprint_nor_url(self) -> None:
        fc = _FieldChange(
            page_url="https://example.com/other",
            field_name="email",
            change_type="modified",
        )
        diff = _DiffResult(field_changes=(fc,))
        metadata = [_metadata("PW-0001")]

        assert analyze_impact(diff, metadata, {}) == []


class TestAnalyzeImpactEmptyWhenNoMatch:
    def test_empty_when_url_does_not_match(self) -> None:
        fc = _FieldChange(
            page_url="https://example.com/other",
            field_name="email",
            change_type="modified",
        )
        diff = _DiffResult(field_changes=(fc,))
        metadata = [_metadata("PW-0001")]

        assert analyze_impact(diff, metadata) == []

    def test_empty_when_no_diff(self) -> None:
        assert analyze_impact(_DiffResult(), [_metadata()]) == []

    def test_empty_when_no_metadata(self) -> None:
        fc = _FieldChange(
            page_url="https://example.com/form",
            field_name="name",
            change_type="modified",
        )
        diff = _DiffResult(field_changes=(fc,))

        assert analyze_impact(diff, []) == []


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
        metadata = [_metadata("PW-0001")]

        results = analyze_impact(diff, metadata)

        assert len(results) == 1
        assert results[0].severity == "breaking"
        assert results[0].reason == "画面削除"
        assert results[0].test_id == "PW-0001"


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
        metadata = [_metadata("PW-0001")]

        results = analyze_impact(diff, metadata)

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
        metadata = [_metadata("PW-0001", url="https://example.com/form")]

        # attribute_diffs からは breaking のみが追加される
        results = analyze_impact(diff, metadata)
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
        metadata = [_metadata("PW-0001", url="https://example.com/form")]

        results = analyze_impact(diff, metadata)

        assert len(results) == 1


# ─────────────────────── 受け入れ条件: 正規表現照合コードの削除 ───────────────────────


class TestRegexMatchingRemoved:
    def test_page_goto_regex_matching_is_removed(self) -> None:
        """impact_analyzer から page.goto 正規表現照合コードが削除されていること。"""
        import inspect

        import diff.impact_analyzer as module

        source = inspect.getsource(module)
        assert "page\\.goto" not in source
        assert "_URL_PATTERN" not in source
        assert "re.compile" not in source


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

    def test_rerun_recommended_includes_breaking_and_warning(self) -> None:
        impacted = [
            ImpactedTest("TC001", "画面削除", "https://example.com/a", "breaking"),
            ImpactedTest("TC002", "フィールド変更", "https://example.com/b", "warning"),
            ImpactedTest("TC003", "新規画面追加", "https://example.com/c", "info"),
            ImpactedTest("", "画面削除", "https://example.com/d", "breaking"),
        ]

        report = format_impact_report(impacted)

        assert report["rerun_recommended"] == ["TC001", "TC002"]

    def test_empty_list_gives_zeros(self) -> None:
        report = format_impact_report([])

        assert report["total"] == 0
        assert report["breaking"] == 0
        assert report["warning"] == 0
        assert report["info"] == 0
        assert report["tests"] == []
        assert report["rerun_recommended"] == []

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
