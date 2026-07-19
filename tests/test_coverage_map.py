"""画面カバレッジマップの契約。

守るべきは「踏んだ＝検証した、と読ませないこと」。割合を品質指標として
掲げず、未踏領域を探す道具に留める。
"""

from __future__ import annotations

from pathlib import Path

from apispec.coverage_map import (
    CLAIM_NOTICE,
    STATUS_COVERED,
    STATUS_UNTOUCHED,
    build_coverage_map,
    executed_pages_from_meta,
    render_html,
    save_coverage_map,
)


def _graph() -> dict:
    return {
        "nodes": [
            {"id": "P001", "title": "トップ", "url": "https://e.com/"},
            {"id": "P002", "title": "検索", "url": "https://e.com/search"},
            {"id": "P003", "title": "設定", "url": "https://e.com/settings"},
        ],
        "edges": [
            {"from": "P001", "to": "P002"},
            {"from": "P002", "to": "P003"},
        ],
    }


# ─────────────────── 重ね合わせ ───────────────────


def test_touched_screens_are_marked_covered() -> None:
    coverage = build_coverage_map(_graph(), {"P001", "P002"})

    statuses = {node["id"]: node["status"] for node in coverage["nodes"]}
    assert statuses == {
        "P001": STATUS_COVERED,
        "P002": STATUS_COVERED,
        "P003": STATUS_UNTOUCHED,
    }


def test_untouched_screens_are_listed_for_follow_up() -> None:
    coverage = build_coverage_map(_graph(), {"P001"})

    assert coverage["summary"]["untouched_screens"] == ["P002", "P003"]


def test_transitions_are_marked_only_when_actually_traversed() -> None:
    coverage = build_coverage_map(_graph(), {"P001", "P002"}, [("P001", "P002")])

    statuses = {(e["from"], e["to"]): e["status"] for e in coverage["edges"]}
    assert statuses[("P001", "P002")] == STATUS_COVERED
    assert statuses[("P002", "P003")] == STATUS_UNTOUCHED


def test_counts_are_reported_as_fractions_not_percentages() -> None:
    """割合（%）を出さないことが主張境界の担保になる。"""
    summary = build_coverage_map(_graph(), {"P001"})["summary"]

    assert summary["traversed_screens"] == 1
    assert summary["total_screens"] == 3
    assert not any("rate" in key or "percent" in key for key in summary)


def test_claim_scope_is_declared() -> None:
    coverage = build_coverage_map(_graph(), set())

    assert coverage["meta"]["claim_scope"] == "traversed_range_only"
    assert coverage["meta"]["claim_notice"] == CLAIM_NOTICE


def test_empty_graph_does_not_raise() -> None:
    coverage = build_coverage_map({"nodes": [], "edges": []}, set())

    assert coverage["summary"]["total_screens"] == 0
    assert coverage["summary"]["untouched_screens"] == []


# ─────────────────── 実行結果からの抽出 ───────────────────


def _meta() -> dict:
    return {
        "tests": [
            {"test_id": "PW-0001", "page_id": "P001"},
            {"test_id": "PW-0002", "page_id": "P002"},
            {"test_id": "PW-0003", "page_id": "P003"},
        ]
    }


def test_all_generated_tests_count_when_no_report_supplied() -> None:
    assert executed_pages_from_meta(_meta()) == {"P001", "P002", "P003"}


def test_skipped_tests_do_not_count_as_traversed() -> None:
    report = {
        "tests": [
            {"title": "PW-0001 表示", "status": "passed"},
            {"title": "PW-0002 遷移", "status": "failed"},
            {"title": "PW-0003 設定", "status": "skipped"},
        ]
    }

    assert executed_pages_from_meta(_meta(), report) == {"P001", "P002"}


def test_failed_tests_still_count_as_traversed() -> None:
    """失敗しても画面には到達しているため、踏んだ範囲には含める。"""
    report = {"tests": [{"title": "PW-0002 遷移", "status": "failed"}]}

    assert executed_pages_from_meta(_meta(), report) == {"P002"}


# ─────────────────── 出力 ───────────────────


def test_html_states_that_traversal_is_not_verification() -> None:
    document = render_html(build_coverage_map(_graph(), {"P001"}))

    assert "踏んだことは検証したことを意味しない" in document
    assert "<script" not in document


def test_html_highlights_untouched_screens() -> None:
    document = render_html(build_coverage_map(_graph(), {"P001"}))

    assert "未踏の画面: P002, P003" in document


def test_save_writes_json_and_html(tmp_path: Path) -> None:
    paths = save_coverage_map(build_coverage_map(_graph(), {"P001"}), tmp_path)

    assert paths["coverage_map_json"].is_file()
    assert paths["coverage_map_html"].is_file()
