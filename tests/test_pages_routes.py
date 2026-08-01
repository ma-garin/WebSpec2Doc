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

    def test_settings_tab_paths_render_index(self) -> None:
        """タブ単位の URL でも設定画面が開ける（リロード・直リンク・共有用）。"""
        client = _client()
        for tab in ("api", "crawl", "notify", "operations", "data", "audit", "test-design"):
            response = client.get(f"/settings/{tab}", headers={"Host": "127.0.0.1"})
            assert response.status_code == 200, tab
            assert 'id="view-settings"' in response.get_data(as_text=True), tab

    def test_unknown_settings_tab_returns_404(self) -> None:
        response = _client().get("/settings/not-a-real-tab", headers={"Host": "127.0.0.1"})
        assert response.status_code == 404

    def test_settings_tabs_cover_rendered_tab_buttons(self) -> None:
        """ルートが受け付けるタブ名と、画面に描画されるタブが食い違わないこと。

        片方だけ増えると「押せるのに直リンクは 404」「URL は通るのに開けない」が起きる。
        """
        import re

        from web.routes.pages import _SETTINGS_TABS

        html = _client().get("/settings", headers={"Host": "127.0.0.1"}).get_data(as_text=True)
        rendered = set(re.findall(r'class="set-tab[^"]*" data-tab="([^"]+)"', html))
        assert rendered, "設定タブが描画されていない"
        assert rendered <= _SETTINGS_TABS, f"ルート未登録のタブ: {rendered - _SETTINGS_TABS}"
