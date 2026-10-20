"""入力ディレクトリの検証と、参照ファイルの digest 確認（本文は保持しない）。

外部ツール連携の撤去に伴い旧アダプタから移設した共通部。プロセス実行・外部ツールは持たない。
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reverse_analysis.models import Diagnostic

_READ_CHUNK_BYTES = 64 * 1024
_UNSAFE_SEGMENTS = frozenset({"", ".", ".."})


def _diag(code: str, severity: str, stage: str, message: str, next_action: str) -> Diagnostic:
    return Diagnostic(code, severity, stage, message, next_action)


def validate_input_directory(path_text: str) -> tuple[Path | None, Diagnostic | None]:
    """実在する local directory だけを受け付ける。symlink・traversal・単体ファイルは拒否。"""
    rejected = _diag(
        "invalid_static_input", "error", "input",
        "静的解析の入力は、実在するローカルのディレクトリ（シンボリックリンク不可）に限ります。",
        "JS とソースマップを置いたディレクトリを --js-input に指定してください。",
    )  # fmt: skip
    if not path_text or "\x00" in path_text or ".." in Path(path_text).parts:
        return None, rejected
    candidate = Path(os.path.abspath(path_text))
    # 親成分を含む全成分を lstat し、どこかに symlink があれば root 外を指しうるため拒否する。
    for component in (*reversed(candidate.parents), candidate):
        try:
            mode = component.lstat().st_mode
        except OSError:
            return None, rejected
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            return None, rejected
    if not _tree_is_plain(candidate):
        return None, _diag(
            "invalid_static_input", "error", "input",
            "入力ディレクトリの中にシンボリックリンクまたは特殊なファイルがあるため、解析を始めませんでした。",
            "シンボリックリンク・パイプ・デバイスなどを除いた、通常のファイルとディレクトリだけの入力を指定してください。",
        )  # fmt: skip
    return candidate, None


def _tree_is_plain(root: Path) -> bool:
    """root 配下が通常ファイルとディレクトリだけか（symlink は辿らない）。読めない箇所も不可。"""
    pending = [root]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    mode = entry.stat(follow_symlinks=False).st_mode
                    if stat.S_ISDIR(mode):
                        pending.append(Path(entry.path))
                    elif not stat.S_ISREG(mode):
                        return False
        except OSError:
            return False
    return True



def is_safe_relative_path(path: Any) -> bool:
    """相対 path の安全規則（空・絶対・NUL・バックスラッシュ・.. を拒否）。"""
    if not isinstance(path, str) or not path or path.startswith("/") or "\x00" in path or "\\" in path:
        return False
    return all(part not in _UNSAFE_SEGMENTS for part in path.split("/"))


@dataclass(frozen=True)
class VerifiedFile:
    """解析が参照する入力 root 内のファイル。本文は保持しない。"""

    path: str
    status: str  # verified | missing | unsafe | not_regular | unreadable
    sha256: str | None = None
    size: int | None = None


def verify_file(root: Path, relative: str) -> VerifiedFile:
    """root 外・symlink・traversal を拒否し、通常ファイルなら digest と size を取る。"""
    if not is_safe_relative_path(relative):
        return VerifiedFile(relative, "unsafe")
    current = root
    for part in relative.split("/"):
        current = current / part
        try:
            mode = current.lstat().st_mode
        except OSError:
            return VerifiedFile(relative, "missing")
        if stat.S_ISLNK(mode):
            return VerifiedFile(relative, "unsafe")
    if not stat.S_ISREG(mode):
        return VerifiedFile(relative, "not_regular")
    digest = hashlib.sha256()
    size = 0
    try:
        with current.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_READ_CHUNK_BYTES), b""):
                digest.update(chunk)
                size += len(chunk)
    except OSError:
        return VerifiedFile(relative, "unreadable")
    return VerifiedFile(relative, "verified", digest.hexdigest(), size)
