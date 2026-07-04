#!/usr/bin/env python3
"""Playwright と同じ Python 環境へ対応 Chromium を導入・検証する。"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from crawler.playwright_runtime import (  # noqa: E402
    PLAYWRIGHT_BROWSERS_PATH_ENV,
    configure_playwright_browsers_path,
    verify_playwright_runtime,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Playwright Chromium ランタイム管理")
    subparsers = parser.add_subparsers(dest="command", required=True)
    install = subparsers.add_parser("install", help="対応 Chromium を導入して起動確認")
    install.add_argument(
        "--with-deps",
        action="store_true",
        help="Linux のシステム依存パッケージも導入する",
    )
    subparsers.add_parser("check", help="Chromium の実起動確認のみ行う")
    return parser.parse_args()


def install_runtime(with_deps: bool) -> None:
    browsers_path = configure_playwright_browsers_path()
    browsers_path.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "playwright", "install"]
    if with_deps:
        command.append("--with-deps")
    command.append("chromium")
    env = {**os.environ, PLAYWRIGHT_BROWSERS_PATH_ENV: str(browsers_path)}
    subprocess.run(command, check=True, cwd=ROOT, env=env)


def main() -> None:
    args = parse_args()
    if args.command == "install":
        install_runtime(bool(args.with_deps))
    info = verify_playwright_runtime()
    print(f"Chromium {info.chromium_version} 起動確認済み: {info.browsers_path}")


if __name__ == "__main__":
    main()
