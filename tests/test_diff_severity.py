"""差分の重要度スコアリングの契約。

守るべきは「決定的であること」と「重要度に必ず根拠が付くこと」。
"""

from __future__ import annotations

from crawler.page_crawler import FieldData
from diff.differ import (
    CHANGE_ADDED,
    CHANGE_REMOVED,
    SEVERITY_BREAKING,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    ApiChange,
    DiffResult,
    FieldAttributeDiff,
    FieldChange,
    LinkChange,
    PageChange,
    TitleChange,
)
from diff.impact_analyzer import ImpactedTest
from diff.severity import score_changes, summarize_change_text, summarize_severity


def _field(name: str = "q", required: bool = False) -> FieldData:
    return FieldData(field_type="text", name=name, placeholder="", required=required)


def _diff(**kwargs) -> DiffResult:
    base: dict = {
        "added_pages": (),
        "removed_pages": (),
        "field_changes": (),
        "link_changes": (),
        "title_changes": (),
        "has_changes": True,
        "attribute_diffs": (),
        "api_changes": (),
    }
    return DiffResult(**{**base, **kwargs})


def _by_label(scored: list[dict], label: str) -> dict:
    return next(item for item in scored if item["label"] == label)


# ─────────────────── 重要度の判定 ───────────────────


def test_removed_page_is_breaking_with_reason() -> None:
    diff = _diff(
        removed_pages=(PageChange(url="https://e.com/x", title="X", change_type=CHANGE_REMOVED),)
    )

    entry = score_changes(diff)[0]

    assert entry["severity"] == SEVERITY_BREAKING
    assert "到達できない" in entry["reason"]


def test_added_page_is_info() -> None:
    diff = _diff(
        added_pages=(PageChange(url="https://e.com/n", title="N", change_type=CHANGE_ADDED),)
    )

    assert score_changes(diff)[0]["severity"] == SEVERITY_INFO


def test_removed_field_is_breaking() -> None:
    diff = _diff(
        field_changes=(
            FieldChange(
                page_url="u",
                field_name="mail",
                change_type=CHANGE_REMOVED,
                before=_field("mail"),
                after=None,
            ),
        )
    )

    assert score_changes(diff)[0]["severity"] == SEVERITY_BREAKING


def test_added_optional_field_is_info_but_required_one_is_breaking() -> None:
    optional = FieldChange(
        page_url="u",
        field_name="nick",
        change_type=CHANGE_ADDED,
        before=None,
        after=_field("nick", required=False),
    )
    mandatory = FieldChange(
        page_url="u",
        field_name="tel",
        change_type=CHANGE_ADDED,
        before=None,
        after=_field("tel", required=True),
    )
    scored = score_changes(_diff(field_changes=(optional, mandatory)))

    assert _by_label(scored, "u / nick")["severity"] == SEVERITY_INFO
    assert _by_label(scored, "u / tel")["severity"] == SEVERITY_BREAKING


def test_newly_required_attribute_is_breaking() -> None:
    diff = _diff(
        attribute_diffs=(
            FieldAttributeDiff(
                page_url="u",
                field_name="tel",
                attribute="required",
                before="false",
                after="true",
                severity="info",
            ),
        )
    )

    entry = score_changes(diff)[0]

    assert entry["severity"] == SEVERITY_BREAKING
    assert "必須化" in entry["reason"]


def test_maxlength_change_is_warning() -> None:
    diff = _diff(
        attribute_diffs=(
            FieldAttributeDiff(
                page_url="u",
                field_name="memo",
                attribute="maxlength",
                before="100",
                after="50",
                severity="info",
            ),
        )
    )

    assert score_changes(diff)[0]["severity"] == SEVERITY_WARNING


def test_removed_link_is_warning_and_added_link_is_info() -> None:
    removed = LinkChange(page_url="u", link="/gone", change_type=CHANGE_REMOVED)
    added = LinkChange(page_url="u", link="/new", change_type=CHANGE_ADDED)
    scored = score_changes(_diff(link_changes=(removed, added)))

    assert _by_label(scored, "u → /gone")["severity"] == SEVERITY_WARNING
    assert _by_label(scored, "u → /new")["severity"] == SEVERITY_INFO


