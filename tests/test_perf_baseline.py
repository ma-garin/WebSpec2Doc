"""応答サイズのベースライン（ISO/IEC 25010 性能効率性の回帰防止）

このプロジェクトの性能効率性テストは 3,106 件中 5 件しか無く、
INC-P01（実行履歴 API が 3,770 件・1.76MB を全件返す）を検出できなかった。
ここでは「利用量に比例して応答が肥大する」型の劣化を捕まえる。

測るのは応答時間ではなく応答サイズ。時間は実行環境で揺れて flaky になるが、
サイズは決定的で、肥大の原因（件数無制限・全件埋め込み）を直接示す。

ベースライン実測: docs/quality/evidence/perf-baseline.csv（2026-08-23）
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import app as appmod
import web.routes.auto_run as auto_run_mod

# 上限は 2026-08-23 の実測に余裕を持たせた値。ここを引き上げるときは
# 「なぜ肥大したか」を説明できること（安易な緩和は劣化の追認になる）。
MAX_BYTES = {
    # "/" はアプリシェル（index.html）。システム選択ハブは /systems（200）に分離。
    "/": 400_000,
    "/api/history": 200_000,
}

# 実行履歴は使うほど増える。既定ページは総数に依存してはならない。
HISTORY_RUNS_MAX_BYTES = 400_000


def _client() -> Any:
    return appmod.app.test_client()


@pytest.mark.parametrize("path", sorted(MAX_BYTES))
def test_response_size_stays_within_baseline(path: str) -> None:
    resp = _client().get(path)

    # 認証設定によっては 302/401 になる。その場合はサイズ検証の対象外。
    if resp.status_code != 200:
        pytest.skip(f"{path} は {resp.status_code}（この環境では未認証）")
    assert len(resp.data) <= MAX_BYTES[path], (
        f"{path} の応答が {len(resp.data)} bytes で上限 {MAX_BYTES[path]} を超えた"
    )


def test_history_runs_size_does_not_grow_with_total(monkeypatch: pytest.MonkeyPatch) -> None:
    """履歴が 10 倍に増えても既定応答のサイズは変わらない（INC-P01 の回帰防止）。"""

    def _sized_history(count: int) -> list[dict]:
        return [
            {
                "run_id": f"run-{i:06d}",
                "domain": "example.com",
                "type": "autorun",
                "status": "complete",
                "timestamp": "2026-08-23T00:00:00",
                "summary": {"passed": 0, "failed": 0, "total": 0, "duration_sec": 0},
            }
            for i in range(count)
        ]

    monkeypatch.setattr(auto_run_mod, "_attach_stage_approval", lambda _runs: None)

    sizes = []
    for count in (500, 5000):
        monkeypatch.setattr(
            "web.services.usage_tracker.build_run_history",
            lambda *_a, count=count, **_k: _sized_history(count),
        )
        resp = _client().get("/api/history/runs")
        assert resp.status_code == 200
        sizes.append(len(resp.data))
        assert resp.get_json()["total"] == count

    # total の桁数だけは増えるので完全一致にはしない。比例していれば 10 倍になる。
    assert abs(sizes[0] - sizes[1]) <= 100, (
        f"履歴 500 件で {sizes[0]} bytes、5000 件で {sizes[1]} bytes。"
        "既定応答が総数に比例している（ページングが効いていない）"
    )
    assert sizes[0] <= HISTORY_RUNS_MAX_BYTES
