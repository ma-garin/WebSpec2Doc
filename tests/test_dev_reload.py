"""開発時のテンプレート/静的ファイル自動リロード（AGENTS.md S-6）。

UI 変更のたびにサーバ再起動が要ると、1 回 1〜2 分がそのまま開発時間になる。
既定（本番）ではキャッシュを効かせ、環境変数を付けたときだけ外す。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web import create_app  # noqa: E402

ENV = "WEBSPEC2DOC_TEMPLATES_AUTO_RELOAD"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)


class TestDefaultIsProductionBehaviour:
    def test_templates_are_cached_by_default(self, monkeypatch) -> None:
        app = create_app()
        assert app.config["TEMPLATES_AUTO_RELOAD"] is False

    def test_version_is_fixed_at_startup(self, monkeypatch) -> None:
        """本番では起動時に固定した値を配り、ブラウザにキャッシュさせる。"""
        app = create_app()
        ver = app.jinja_env.globals["_ver"]
        assert isinstance(ver, str)
        assert str(ver) == str(ver)


class TestDevReloadEnabled:
    def test_templates_auto_reload_is_on(self, monkeypatch) -> None:
        monkeypatch.setenv(ENV, "1")
        app = create_app()
        assert app.config["TEMPLATES_AUTO_RELOAD"] is True
        assert app.jinja_env.auto_reload is True

    def test_version_changes_between_renders(self, monkeypatch) -> None:
        """`?v=` が変わらないと、ブラウザが古い JS / CSS を使い続ける。

        テンプレートだけ再読み込みされても、JS が古いままだと
        「直したのに直っていない」状態になり、原因調査に時間を取られる。
        """
        monkeypatch.setenv(ENV, "1")
        app = create_app()
        ver = app.jinja_env.globals["_ver"]

        seen = set()
        for stamp in (1000, 1001, 1002):
            monkeypatch.setattr("web.time.time", lambda s=stamp: s)
            seen.add(str(ver))
        assert len(seen) == 3, "レンダリングのたびに _ver が変わっていない"

    def test_other_values_do_not_enable_it(self, monkeypatch) -> None:
        """誤って "true" や "0" を入れても本番挙動のままであること。"""
        for value in ("0", "true", "yes", ""):
            monkeypatch.setenv(ENV, value)
            assert create_app().config["TEMPLATES_AUTO_RELOAD"] is False, value
