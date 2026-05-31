"""registry.session_store のユニットテスト（tmp ディレクトリでセッション管理を検証）"""

from __future__ import annotations

from pathlib import Path

from registry.session_store import (
    has_session,
    session_age_seconds,
    session_path,
    signal_path,
)


class TestSessionStore:
    def test_session_path_is_under_domain(self, tmp_path: Path) -> None:
        assert session_path("example.com", tmp_path) == tmp_path / "example.com" / "auth.json"

    def test_signal_path_is_under_domain(self, tmp_path: Path) -> None:
        assert signal_path("example.com", tmp_path) == tmp_path / "example.com" / ".login_done"

    def test_has_session_false_when_missing(self, tmp_path: Path) -> None:
        assert has_session("example.com", tmp_path) is False

    def test_has_session_true_when_present(self, tmp_path: Path) -> None:
        path = session_path("example.com", tmp_path)
        path.parent.mkdir(parents=True)
        path.write_text("{}", encoding="utf-8")
        assert has_session("example.com", tmp_path) is True

    def test_session_age_none_when_missing(self, tmp_path: Path) -> None:
        assert session_age_seconds("example.com", tmp_path) is None

    def test_session_age_is_small_for_fresh_file(self, tmp_path: Path) -> None:
        path = session_path("example.com", tmp_path)
        path.parent.mkdir(parents=True)
        path.write_text("{}", encoding="utf-8")
        age = session_age_seconds("example.com", tmp_path)
        assert age is not None and age < 5
