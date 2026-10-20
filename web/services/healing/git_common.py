"""git 操作（dulwich 実装）の共通部品。結果型と例外の畳み込みだけを置く。

製品の実行時に git コマンドを起動しない方針（外部 CLI 不要）のため、
読取は git_read.py、書込は git_write.py で dulwich を直接呼ぶ。
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class GitResult:
    """git 操作 1 回分の結果。

    例外を投げる代わりにこの型で失敗を表現する。呼び出し側（orchestrator）は
    try/except を書かずに ok を見るだけで分岐できる。
    """

    ok: bool
    stdout: str
    stderr: str
    exit_code: int


def strip_ansi(text: str) -> str:
    """色付き出力から装飾を落とす。画面と PR 本文にそのまま出るため。"""
    return re.sub(r"\x1b\[[0-9;]*m", "", text or "")


def ok_result(stdout: str = "") -> GitResult:
    return GitResult(ok=True, stdout=stdout, stderr="", exit_code=0)


def fail_result(message: str, exit_code: int = 1) -> GitResult:
    return GitResult(ok=False, stdout="", stderr=strip_ansi(message)[:500], exit_code=exit_code)


def describe_error(exc: BaseException) -> str:
    """例外を 1 行の説明にする（空文字になる例外は型名で補う）。"""
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__
