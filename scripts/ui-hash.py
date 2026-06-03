#!/usr/bin/env python3
"""UI ファイルのコンテンツハッシュを計算する（クロスプラットフォーム）。

使い方:
    python scripts/ui-hash.py disk    # ディスク上の UI ファイルをハッシュ
    python scripts/ui-hash.py staged  # git staged の UI ファイルをハッシュ
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

UI_EXTENSIONS = {".html", ".js", ".css"}
EXCLUDE_DIRS = {".git", "venv", "node_modules", "output", "__pycache__"}


def _ui_files_on_disk() -> list[str]:
    root = Path(".")
    paths: list[str] = []
    for ext in UI_EXTENSIONS:
        for p in root.rglob(f"*{ext}"):
            parts = set(p.parts)
            if not parts & EXCLUDE_DIRS:
                paths.append(str(p))
    return sorted(paths)


def _ui_files_staged() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
    )
    return sorted(
        f for f in result.stdout.strip().splitlines()
        if Path(f).suffix in UI_EXTENSIONS
    )


def compute_hash(mode: str = "disk") -> str:
    files = _ui_files_staged() if mode == "staged" else _ui_files_on_disk()
    h = hashlib.sha256()
    for path_str in files:
        p = Path(path_str)
        if p.exists():
            h.update(path_str.encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:32]


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "disk"
    print(compute_hash(mode))
