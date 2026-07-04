"""Playwright ブラウザをプロジェクト単位で管理・検証する。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

PLAYWRIGHT_BROWSERS_PATH_ENV = "PLAYWRIGHT_BROWSERS_PATH"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BROWSERS_PATH = PROJECT_ROOT / ".runtime" / "ms-playwright"


class PlaywrightRuntimeError(RuntimeError):
    """対応ブラウザが欠落・破損している場合の起動エラー。"""


@dataclass(frozen=True)
class PlaywrightRuntimeInfo:
    browsers_path: Path
    chromium_version: str


def configure_playwright_browsers_path() -> Path:
    """明示設定を尊重しつつ、既定値をリポジトリ配下へ固定する。"""
    configured = os.environ.setdefault(
        PLAYWRIGHT_BROWSERS_PATH_ENV,
        str(DEFAULT_BROWSERS_PATH),
    )
    return Path(configured).expanduser().resolve()


def verify_playwright_runtime() -> PlaywrightRuntimeInfo:
    """Chromiumを実際に起動し、実行可能なランタイムであることを確認する。"""
    browsers_path = configure_playwright_browsers_path()

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                version = browser.version
            finally:
                browser.close()
    except Exception as exc:
        command = f"{Path(sys.executable)} scripts/manage_playwright_runtime.py install"
        raise PlaywrightRuntimeError(
            "解析用Chromiumを起動できません。"
            f"PLAYWRIGHT_BROWSERS_PATH={browsers_path}。"
            f"'{command}' を実行してください。"
        ) from exc

    return PlaywrightRuntimeInfo(
        browsers_path=browsers_path,
        chromium_version=version,
    )
