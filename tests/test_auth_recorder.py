"""認証フローレコーダー（SPEC-3-2）のユニットテスト。実ブラウザ不要・フェイク page 注入。

フェイクは tests/test_capture.py::_FakeRecorderPage・
tests/test_real_site_resilience.py::_FakeClock に倣う。
"""

from __future__ import annotations

import json
from pathlib import Path

from crawler.auth_recorder import (
    PHASE_CLOSED,
    PHASE_SAVED,
    PHASE_TIMEOUT,
    RecorderStatus,
    _run_recorder_loop,
    _write_status,
    verify_auth_state,
)

LOGIN_URL = "https://example.com/login"


class _FakeAuthContext:
    """context.storage_state() の呼び出しを記録するフェイク。"""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.saved_paths: list[str] = []

    def storage_state(self, path: str) -> None:
        if self.fail:
            raise RuntimeError("ディスク書き込みに失敗しました（フェイク）")
        Path(path).write_text("{}", encoding="utf-8")
        self.saved_paths.append(path)


class _FakeAuthPage:
    """(url, パスワード欄有無) の遷移列を1周ごとに1ステップ進めるフェイク。"""

    def __init__(self, steps: list[tuple[str, bool]]) -> None:
        self._steps = steps
        self._index = 0

    @property
    def url(self) -> str:
        idx = min(self._index, len(self._steps) - 1)
        return self._steps[idx][0]

    def evaluate(self, _js: str) -> bool:
        idx = min(self._index, len(self._steps) - 1)
        has_password = self._steps[idx][1]
        self._index += 1
        return has_password


class _FakeClosingPage:
    """evaluate が例外を投げる＝ブラウザが閉じられた状態を模すフェイク。"""

    def __init__(self, url: str = LOGIN_URL) -> None:
        self.url = url

    def evaluate(self, _js: str) -> bool:
        raise RuntimeError("Target page, context or browser has been closed")


class TestRunRecorderLoop:
    def test_signal_saves_auth_with_permission(self, tmp_path: Path, monkeypatch) -> None:
        """AC-1: シグナルが出現するとセッションを保存し、chmod 600 になる。"""
        auth_path = tmp_path / "auth.json"
        signal_file = tmp_path / ".login_signal"
        page = _FakeAuthPage([(LOGIN_URL, True)])
        context = _FakeAuthContext()

        # 2周目のポーリングでシグナルが出現する想定（人が「ログイン完了」を押す想定）
        calls = {"n": 0}

        def sleeper(_sec: float) -> None:
            calls["n"] += 1
            if calls["n"] >= 1:
                signal_file.touch()

        monkeypatch.setattr("crawler.auth_recorder.verify_auth_state", lambda *_a, **_k: True)

        status = _run_recorder_loop(
            page=page,
            context=context,
            login_url=LOGIN_URL,
            auth_path=auth_path,
            signal_file=signal_file,
            status_file=None,
            timeout=10.0,
            poll_interval=0.0,
            clock=lambda: 0.0,
            sleeper=sleeper,
        )

        assert status.phase == PHASE_SAVED
        assert context.saved_paths == [str(auth_path)]
        assert auth_path.exists()
        assert oct(auth_path.stat().st_mode)[-3:] == "600"
        assert status.verified is True

    def test_login_detected_phase_without_save(self, tmp_path: Path) -> None:
        """AC-3: パスワード欄消失＋URL変化で login_detected を提示するが保存はしない。"""
        auth_path = tmp_path / "auth.json"
        signal_file = tmp_path / ".login_signal"  # 意図的に作らない
        status_file = tmp_path / ".login_status.json"
        page = _FakeAuthPage(
            [
                (LOGIN_URL, True),
                ("https://example.com/home", False),
                ("https://example.com/home", False),
            ]
        )
        context = _FakeAuthContext()
        seen_phases: list[str] = []
        clock_state = {"t": 0.0}

        def clock() -> float:
            return clock_state["t"]

        def sleeper(_sec: float) -> None:
            data = json.loads(status_file.read_text(encoding="utf-8"))
            seen_phases.append(data["phase"])
            clock_state["t"] += 5.0  # 2回のポーリング後にタイムアウトさせループを終える

        status = _run_recorder_loop(
            page=page,
            context=context,
            login_url=LOGIN_URL,
            auth_path=auth_path,
            signal_file=signal_file,
            status_file=status_file,
            timeout=10.0,
            poll_interval=0.0,
            clock=clock,
            sleeper=sleeper,
        )

        assert "login_detected" in seen_phases
        assert status.phase == PHASE_TIMEOUT
        assert not auth_path.exists()

    def test_timeout_leaves_no_auth_file(self, tmp_path: Path) -> None:
        """AC-4: timeout 秒シグナルなしなら phase=timeout・auth.json は作成しない。"""
        auth_path = tmp_path / "auth.json"
        signal_file = tmp_path / ".login_signal"
        page = _FakeAuthPage([(LOGIN_URL, True)])
        context = _FakeAuthContext()
        clock_state = {"t": 0.0}

        def clock() -> float:
            return clock_state["t"]

        def sleeper(_sec: float) -> None:
            clock_state["t"] += 1.0

        status = _run_recorder_loop(
            page=page,
            context=context,
            login_url=LOGIN_URL,
            auth_path=auth_path,
            signal_file=signal_file,
            status_file=None,
            timeout=0.5,
            poll_interval=0.0,
            clock=clock,
            sleeper=sleeper,
        )

        assert status.phase == PHASE_TIMEOUT
        assert not auth_path.exists()
        assert not context.saved_paths

    def test_page_closed_returns_closed(self, tmp_path: Path) -> None:
        """AC-5: 保存前にブラウザが閉じられたら例外を出さず phase=closed。"""
        auth_path = tmp_path / "auth.json"
        signal_file = tmp_path / ".login_signal"
        page = _FakeClosingPage()
        context = _FakeAuthContext()

        status = _run_recorder_loop(
            page=page,
            context=context,
            login_url=LOGIN_URL,
            auth_path=auth_path,
            signal_file=signal_file,
            status_file=None,
            timeout=5.0,
            poll_interval=0.0,
            clock=lambda: 0.0,
            sleeper=lambda _sec: None,
        )

        assert status.phase == PHASE_CLOSED
        assert not auth_path.exists()

    def test_storage_state_failure_leaves_no_partial_file(self, tmp_path: Path) -> None:
        """保存失敗時は部分ファイルを残さずエラーにする（5-2 エラー処理表）。"""
        auth_path = tmp_path / "auth.json"
        signal_file = tmp_path / ".login_signal"
        signal_file.touch()  # 最初のポーリングで即座にシグナルが見つかる
        page = _FakeAuthPage([(LOGIN_URL, True)])
        context = _FakeAuthContext(fail=True)

        status = _run_recorder_loop(
            page=page,
            context=context,
            login_url=LOGIN_URL,
            auth_path=auth_path,
            signal_file=signal_file,
            status_file=None,
            timeout=5.0,
            poll_interval=0.0,
            clock=lambda: 0.0,
            sleeper=lambda _sec: None,
        )

        assert status.phase == "error"
        assert not auth_path.exists()


