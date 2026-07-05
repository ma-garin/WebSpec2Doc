"""カバレッジヒートマップ生成（解析＝取得状況 / AutoRun＝実行回数×成否）の単体テスト。"""

from __future__ import annotations

import pytest

from generator.heatmap_reporter import (
    classify_analysis_status,
    classify_autorun_status,
    generate_analysis_coverage_html,
    generate_autorun_coverage_html,
)


# --- 解析カバレッジの 3 分類 -------------------------------------------------


@pytest.mark.parametrize(
    "screen,expected",
    [
        ({"captured": True}, "captured"),
        ({"has_screenshot": True}, "captured"),
        ({"screenshot": "p001.png"}, "captured"),
        ({"requires_login": True}, "login"),
        ({"is_login_required": True}, "login"),
        ({}, "missing"),
        ({"captured": False}, "missing"),
        # 取得済みは要ログインより優先（認証後に取得できたケース）
        ({"captured": True, "requires_login": True}, "captured"),
    ],
)
def test_classify_analysis_status(screen: dict, expected: str) -> None:
    assert classify_analysis_status(screen) == expected


# --- AutoRun の成否 2 軸分類 -------------------------------------------------


@pytest.mark.parametrize(
    "runs,passed,failed,expected",
    [
        (0, 0, 0, "none"),
        (3, 3, 0, "pass"),
        (3, 2, 1, "fail"),
        (1, 0, 1, "fail"),
        (5, 5, 0, "pass"),
    ],
)
def test_classify_autorun_status(runs: int, passed: int, failed: int, expected: str) -> None:
    assert classify_autorun_status(runs, passed, failed) == expected


# --- 解析ヒートマップ HTML ---------------------------------------------------


def test_analysis_html_is_self_contained_and_counts() -> None:
    screens = [
        {"page_id": "P001", "title": "トップ", "url": "/", "captured": True},
        {"page_id": "P002", "title": "会員", "url": "/mypage", "requires_login": True},
        {"page_id": "P003", "title": "検索", "url": "/search"},
    ]
    out = generate_analysis_coverage_html(screens)
    assert out.startswith("<!DOCTYPE html>")
    # 外部リソース参照なし（自己完結）
    assert "http://" not in out.replace("http://127.0.0.1", "")
    assert "<script" not in out
    # 3 分類ラベルがすべて描画される
    assert "取得済み" in out and "要ログイン" in out and "未取得" in out
    # 集計タイル: 総 3 / 取得 1 / ログイン 1 / 未取得 1 / 取得率 33%
    assert "<b>3</b>" in out
    assert "33%" in out
    # XSS 対策（エスケープ）
    assert "P001" in out


def test_analysis_html_escapes_titles() -> None:
    screens = [{"page_id": "P001", "title": "<script>x</script>", "url": "/"}]
    out = generate_analysis_coverage_html(screens)
    assert "<script>x</script>" not in out
    assert "&lt;script&gt;" in out


def test_analysis_html_empty() -> None:
    out = generate_analysis_coverage_html([])
    assert out.startswith("<!DOCTYPE html>")
    assert "<b>0</b>" in out
    assert "0%" in out


# --- AutoRun ヒートマップ HTML ----------------------------------------------


def test_autorun_html_two_axis_coloring() -> None:
    screens = [
        {"page_id": "P001", "title": "決済", "url": "/pay", "runs": 7, "passed": 7, "failed": 0},
        {"page_id": "P002", "title": "登録", "url": "/reg", "runs": 2, "passed": 1, "failed": 1},
        {"page_id": "P003", "title": "未実行", "url": "/x", "runs": 0, "passed": 0, "failed": 0},
    ]
    out = generate_autorun_coverage_html(screens)
    assert out.startswith("<!DOCTYPE html>")
    # 成否クラス（色相軸）
    assert "cov autorun pass" in out
    assert "cov autorun fail" in out
    assert "cov autorun none" in out
    # 実行回数バケット（濃淡軸）: 7 回 -> data-runs="4"
    assert 'data-runs="4"' in out
    # 集計: 総 3 / 実行済み 2 / 実行カバレッジ 67% / 総実行 9 / 成功率
    assert "<b>3</b>" in out
    assert "<b>9</b>" in out
    assert "67%" in out


def test_autorun_html_empty() -> None:
    out = generate_autorun_coverage_html([])
    assert out.startswith("<!DOCTYPE html>")
    assert "<b>0</b>" in out
    # 0 除算しない
    assert "0%" in out


def test_autorun_html_all_unexecuted_no_zero_division() -> None:
    screens = [{"page_id": "P001", "title": "a", "url": "/", "runs": 0}]
    out = generate_autorun_coverage_html(screens)
    assert "cov autorun none" in out
    assert "未実行" in out
