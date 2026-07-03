"""ROI ダッシュボードルート（/api/usage, /usage）の統合テスト。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as appmod  # noqa: E402


def _client():
    return appmod.app.test_client()


class TestUsageApi:
    def test_api_usage_returns_summary_shape(self) -> None:
        response = _client().get("/api/usage", headers={"Host": "127.0.0.1"})
        assert response.status_code == 200
        data = response.get_json()
        for key in (
            "total_crawls",
            "total_screens",
            "estimated_saved_hours",
            "estimated_saved_yen",
            "coefficients",
            "disclaimer",
            "record_count",
        ):
            assert key in data

    def test_usage_view_renders(self) -> None:
        response = _client().get("/usage", headers={"Host": "127.0.0.1"})
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "ROI ダッシュボード" in body
        assert "推定削減工数" in body
