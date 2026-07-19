"""メタモルフィック候補生成の契約。

守るべきは「実測要素に根拠を持つ関係だけを提案すること」と
「仕様がそれを保証すると断定しないこと」。
"""

from __future__ import annotations

from pathlib import Path

from mbt.metamorphic import (
    CLAIM_NOTICE,
    MR_FILTER_SUBSET,
    MR_PAGINATION_CONSISTENCY,
    MR_SORT_INVARIANCE,
    build_metamorphic_candidates,
    save_metamorphic_candidates,
)


def _screen(**kwargs) -> dict:
    return {"page_id": "P001", "url": "https://e.com/search", "forms": [], "links": [], **kwargs}


def _report(*screens: dict) -> dict:
    return {"screens": list(screens)}


def test_search_with_filter_suggests_subset_relation() -> None:
    screen = _screen(
        forms=[
            {
                "fields": [
                    {"name": "keyword", "field_type": "search", "options": []},
                    {"name": "category", "field_type": "select", "options": ["a", "b"]},
                ]
            }
        ]
    )

    result = build_metamorphic_candidates(_report(screen))

    subset = [c for c in result["candidates"] if c["mr_type"] == MR_FILTER_SUBSET]
    assert len(subset) == 1
    assert subset[0]["evidence"]["filter_fields"] == ["category"]


def test_sort_select_suggests_sort_invariance() -> None:
    screen = _screen(
        forms=[
            {"fields": [{"name": "sort_order", "field_type": "select", "options": ["new", "old"]}]}
        ]
    )

    result = build_metamorphic_candidates(_report(screen))

    assert [c["mr_type"] for c in result["candidates"]] == [MR_SORT_INVARIANCE]


def test_pagination_links_suggest_consistency_check() -> None:
    screen = _screen(links=["/items?page=2", "/items?page=3"])

    result = build_metamorphic_candidates(_report(screen))

    assert [c["mr_type"] for c in result["candidates"]] == [MR_PAGINATION_CONSISTENCY]


def test_plain_screen_yields_no_candidates() -> None:
    """根拠となる実測要素が無ければ何も提案しない（発明しない）。"""
    result = build_metamorphic_candidates(_report(_screen()))

    assert result["candidates"] == []
    assert result["summary"]["total"] == 0


def test_sort_field_is_not_double_counted_as_filter() -> None:
    screen = _screen(
        forms=[
            {
                "fields": [
                    {"name": "q", "field_type": "text", "options": []},
                    {"name": "sort", "field_type": "select", "options": ["asc", "desc"]},
                ]
            }
        ]
    )

    result = build_metamorphic_candidates(_report(screen))

    types = [c["mr_type"] for c in result["candidates"]]
    assert MR_FILTER_SUBSET not in types  # sortはフィルタとして数えない
    assert MR_SORT_INVARIANCE in types


def test_every_candidate_has_id_procedure_and_claim_scope() -> None:
    screen = _screen(
        links=["/x?page=2"],
        forms=[{"fields": [{"name": "order", "field_type": "select", "options": ["a", "b"]}]}],
    )

    result = build_metamorphic_candidates(_report(screen))

    assert result["meta"]["claim_notice"] == CLAIM_NOTICE
    for candidate in result["candidates"]:
        assert candidate["mr_id"].startswith("MR-")
        assert candidate["procedure"]
        assert candidate["claim_scope"] == "relation_candidates_from_measured_elements"


def test_save_writes_json(tmp_path: Path) -> None:
    payload = build_metamorphic_candidates(_report(_screen(links=["/p?page=2"])))

    paths = save_metamorphic_candidates(payload, tmp_path)

    assert paths["metamorphic_checks_json"].is_file()
