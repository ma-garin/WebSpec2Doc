from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import Browser, sync_playwright

DEFAULT_AUTH_FILE = "auth.json"
LOGIN_PROMPT = "ブラウザでログインを完了したら、このターミナルで Enter を押してください... "

logger = logging.getLogger(__name__)


def capture_auth_state(login_url: str, output_path: Path) -> Path:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(login_url)
            logger.info("ログインページを開きました: %s", login_url)
            input(LOGIN_PROMPT)
            context.storage_state(path=str(output_path))
            logger.info("セッションを保存しました: %s", output_path)
        finally:
            _close_browser(browser)
    return output_path


def _close_browser(browser: Browser) -> None:
    try:
        browser.close()
    except Exception as exc:
        logger.warning("ブラウザ終了時にエラーが発生しました: %s", exc)
