"""状態遷移表（ISTQB 状態遷移テスト）の検証。

回帰の主対象は「共通ナビゲーションを除外して表が空になる」不具合。
画面数が少ないサイトで、割合を閾値にした除外が正当な遷移まで落としていた。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from graph.state_table import (
    INVALID_CELL,
    build_state_table,
    build_state_transition_report,
    invalid_transition_cases,
    one_switch_paths,
    zero_switch_paths,
)

# 全画面が相互にリンクし合う（共通ヘッダのある）小規模サイト。
# 旧実装ではこの形が「共通ナビ」と判定され、表がほぼ空になっていた。
SCREENS = [
    {
        "page_id": "P001",
        "title": "トップ",
        "url": "http://x/",
        "transitions": {"to": ["P002", "P003"]},
    },
    {
        "page_id": "P002",
        "title": "商品一覧",
        "url": "http://x/list",
        "transitions": {"to": ["P001", "P003"]},
        "forms": [{"method": "get", "action": "http://x/list"}],
    },
    {
        "page_id": "P003",
        "title": "お問い合わせ",
        "url": "http://x/contact",
        "transitions": {"to": ["P001", "P002", "P004"]},
        "forms": [{"method": "post", "action": "http://x/contact"}],
    },
    {"page_id": "P004", "title": "404", "url": "http://x/404", "transitions": {"to": []}},
]


def test_common_navigation_is_not_excluded() -> None:
    """共通ナビも遷移として表に載る（除外すると被覆が欠ける）。"""
    table = build_state_table(SCREENS)
    pairs = {(t.from_state, t.to_state) for t in table.transitions}
    assert ("P001", "P002") in pairs
    assert ("P002", "P001") in pairs
    assert ("P003", "P002") in pairs
    assert len(table.transitions) == 9  # リンク7 + フォーム2


def test_common_navigation_is_marked_not_dropped() -> None:
    """共通ナビは is_common で識別されるが、イベント一覧から消えない。"""
    table = build_state_table(SCREENS)
    common = [e.event_id for e in table.events if e.is_common]
    assert common, "共通ナビが 1 件も識別されていない"
    assert set(common) <= {e.event_id for e in table.events}


def test_form_submit_is_never_common() -> None:
    """フォーム送信は特定画面にしか存在しないため共通ナビにならない。"""
    table = build_state_table(SCREENS)
    for event in table.events:
        if event.kind == "フォーム送信":
            assert event.is_common is False


def test_matrix_has_state_times_event_cells() -> None:
    """行 × 列がすべて埋まる（無効遷移も欠測ではなくセルとして現れる）。"""
    table = build_state_table(SCREENS)
    matrix = table.matrix()
    assert len(matrix) == len(table.states)
    for row in matrix:
        assert len(row["cells"]) == len(table.events)


def test_invalid_transitions_are_enumerated() -> None:
    """定義されていない状態 × イベントが無効遷移として列挙される。"""
    table = build_state_table(SCREENS)
    total = len(table.states) * len(table.events)
    assert len(table.transitions) + len(table.invalid) == total
    assert table.cell("P001", "link:P004") == INVALID_CELL
    assert table.cell("P003", "link:P004") == "P004"


def test_initial_state_falls_back_to_entry_when_all_linked() -> None:
    """全画面が相互リンクでも初期状態を 1 つは決める（空にしない）。"""
    table = build_state_table(SCREENS)
    initial = [s.state_id for s in table.states if s.is_initial]
    assert initial == ["P001"]


def test_final_state_is_screen_without_exits() -> None:
    table = build_state_table(SCREENS)
    assert [s.state_id for s in table.states if s.is_final] == ["P004"]


def test_zero_switch_covers_every_valid_transition() -> None:
    table = build_state_table(SCREENS)
    paths = zero_switch_paths(table)
    assert len(paths) == len(table.transitions)


def test_one_switch_enumerates_consecutive_pairs() -> None:
    """1-switch は連続する 2 遷移の組を数える。"""
    table = build_state_table(SCREENS)
    paths, dropped = one_switch_paths(table)
    expected = sum(
        len([t for t in table.transitions if t.from_state == first.to_state])
        for first in table.transitions
    )
    assert len(paths) + dropped == expected
    for path in paths:
        assert len(path["steps"]) == 3


def test_invalid_transition_cases_match_invalid_cells() -> None:
    table = build_state_table(SCREENS)
    assert len(invalid_transition_cases(table)) == len(table.invalid)


def test_report_is_deterministic() -> None:
    assert build_state_transition_report(SCREENS) == build_state_transition_report(SCREENS)


def test_report_not_applicable_without_screens() -> None:
    result = build_state_transition_report([])
    assert result["applicable"] is False


def test_report_summary_counts_are_consistent() -> None:
    result = build_state_transition_report(SCREENS)
    summary = result["summary"]
    assert (
        summary["valid_transition_count"] + summary["invalid_transition_count"]
        == summary["cell_total"]
    )
    assert summary["initial_states"] == ["P001"]
    assert summary["final_states"] == ["P004"]


def test_single_screen_site_produces_no_false_transitions() -> None:
    """1 画面だけのサイトで遷移を捏造しない。"""
    result = build_state_transition_report(
        [{"page_id": "P001", "title": "単一", "url": "http://x/", "transitions": {"to": []}}]
    )
    assert result["applicable"] is True
    assert result["summary"]["valid_transition_count"] == 0
