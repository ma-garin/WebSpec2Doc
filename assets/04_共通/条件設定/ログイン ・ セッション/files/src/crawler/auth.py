from __future__ import annotations

import logging
from pathlib import Path

from playwright.sync_api import Browser, sync_playwright

DEFAULT_AUTH_FILE = "auth.json"
LOGIN_PROMPT = "ブラウザでログインを完了したら、このターミナルで Enter を押してください... "
SIGNAL_WAIT_TIMEOUT_SEC = 600.0

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
            if output_path.exists():
                output_path.chmod(0o600)
            logger.info("セッションを保存しました: %s", output_path)
        finally:
            _close_browser(browser)
    return output_path


def capture_auth_state_via_signal(
    login_url: str,
    output_path: Path,
    signal_file: Path,
    timeout: float = SIGNAL_WAIT_TIMEOUT_SEC,
) -> Path | None:
    """GUI 手渡しログイン用。signal_file の出現を待ってセッションを保存する（ADR-0001）。
    タイムアウト時は None を返し、セッションは保存しない。

    実体は auth_recorder.record_auth_session への薄いラッパー（SPEC-3-2）。
    ログイン完了検知の提示・保存後の検証は record_auth_session 側で行うが、
    ここでは既存呼び出し元との互換のため Path | None のみを返す。"""
    from crawler.auth_recorder import PHASE_SAVED, record_auth_session

    status = record_auth_session(
        login_url=login_url,
        auth_path=output_path,
        signal_file=signal_file,
        timeout=timeout,
        headless=False,
    )
    if status.phase != PHASE_SAVED:
        logger.warning("ログイン完了シグナルを待機中にタイムアウトしました")
        return None
    logger.info("セッションを保存しました: %s", output_path)
    return output_path


def _close_browser(browser: Browser) -> None:
    try:
        browser.close()
    except Exception as exc:
        logger.warning("ブラウザ終了時にエラーが発生しました: %s", exc)
