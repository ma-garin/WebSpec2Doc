"""画面別URL（/settings, /viewpoints 等）ルートの統合テスト。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as appmod  # noqa: E402


def _client():
    return appmod.app.test_client()


class TestPageRoutes:
    def test_root_renders_index(self) -> None:
        response = _client().get("/", headers={"Host": "127.0.0.1"})
        assert response.status_code == 200
        assert 'id="view-dashboard"' in response.get_data(as_text=True)

    def test_known_view_paths_render_index(self) -> None:
        client = _client()
        for path in (
            "/dashboard",
            "/generate",
            "/qa-quality",
            "/viewpoints",
            "/auto-run",
            "/user-guide",
            "/settings",
        ):
            response = client.get(path, headers={"Host": "127.0.0.1"})
            assert response.status_code == 200, path
            assert 'id="app-content"' in response.get_data(as_text=True)

    def test_home_alias_renders_index(self) -> None:
        response = _client().get("/home", headers={"Host": "127.0.0.1"})
        assert response.status_code == 200
        assert 'id="view-dashboard"' in response.get_data(as_text=True)

    def test_unknown_view_path_returns_404(self) -> None:
        response = _client().get("/not-a-real-view", headers={"Host": "127.0.0.1"})
        assert response.status_code == 404
