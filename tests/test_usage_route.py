"""ROI ダッシュボードルート（/api/usage, /usage）の統合テスト。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as appmod  # noqa: E402
import web.routes.usage as usage_route  # noqa: E402
from web.services.usage_tracker import record_usage  # noqa: E402


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


class TestUsageApiComparisonAndUxReview:
    """AC-1・AC-2 の結合テスト（§6-2）: comparison/ux_review 記録後の /api/usage。"""

    def test_reflects_comparison_and_ux_review_records(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(usage_route, "OUTPUT_DIR", tmp_path)
        record_usage(
            tmp_path,
            event="comparison",
            domain="example.com",
            compare_screen_count=5,
            finding_count=12,
        )
        record_usage(
            tmp_path,
            event="ux_review",
            domain="example.com",
            compare_screen_count=3,
            finding_count=7,
        )
        response = _client().get("/api/usage", headers={"Host": "127.0.0.1"})
        assert response.status_code == 200
        data = response.get_json()
        # 新旧キーの両方が存在すること（既存キー改名・削除の検知）
        for key in ("total_crawls", "total_screens", "total_compare_screens", "total_findings"):
            assert key in data
        assert data["total_compare_screens"] == 5 + 3
        assert data["total_findings"] == 12 + 7
        assert "minutes_per_compare_screen" in data["coefficients"]
        assert "minutes_per_ux_finding" in data["coefficients"]
        assert "推定値" in data["disclaimer"]
