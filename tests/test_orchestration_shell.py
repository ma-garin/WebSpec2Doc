"""指揮の殻の統一（D-P0-3）: /orchestration と実行履歴（/orchestration/d）が同じ共通シェル・
サイドバー・asset version を使い、旧比較案 b は正本へ転送される。"""

from __future__ import annotations

import re

import pytest

ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import app

    monkeypatch.setattr("web.routes.orchestration._out", lambda: tmp_path)
    app.config["TESTING"] = True
    return app.test_client()


def _html(client, path: str) -> str:
    res = client.get(path)
    assert res.status_code == 200, path
    return res.get_data(as_text=True)


def _versions(html: str) -> set[str]:
    return set(re.findall(r'\.(?:css|js)\?v=([^"&]+)"', html))


def test_home_and_history_share_shell_and_sidebar(client):
    for path in ("/orchestration", "/orchestration/d"):
        html = _html(client, path)
        assert 'class="app-shell"' in html, path
        assert "app-sidebar" in html, path  # partials/conductor-sidebar.html
        assert 'href="/orchestration/d"' in html, path  # 実行履歴の導線
        assert 'id="app-content"' in html, path


def test_history_marks_its_nav_item_current(client):
    html = _html(client, "/orchestration/d")
    m = re.search(r'<a class="app-nav-item is-active" href="/orchestration/d" aria-current="page">', html)
    assert m is not None


def test_asset_version_is_single_mechanism(client):
    home, hist = _html(client, "/orchestration"), _html(client, "/orchestration/d")
    assert len(_versions(home)) == 1
    assert _versions(home) == _versions(hist)


def test_retired_variant_b_redirects_to_canonical(client):
    res = client.get("/orchestration/b?site=example.com")
    assert res.status_code == 301
    assert res.headers["Location"].endswith("/orchestration")


def test_unknown_variant_is_404(client):
    assert client.get("/orchestration/zz").status_code == 404


def test_ab_event_rejects_retired_variant(client):
    res = client.post("/api/orchestration/ab", json={"variant": "b", "event": "view", "ms": 1}, headers=ORIGIN)
    assert res.status_code == 400


def test_no_production_link_to_retired_b(client):
    for path in ("/orchestration", "/orchestration/d", "/systems"):
        assert "/orchestration/b" not in _html(client, path), path
