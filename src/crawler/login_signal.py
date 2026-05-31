"""手渡しログインの完了シグナル待機（ADR-0001）。

GUI の「ログイン完了」ボタンが置くシグナルファイルの出現を、ログイン用
サブプロセスがポーリングして待つ。input() による端末待ちの代替。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

DEFAULT_POLL_INTERVAL_SEC = 0.5

logger = logging.getLogger(__name__)


def wait_for_signal(
    signal_file: Path, timeout: float, poll_interval: float = DEFAULT_POLL_INTERVAL_SEC
) -> bool:
    """signal_file が出現したら True、timeout 秒経過しても無ければ False。"""
    deadline = time.monotonic() + timeout
    while True:
        if signal_file.exists():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(poll_interval)
