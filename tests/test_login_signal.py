"""crawler.login_signal.wait_for_signal のユニットテスト"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from crawler.login_signal import wait_for_signal


def test_returns_true_when_signal_already_present(tmp_path: Path) -> None:
    sig = tmp_path / ".login_done"
    sig.write_text("", encoding="utf-8")
    assert wait_for_signal(sig, timeout=1.0, poll_interval=0.01) is True


def test_returns_false_on_timeout(tmp_path: Path) -> None:
    sig = tmp_path / ".login_done"
    assert wait_for_signal(sig, timeout=0.1, poll_interval=0.01) is False


def test_returns_true_when_signal_appears_later(tmp_path: Path) -> None:
    sig = tmp_path / ".login_done"

    def _create() -> None:
        time.sleep(0.05)
        sig.write_text("", encoding="utf-8")

    threading.Thread(target=_create).start()
    assert wait_for_signal(sig, timeout=2.0, poll_interval=0.01) is True
