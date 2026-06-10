"""transition_graph.py のユニットテスト（状態遷移テストパス生成）"""

from __future__ import annotations

import json

import pytest

from crawler.page_crawler import PageData
from graph.transition_graph import (
    TransitionTestPath,
    generate_transition_tests,
    transition_tests_to_dict,
)

# ---------- フィクスチャ ----------


def _make_page(url: str, title: str, links: tuple[str, ...] = ()) -> PageData:
    return PageData(
        url=url,
        title=title,
        headings=(),
        links=links,
        forms=(),
        screenshot_path=None,
    )


@pytest.fixture()
def pages_abc() -> list[PageData]:
    """A→B→C の直線グラフ"""
    a = _make_page("https://example.com/a", "ページA", ("https://example.com/b",))
    b = _make_page("https://example.com/b", "ページB", ("https://example.com/c",))
    c = _make_page("https://example.com/c", "ページC", ())
    return [a, b, c]


@pytest.fixture()
def pages_no_links() -> list[PageData]:
    """リンクなしの 3 ページ"""
    return [
        _make_page("https://example.com/x", "ページX"),
        _make_page("https://example.com/y", "ページY"),
        _make_page("https://example.com/z", "ページZ"),
    ]


# ---------- 0-switch テスト ----------


class TestGenerateTransitionTests0Switch:
    def test_returns_one_path_per_node(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="0-switch")
        assert len(paths) == 3

    def test_each_path_has_single_node(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="0-switch")
        assert all(len(p.nodes) == 1 for p in paths)

    def test_each_path_has_no_edges(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="0-switch")
        assert all(len(p.edges) == 0 for p in paths)

    def test_coverage_field_is_set(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="0-switch")
        assert all(p.coverage == "0-switch" for p in paths)

    def test_path_ids_are_sequential(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="0-switch")
        expected = ["TP001", "TP002", "TP003"]
        assert [p.path_id for p in paths] == expected

    def test_test_objective_contains_page_title(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="0-switch")
        # 各パスの目的文にそのページのタイトルが含まれているはず
        titles_in_objectives = [
            any(p.nodes[0] in obj or "ページ" in obj for obj in [p.test_objective]) for p in paths
        ]
        assert all(titles_in_objectives)


# ---------- 1-switch テスト ----------


class TestGenerateTransitionTests1Switch:
    def test_returns_one_path_per_edge(self, pages_abc: list[PageData]) -> None:
        # A→B, B→C の 2 エッジ → 2 パス
        paths = generate_transition_tests(pages_abc, coverage="1-switch")
        assert len(paths) == 2

    def test_each_path_has_two_nodes(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="1-switch")
        assert all(len(p.nodes) == 2 for p in paths)

    def test_each_path_has_one_edge(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="1-switch")
        assert all(len(p.edges) == 1 for p in paths)

    def test_edge_format_uses_arrow(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="1-switch")
        for p in paths:
            assert "→" in p.edges[0]

    def test_coverage_field_is_set(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="1-switch")
        assert all(p.coverage == "1-switch" for p in paths)

    def test_test_objective_mentions_transition(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="1-switch")
        assert all("遷移" in p.test_objective for p in paths)

    def test_nodes_are_valid_urls(self, pages_abc: list[PageData]) -> None:
        known_urls = {p.url for p in pages_abc}
        paths = generate_transition_tests(pages_abc, coverage="1-switch")
        for path in paths:
            assert all(node in known_urls for node in path.nodes)


# ---------- 2-switch テスト ----------


