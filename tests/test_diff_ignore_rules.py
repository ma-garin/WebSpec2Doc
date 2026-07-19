"""無視ルール（誤検知フィルタ）の契約。

重要なのは「除外が黙って消えないこと」と「入力を書き換えないこと」。
"""

from __future__ import annotations

import json
from pathlib import Path

from crawler.page_crawler import FieldData
from diff.differ import (
    CHANGE_ADDED,
    CHANGE_MODIFIED,
    CHANGE_REMOVED,
    DiffResult,
    FieldAttributeDiff,
    FieldChange,
    LinkChange,
    PageChange,
    TitleChange,
)
from diff.ignore_rules import (
    IgnoreRule,
    apply_ignore_rules,
    load_ignore_rules,
    summarize_exclusions,
)


def _field(name: str = "q", element_id: str = "") -> FieldData:
    return FieldData(
        field_type="text",
        name=name,
        placeholder="",
        required=False,
        element_id=element_id,
    )


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


# ─────────────────── 読み込み ───────────────────


def test_missing_file_yields_no_rules(tmp_path: Path) -> None:
    assert load_ignore_rules(tmp_path / "absent.json") == []


def test_broken_json_is_tolerated_as_no_rules(tmp_path: Path) -> None:
    path = tmp_path / "diff_ignore.json"
    path.write_text("{ not json", encoding="utf-8")

    assert load_ignore_rules(path) == []


def test_invalid_entries_are_skipped_but_valid_ones_survive(tmp_path: Path) -> None:
    path = tmp_path / "diff_ignore.json"
    path.write_text(
        json.dumps(
            {
                "rules": [
                    {"kind": "unknown", "pattern": "x"},
                    {"kind": "regex", "pattern": "("},
                    {"kind": "field", "pattern": ""},
                    {"kind": "field", "pattern": "csrf_token", "note": "トークン"},
                ]
            }
        ),
        encoding="utf-8",
    )

    rules = load_ignore_rules(path)

    assert rules == [IgnoreRule(kind="field", pattern="csrf_token", note="トークン")]


# ─────────────────── 適用 ───────────────────


def test_no_rules_returns_input_untouched() -> None:
    diff = _diff(title_changes=(TitleChange(url="u", before="a", after="b"),))

    filtered, excluded = apply_ignore_rules(diff, [])

    assert filtered is diff
    assert excluded == []


def test_regex_rule_excludes_dynamic_date_but_keeps_real_change() -> None:
    dynamic = TitleChange(url="https://e.com/", before="2026/07/18", after="2026/07/19")
    real = TitleChange(url="https://e.com/a", before="申込", after="申込（終了）")
    diff = _diff(title_changes=(dynamic, real))

    filtered, excluded = apply_ignore_rules(
        diff, [IgnoreRule(kind="regex", pattern=r"^\d{4}/\d{2}/\d{2}$", note="日付")]
    )

    assert filtered.title_changes == (real,)
    assert [item["rule_note"] for item in excluded] == ["日付"]


def test_field_rule_matches_exactly_not_by_substring() -> None:
    token = FieldChange(
        page_url="u",
        field_name="csrf_token",
        change_type=CHANGE_MODIFIED,
        before=_field("csrf_token"),
        after=_field("csrf_token"),
    )
    similar = FieldChange(
        page_url="u",
        field_name="csrf_token_backup",
        change_type=CHANGE_MODIFIED,
        before=_field("csrf_token_backup"),
        after=_field("csrf_token_backup"),
    )
    diff = _diff(field_changes=(token, similar))

    filtered, excluded = apply_ignore_rules(diff, [IgnoreRule(kind="field", pattern="csrf_token")])

    assert filtered.field_changes == (similar,)
    assert len(excluded) == 1


def test_selector_rule_accepts_hash_prefix_and_matches_element_id() -> None:
    counter = FieldChange(
        page_url="u",
        field_name="count",
        change_type=CHANGE_MODIFIED,
        before=_field("count", element_id="visitor-counter"),
        after=_field("count", element_id="visitor-counter"),
    )
    diff = _diff(field_changes=(counter,))

    filtered, excluded = apply_ignore_rules(
        diff, [IgnoreRule(kind="selector", pattern="#visitor-counter")]
    )

    assert filtered.field_changes == ()
    assert excluded[0]["rule_kind"] == "selector"


def test_url_rule_excludes_every_change_on_matching_page() -> None:
    diff = _diff(
        added_pages=(PageChange(url="https://e.com/tmp/1", title="t", change_type=CHANGE_ADDED),),
        link_changes=(
            LinkChange(page_url="https://e.com/keep", link="/x", change_type=CHANGE_ADDED),
        ),
    )

    filtered, excluded = apply_ignore_rules(diff, [IgnoreRule(kind="url", pattern=r"/tmp/")])

    assert filtered.added_pages == ()
    assert len(filtered.link_changes) == 1
    assert len(excluded) == 1


def test_excluded_changes_are_recorded_not_discarded() -> None:
    diff = _diff(
        removed_pages=(PageChange(url="https://e.com/x", title="X", change_type=CHANGE_REMOVED),)
    )

    _filtered, excluded = apply_ignore_rules(
        diff, [IgnoreRule(kind="url", pattern="x$", note="一時")]
    )

    assert excluded == [
        {
            "category": "removed_page",
            "label": "https://e.com/x",
            "url": "https://e.com/x",
            "rule_kind": "url",
            "rule_pattern": "x$",
            "rule_note": "一時",
        }
    ]


def test_input_diff_result_is_not_mutated() -> None:
    original = TitleChange(url="u", before="2026/07/18", after="2026/07/19")
    diff = _diff(title_changes=(original,))

    apply_ignore_rules(diff, [IgnoreRule(kind="regex", pattern=r"\d{4}/")])

    assert diff.title_changes == (original,)
    assert diff.has_changes is True


def test_has_changes_becomes_false_when_everything_is_excluded() -> None:
    diff = _diff(title_changes=(TitleChange(url="u", before="2026/07/18", after="2026/07/19"),))

    filtered, _excluded = apply_ignore_rules(diff, [IgnoreRule(kind="regex", pattern=r"\d{4}/")])

    assert filtered.has_changes is False


def test_attribute_diffs_can_be_excluded_by_field_name() -> None:
    diff = _diff(
        attribute_diffs=(
            FieldAttributeDiff(
                page_url="u",
                field_name="token",
                attribute="default",
                before="a",
                after="b",
                severity="info",
            ),
        )
    )

    filtered, excluded = apply_ignore_rules(diff, [IgnoreRule(kind="field", pattern="token")])

    assert filtered.attribute_diffs == ()
    assert excluded[0]["category"] == "attribute_diff"


# ─────────────────── 集計 ───────────────────


def test_summary_groups_by_rule_and_orders_by_count() -> None:
    excluded = [
        {"rule_kind": "regex", "rule_pattern": r"\d{4}", "rule_note": "日付"},
        {"rule_kind": "regex", "rule_pattern": r"\d{4}", "rule_note": "日付"},
        {"rule_kind": "field", "rule_pattern": "token", "rule_note": ""},
    ]

    assert summarize_exclusions(excluded) == [
        {"rule_kind": "regex", "rule_pattern": r"\d{4}", "rule_note": "日付", "count": 2},
        {"rule_kind": "field", "rule_pattern": "token", "rule_note": "", "count": 1},
    ]
