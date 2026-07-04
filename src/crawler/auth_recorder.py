"""認証フローレコーダー（SPEC-3-2）。

「見えるブラウザで人が普通にログインし、ボタン一つで保存する」フローを
実現する中核。ログイン完了はシグナルファイル（ADR-0001 と同じ仕組み）の
出現で確定するが、それとは別にパスワード欄の消失と URL 変化から
「ログインを検知した見込み」を status_file 経由で提示する（AC-3）。
この検知は近似であり、保存トリガーにはしない（evidence-only: 推定を
事実として扱わない。保存は人がシグナルを作った時のみ）。

監視はポーリング方式にする。Playwright sync API の binding コールバック内
から page 操作を行うと再入で行き詰まるため（capture/session_recorder.py
と同じ設計理由）。Flask 開発サーバはワーカー内グローバルを共有しないため、
進行状態はメモリでなく status_file（JSON 1 行・原子的上書き）で公開する。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, sync_playwright

from analyzer.login_wall import PageAuthSignals, detect_login_wall

# auth.py の SIGNAL_WAIT_TIMEOUT_SEC と同値（GUI 手渡しログインの待機上限を共用）
SIGNAL_WAIT_TIMEOUT_SEC = 600.0
DEFAULT_POLL_INTERVAL_SEC = 0.5
VERIFY_TIMEOUT_MS = 10_000

PHASE_WAITING = "waiting"
PHASE_LOGIN_DETECTED = "login_detected"
PHASE_SAVED = "saved"
PHASE_TIMEOUT = "timeout"
PHASE_CLOSED = "closed"
PHASE_ERROR = "error"

# has_password_field(page)（crawler/link_extractor.py）は例外を握りつぶして
# False を返すため、ブラウザクローズの検知には使えない（AC-5 が成立しない）。
# ここでは独自に evaluate() を呼び、例外は呼び出し側でクローズ判定に使う。
_PASSWORD_FIELD_JS = "() => !!document.querySelector('input[type=password]')"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecorderStatus:
    """レコーダーの進行状態。status_file（JSON 1 行）として Web UI へ公開する。"""

    phase: str  # "waiting" / "login_detected" / "saved" / "timeout" / "closed" / "error"
    current_url: str  # 検知時点の URL（evidence: 何を根拠に検知したか）
    detail: str = ""  # 日本語の説明（例: "パスワード欄の消失とURL変化を検知しました"）
    verified: bool | None = None  # AC-6。None = 未検証・未確認


def record_auth_session(
    login_url: str,
    auth_path: Path,
    signal_file: Path,
    status_file: Path | None = None,
    timeout: float = SIGNAL_WAIT_TIMEOUT_SEC,
    headless: bool = False,
    poll_interval: float = DEFAULT_POLL_INTERVAL_SEC,
) -> RecorderStatus:
    """headful ブラウザで人のログインを待ち、シグナル受領時にセッションを保存する。

    ループ内で毎周 (1) signal_file 存在 (2) パスワード欄の有無と page.url を確認する。
    status_file には RecorderStatus を JSON で原子的に上書きする（.tmp → replace）。
    """
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=headless)
        except Exception as exc:  # noqa: BLE001  # DISPLAY なし等、環境要因の起動失敗
            logger.error("ブラウザ起動に失敗しました: %s", exc)
            status = RecorderStatus(
                phase=PHASE_ERROR,
                current_url=login_url,
                detail="この機能はローカル環境で GUI ブラウザを使います",
            )
            _write_status(status_file, status)
            return status
        try:
            context = browser.new_context()
            page = context.new_page()
            try:
                page.goto(login_url)
            except Exception as exc:  # noqa: BLE001
                logger.error("ログインページへの遷移に失敗しました: %s", exc)
                status = RecorderStatus(
                    phase=PHASE_ERROR,
                    current_url=login_url,
                    detail=f"ページを開けませんでした: {exc}",
                )
                _write_status(status_file, status)
                return status
            logger.info("ログインページを開きました: %s", login_url)
            return _run_recorder_loop(
                page=page,
                context=context,
                login_url=login_url,
                auth_path=auth_path,
                signal_file=signal_file,
                status_file=status_file,
                timeout=timeout,
                poll_interval=poll_interval,
                playwright=playwright,
            )
        finally:
            _close_browser(browser)


def _run_recorder_loop(
    page: Any,
    context: Any,
    login_url: str,
    auth_path: Path,
    signal_file: Path,
    status_file: Path | None,
    timeout: float,
    poll_interval: float,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
    playwright: Any | None = None,
) -> RecorderStatus:
    """ポーリングでシグナル・ログイン検知・タイムアウト・クローズを監視するコア処理。

    page / context は Playwright の実オブジェクトのほか、テストではフェイクを
    注入できるようダックタイピングで受け取る（_FakeRecorderPage 等の前例に倣う）。
    playwright は保存後の検証（verify_auth_state）に渡す既存の Playwright
    ドライバ。同一スレッドで sync_playwright() を二重に開始すると
    "Sync API inside the asyncio loop" で失敗するため、呼び出し元が既に
    開いているドライバを再利用する（省略時は verify_auth_state が新規に開く）。
    """
    status = RecorderStatus(phase=PHASE_WAITING, current_url=login_url)
    _write_status(status_file, status)
    login_detected = False
    deadline = clock() + timeout
    current_url = login_url

    while True:
        if signal_file.exists():
            return _save_and_verify(
                context, page, login_url, auth_path, status_file, current_url, playwright
            )

        try:
            current_url = page.url
            has_password = bool(page.evaluate(_PASSWORD_FIELD_JS))
        except Exception as exc:  # noqa: BLE001  # ページ/ブラウザが閉じられた
            logger.info("ブラウザが閉じられました（保存前）: %s", exc)
            status = RecorderStatus(
                phase=PHASE_CLOSED,
                current_url=current_url,
                detail="ブラウザが閉じられました（保存されていません）",
            )
            _write_status(status_file, status)
            return status

        transitioned = (not has_password) and (current_url != login_url)
        if transitioned and not login_detected:
            login_detected = True
            status = RecorderStatus(
                phase=PHASE_LOGIN_DETECTED,
                current_url=current_url,
                detail=(
                    "パスワード欄の消失とURL変化を検知しました"
                    "（保存するには「ログイン完了」を押してください）"
                ),
            )
            _write_status(status_file, status)
        elif not transitioned and login_detected:
            # ログイン画面へ戻った等、検知条件が崩れたら待機表示に戻す
            login_detected = False
            status = RecorderStatus(phase=PHASE_WAITING, current_url=current_url)
            _write_status(status_file, status)

        if clock() >= deadline:
            status = RecorderStatus(
                phase=PHASE_TIMEOUT,
                current_url=current_url,
                detail="時間切れです。もう一度お試しください",
            )
            _write_status(status_file, status)
            return status
        sleeper(poll_interval)


def _save_and_verify(
    context: Any,
    page: Any,
    login_url: str,
    auth_path: Path,
    status_file: Path | None,
    fallback_url: str,
    playwright: Any | None = None,
) -> RecorderStatus:
    """シグナル受領時の保存処理。保存後に verify_auth_state で検証する（AC-6）。"""
    try:
        current_url = page.url
    except Exception:  # noqa: BLE001
        current_url = fallback_url

    try:
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(auth_path))
    except Exception as exc:  # noqa: BLE001
        logger.error("セッション保存に失敗しました: %s", exc)
        if auth_path.exists():
            try:
                auth_path.unlink()
            except OSError:
                pass
        status = RecorderStatus(
            phase=PHASE_ERROR,
            current_url=current_url,
            detail=f"セッション保存に失敗しました: {exc}",
        )
        _write_status(status_file, status)
        return status

    if auth_path.exists():
        auth_path.chmod(0o600)
    logger.info("セッションを保存しました: %s", auth_path)

    verified = verify_auth_state(login_url, auth_path, playwright=playwright)
    detail = "保存しました" if verified else "保存しました（動作確認は未確認）"
    status = RecorderStatus(
        phase=PHASE_SAVED, current_url=current_url, detail=detail, verified=verified
    )
    _write_status(status_file, status)
    return status


def verify_auth_state(
    login_url: str, auth_path: Path, playwright: Any | None = None
) -> bool | None:
    """保存済み auth.json でログイン URL を headless 再訪し、detect_login_wall で検証する。

    到達失敗・判定不能は None（=未確認）。auto_login.py の PageAuthSignals 構築を踏襲する。
    playwright: 呼び出し元が既に sync_playwright() コンテキスト内にいる場合はその
    ドライバを渡す（同一スレッドで sync_playwright() を二重に開始できないため）。
    省略時はこの関数内で新規に開く（CLI から単体で呼ぶ場合）。
    """
    if not auth_path.exists():
        return None
    if playwright is not None:
        return _verify_with_driver(playwright, login_url, auth_path)
    try:
        with sync_playwright() as playwright_:
            return _verify_with_driver(playwright_, login_url, auth_path)
    except Exception as exc:  # noqa: BLE001  # ブラウザ起動失敗等も未確認扱い
        logger.warning("検証に失敗しました（未確認）: %s", exc)
        return None


def _verify_with_driver(playwright: Any, login_url: str, auth_path: Path) -> bool | None:
    """既存の Playwright ドライバでブラウザを1つ起動して検証する（verify_auth_state のコア）。"""
    try:
        browser = playwright.chromium.launch(headless=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("検証用ブラウザの起動に失敗しました（未確認）: %s", exc)
        return None
    try:
        context = browser.new_context(storage_state=str(auth_path))
        page = context.new_page()
        try:
            page.goto(login_url, wait_until="networkidle", timeout=VERIFY_TIMEOUT_MS)
        except Exception as exc:  # noqa: BLE001
            logger.warning("検証時のページ遷移に失敗しました（未確認）: %s", exc)
            return None
        has_password = bool(page.evaluate(_PASSWORD_FIELD_JS))
        verdict = detect_login_wall(
            PageAuthSignals(
                requested_url=login_url,
                final_url=page.url,
                status=200,
                has_password_field=has_password,
            )
        )
        return not verdict.is_login_required
    finally:
        _close_browser(browser)


def _write_status(status_file: Path | None, status: RecorderStatus) -> None:
    """status_file へ RecorderStatus を原子的に上書きする（.tmp → replace）。"""
    if status_file is None:
        return
    status_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = status_file.with_name(status_file.name + ".tmp")
    tmp_path.write_text(json.dumps(asdict(status), ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(status_file)


def _close_browser(browser: Browser) -> None:
    try:
        browser.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ブラウザ終了時にエラーが発生しました: %s", exc)


__all__ = [
    "PHASE_CLOSED",
    "PHASE_ERROR",
    "PHASE_LOGIN_DETECTED",
    "PHASE_SAVED",
    "PHASE_TIMEOUT",
    "PHASE_WAITING",
    "RecorderStatus",
    "record_auth_session",
    "verify_auth_state",
]