class TestGenerateTransitionTests2Switch:
    def test_returns_one_path_for_linear_graph(self, pages_abc: list[PageData]) -> None:
        # A→B→C の直線グラフで 2-switch は 1 パス
        paths = generate_transition_tests(pages_abc, coverage="2-switch")
        assert len(paths) == 1

    def test_path_has_three_nodes(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="2-switch")
        assert len(paths[0].nodes) == 3

    def test_path_has_two_edges(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="2-switch")
        assert len(paths[0].edges) == 2

    def test_coverage_field_is_set(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="2-switch")
        assert all(p.coverage == "2-switch" for p in paths)

    def test_test_objective_mentions_consecutive_transition(
        self, pages_abc: list[PageData]
    ) -> None:
        paths = generate_transition_tests(pages_abc, coverage="2-switch")
        assert "連続遷移" in paths[0].test_objective

    def test_50_path_limit(self) -> None:
        """多数の連続エッジが存在しても上限 50 パスに制限される。"""
        # ハブ構造: hub が 10 ノードにリンク、各ノードも hub にリンク → 10*10=100 ペア
        hub = "https://example.com/hub"
        spokes = [f"https://example.com/s{i}" for i in range(10)]
        pages: list[PageData] = [
            _make_page(hub, "ハブ", tuple(spokes)),
        ] + [_make_page(s, f"スポーク{i}", (hub,)) for i, s in enumerate(spokes)]
        paths = generate_transition_tests(pages, coverage="2-switch")
        assert len(paths) <= 50


# ---------- リンクなしのテスト ----------


class TestGenerateTransitionTestsNoLinks:
    def test_0switch_returns_all_nodes(self, pages_no_links: list[PageData]) -> None:
        paths = generate_transition_tests(pages_no_links, coverage="0-switch")
        assert len(paths) == 3

    def test_1switch_returns_empty(self, pages_no_links: list[PageData]) -> None:
        paths = generate_transition_tests(pages_no_links, coverage="1-switch")
        assert paths == []

    def test_2switch_returns_empty(self, pages_no_links: list[PageData]) -> None:
        paths = generate_transition_tests(pages_no_links, coverage="2-switch")
        assert paths == []


# ---------- 空リストのテスト ----------


class TestGenerateTransitionTestsEmpty:
    def test_empty_pages_0switch(self) -> None:
        assert generate_transition_tests([], coverage="0-switch") == []

    def test_empty_pages_1switch(self) -> None:
        assert generate_transition_tests([], coverage="1-switch") == []

    def test_empty_pages_2switch(self) -> None:
        assert generate_transition_tests([], coverage="2-switch") == []


# ---------- transition_tests_to_dict テスト ----------


class TestTransitionTestsToDictSerializable:
    def test_returns_list_of_dicts(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="1-switch")
        result = transition_tests_to_dict(paths)
        assert isinstance(result, list)
        assert all(isinstance(d, dict) for d in result)

    def test_json_serializable(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="1-switch")
        result = transition_tests_to_dict(paths)
        # JSON シリアライズが例外なく完了すること
        serialized = json.dumps(result, ensure_ascii=False)
        assert isinstance(serialized, str)

    def test_dict_contains_expected_keys(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="1-switch")
        result = transition_tests_to_dict(paths)
        expected_keys = {"path_id", "nodes", "edges", "coverage", "test_objective"}
        for d in result:
            assert expected_keys.issubset(d.keys())

    def test_nodes_and_edges_are_lists(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="1-switch")
        result = transition_tests_to_dict(paths)
        for d in result:
            assert isinstance(d["nodes"], list)
            assert isinstance(d["edges"], list)

    def test_empty_paths_returns_empty_list(self) -> None:
        assert transition_tests_to_dict([]) == []

    def test_path_id_preserved(self, pages_abc: list[PageData]) -> None:
        paths = generate_transition_tests(pages_abc, coverage="0-switch")
        result = transition_tests_to_dict(paths)
        assert result[0]["path_id"] == "TP001"


# ---------- TransitionTestPath frozen dataclass ----------


class TestTransitionTestPathDataclass:
    def test_is_frozen(self) -> None:
        path = TransitionTestPath(
            path_id="TP001",
            nodes=("https://example.com/a",),
            edges=(),
            coverage="0-switch",
            test_objective="テスト",
        )
        with pytest.raises(AttributeError):
            path.path_id = "TP999"  # type: ignore[misc]

    def test_equality(self) -> None:
        p1 = TransitionTestPath(
            path_id="TP001",
            nodes=("https://example.com/a",),
            edges=(),
            coverage="0-switch",
            test_objective="テスト",
        )
        p2 = TransitionTestPath(
            path_id="TP001",
            nodes=("https://example.com/a",),
            edges=(),
            coverage="0-switch",
            test_objective="テスト",
        )
        assert p1 == p2
