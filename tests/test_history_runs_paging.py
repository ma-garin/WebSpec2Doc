"""実行履歴 API のページング（INC-P01 の回帰防止）

実行履歴は使うほど増える。全件返却のままだと応答サイズ・DOM 行数が利用量に
比例して劣化するため、既定で直近 N 件に絞る契約を固定する。

対応するインシデント: docs/quality/iso29119-incident-report.md の INC-P01
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.auto_run as auto_run_mod


def _client() -> Any:
    return appmod.app.test_client()


@pytest.fixture()
def many_runs(monkeypatch: pytest.MonkeyPatch) -> int:
    """新しい順に並んだ実行履歴を既定上限より多く用意する。"""
    total = auto_run_mod.HISTORY_RUNS_DEFAULT_LIMIT + 50
    runs = [
        {
            "run_id": f"run-{i:05d}",
            "domain": "example.com",
            "type": "autorun",
            "status": "complete",
            "timestamp": f"2026-08-{(i % 28) + 1:02d}T00:00:00",
        }
        for i in range(total)
    ]
    monkeypatch.setattr(auto_run_mod, "_attach_stage_approval", lambda _runs: None)
    monkeypatch.setattr(
        "web.services.usage_tracker.build_run_history",
        lambda *_args, **_kwargs: list(runs),
    )
    return total


def test_defaults_to_recent_page_not_everything(many_runs: int) -> None:
    """既定では全件を返さない。total で総数が分かる。"""
    data = _client().get("/api/history/runs").get_json()

    assert len(data["runs"]) == auto_run_mod.HISTORY_RUNS_DEFAULT_LIMIT
    assert data["total"] == many_runs
    assert data["limit"] == auto_run_mod.HISTORY_RUNS_DEFAULT_LIMIT
    assert data["offset"] == 0


def test_returns_newest_first_page(many_runs: int) -> None:
    """既定ページは先頭（＝新しい順の先頭）から返す。"""
    data = _client().get("/api/history/runs").get_json()

    assert data["runs"][0]["run_id"] == "run-00000"


def test_offset_moves_the_window(many_runs: int) -> None:
    data = _client().get("/api/history/runs?limit=10&offset=20").get_json()

    assert [r["run_id"] for r in data["runs"]] == [f"run-{i:05d}" for i in range(20, 30)]
    assert data["total"] == many_runs


def test_limit_zero_returns_everything_for_backward_compatibility(many_runs: int) -> None:
    """ページング導入前の呼び出し元のために全件取得の口を残す。"""
    data = _client().get("/api/history/runs?limit=0").get_json()

    assert len(data["runs"]) == many_runs


def test_limit_is_capped(many_runs: int) -> None:
    """上限を超える要求は上限へ丸める（際限のない応答を作らせない）。"""
    data = _client().get(f"/api/history/runs?limit={auto_run_mod.HISTORY_RUNS_MAX_LIMIT * 10}").get_json()

    assert data["limit"] == auto_run_mod.HISTORY_RUNS_MAX_LIMIT


@pytest.mark.parametrize("query", ["limit=abc", "offset=-5", "offset=xyz", "limit=-1"])
def test_invalid_paging_args_fall_back_instead_of_500(query: str, many_runs: int) -> None:
    """不正な引数で 500 にしない。利用者に見えるのは常に履歴。"""
    resp = _client().get(f"/api/history/runs?{query}")

    assert resp.status_code == 200
    assert resp.get_json()["offset"] >= 0


def test_offset_beyond_total_returns_empty_page_not_error(many_runs: int) -> None:
    data = _client().get(f"/api/history/runs?offset={many_runs + 100}").get_json()

    assert data["runs"] == []
    assert data["total"] == many_runs


def test_type_filter_scopes_total_and_stats(monkeypatch: pytest.MonkeyPatch) -> None:
    """種別で絞ったとき、total と stats はその種別だけを母数にする。

    画面側が全件を取ってから絞ると、ページングと件数表示が両立しない
    （表示中の 200 件を数えた値を「実行数」として出してしまう）。
    """
    runs = (
        [{"run_id": f"a{i}", "type": "autorun", "status": "complete"} for i in range(7)]
        + [{"run_id": f"c{i}", "type": "crawl", "status": "failed"} for i in range(5)]
        + [{"run_id": f"t{i}", "type": "testcase_run", "status": "failed"} for i in range(3)]
    )
    monkeypatch.setattr(auto_run_mod, "_attach_stage_approval", lambda _runs: None)
    monkeypatch.setattr(
        "web.services.usage_tracker.build_run_history", lambda *_a, **_k: list(runs)
    )

    data = _client().get("/api/history/runs?type=autorun,testcase_run").get_json()

    assert data["total"] == 10  # crawl の 5 件は母数に入らない
    assert data["stats"] == {"total": 10, "complete": 7, "failed": 3, "cancelled": 0}
    assert {r["type"] for r in data["runs"]} == {"autorun", "testcase_run"}


def test_stats_counts_all_pages_not_just_the_returned_one(many_runs: int) -> None:
    """stats は返した 1 ページではなく、絞り込み後の全件を数える。"""
    data = _client().get("/api/history/runs?limit=10").get_json()

    assert len(data["runs"]) == 10
    assert data["stats"]["total"] == many_runs


def test_unknown_type_yields_empty_result_not_error(many_runs: int) -> None:
    data = _client().get("/api/history/runs?type=no-such-type").get_json()

    assert data["runs"] == []
    assert data["total"] == 0
    assert data["stats"]["total"] == 0
