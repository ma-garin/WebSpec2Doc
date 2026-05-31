from __future__ import annotations

import subprocess

# 実行中クロールのサブプロセス（run_id → Popen）。停止ボタンから kill するために保持。
_RUNNING_PROCS: dict[str, subprocess.Popen] = {}


def _terminate_proc(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