class TestWriteStatusAtomic:
    def test_status_file_written_atomically(self, tmp_path: Path) -> None:
        """5-1: status_file には .tmp 経由で JSON が原子的に上書きされる。"""
        status_file = tmp_path / ".login_status.json"
        status = RecorderStatus(phase="waiting", current_url=LOGIN_URL)

        _write_status(status_file, status)

        assert status_file.exists()
        assert not status_file.with_name(status_file.name + ".tmp").exists()
        data = json.loads(status_file.read_text(encoding="utf-8"))
        assert data == {
            "phase": "waiting",
            "current_url": LOGIN_URL,
            "detail": "",
            "verified": None,
        }

        # 2回目の上書きでも一貫して読める（.tmp が残らない）
        _write_status(
            status_file, RecorderStatus(phase="saved", current_url=LOGIN_URL, verified=True)
        )
        data2 = json.loads(status_file.read_text(encoding="utf-8"))
        assert data2["phase"] == "saved"
        assert data2["verified"] is True

    def test_write_status_noop_when_none(self, tmp_path: Path) -> None:
        """status_file=None の場合は何もしない（呼び出し元が任意で渡す設計）。"""
        _write_status(None, RecorderStatus(phase="waiting", current_url=LOGIN_URL))
        assert list(tmp_path.iterdir()) == []


class TestVerifyAuthState:
    def test_verify_auth_state_unreachable_is_none(self, tmp_path: Path) -> None:
        """AC-6: 到達不能 URL の検証は None（未確認）。"""
        auth_path = tmp_path / "auth.json"
        auth_path.write_text("{}", encoding="utf-8")

        result = verify_auth_state("http://127.0.0.1:1/unreachable", auth_path)

        assert result is None

    def test_verify_auth_state_missing_file_is_none(self, tmp_path: Path) -> None:
        """auth.json が存在しない場合も None（未確認）。"""
        auth_path = tmp_path / "auth.json"
        assert verify_auth_state(LOGIN_URL, auth_path) is None