def test_title_only_change_is_info() -> None:
    diff = _diff(title_changes=(TitleChange(url="u", before="申込", after="申込（終了）"),))

    assert score_changes(diff)[0]["severity"] == SEVERITY_INFO


def test_removed_api_is_breaking() -> None:
    diff = _diff(
        api_changes=(
            ApiChange(page_url="u", method="POST", path="/api/order", change_type=CHANGE_REMOVED),
        )
    )

    assert score_changes(diff)[0]["severity"] == SEVERITY_BREAKING


# ─────────────────── 影響テストの反映 ───────────────────


def test_impacted_tests_escalate_severity_and_are_counted_in_reason() -> None:
    diff = _diff(title_changes=(TitleChange(url="https://e.com/a", before="A", after="B"),))
    impacted = [
        ImpactedTest(
            test_id="T1", reason="locator", page_url="https://e.com/a", severity="warning"
        ),
        ImpactedTest(
            test_id="T2", reason="locator", page_url="https://e.com/a", severity="warning"
        ),
    ]

    entry = score_changes(diff, impacted)[0]

    assert entry["severity"] == SEVERITY_BREAKING
    assert entry["impacted_test_count"] == 2
    assert "影響テスト 2 件" in entry["reason"]


# ─────────────────── 決定性・並び ───────────────────


def test_scoring_is_deterministic_for_identical_input() -> None:
    diff = _diff(
        removed_pages=(PageChange(url="https://e.com/x", title="X", change_type=CHANGE_REMOVED),),
        title_changes=(TitleChange(url="https://e.com/a", before="A", after="B"),),
        link_changes=(LinkChange(page_url="u", link="/gone", change_type=CHANGE_REMOVED),),
    )

    assert score_changes(diff) == score_changes(diff)


def test_breaking_entries_are_listed_before_info() -> None:
    diff = _diff(
        removed_pages=(PageChange(url="https://e.com/x", title="X", change_type=CHANGE_REMOVED),),
        title_changes=(TitleChange(url="https://e.com/a", before="A", after="B"),),
    )

    severities = [item["severity"] for item in score_changes(diff)]

    assert severities == [SEVERITY_BREAKING, SEVERITY_INFO]


def test_every_entry_carries_reason_and_claim_scope() -> None:
    diff = _diff(
        removed_pages=(PageChange(url="u", title="X", change_type=CHANGE_REMOVED),),
        title_changes=(TitleChange(url="u", before="A", after="B"),),
    )

    for entry in score_changes(diff):
        assert entry["reason"]
        assert entry["claim_scope"] == "rule_based_classification_only"


# ─────────────────── 集計・要約 ───────────────────


def test_severity_summary_counts_each_level() -> None:
    diff = _diff(
        removed_pages=(PageChange(url="u", title="X", change_type=CHANGE_REMOVED),),
        link_changes=(LinkChange(page_url="u", link="/g", change_type=CHANGE_REMOVED),),
        title_changes=(TitleChange(url="u", before="A", after="B"),),
    )

    assert summarize_severity(score_changes(diff)) == {"breaking": 1, "warning": 1, "info": 1}


def test_change_summary_text_is_built_from_counts() -> None:
    diff = _diff(
        removed_pages=(PageChange(url="u", title="X", change_type=CHANGE_REMOVED),),
        field_changes=(
            FieldChange(
                page_url="u",
                field_name="mail",
                change_type=CHANGE_REMOVED,
                before=_field("mail"),
                after=None,
            ),
        ),
        attribute_diffs=(
            FieldAttributeDiff(
                page_url="u",
                field_name="tel",
                attribute="required",
                before="false",
                after="true",
                severity="info",
            ),
        ),
    )

    assert summarize_change_text(diff) == "画面 1 件が削除、入力項目 1 件が削除、必須化 1 件。"


def test_change_summary_states_no_changes_explicitly() -> None:
    assert summarize_change_text(_diff(has_changes=False)) == "検出された変更はありません。"
