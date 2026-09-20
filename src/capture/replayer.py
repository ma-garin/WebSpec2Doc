"""記録済みユーザーフローの再生（キャプチャ&リプレイ Phase 2: リプレイ）。

Chrome DevTools Recorder 互換の user-flow JSON（sessions/session_NNN.flow.json）を
Playwright sync API で再生し、各 step の成否・スクリーンショットを
replays/<replay_name>.json に保存する。LLM は使わず記録された selectors 候補を
そのまま順に試すだけ（evidence-only 原則: 推定・言い換えをしない）。
失敗した step があっても以降の step は試み続ける（回帰の全体像を優先する）。
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)

REPLAYS_DIR_NAME = "replays"
_MASK_VALUE = "***"
_NAME_ATTR_RE = re.compile(r"\[name=['\"]([^'\"]+)['\"]\]")


def replay_user_flow(
    flow: dict[str, Any],
    *,
    output_dir: Path,
    replay_name: str,
    headless: bool = True,
    auth_state: Path | None = None,
    base_url: str | None = None,
    step_timeout_ms: int = 10000,
) -> dict[str, Any]:
    """user-flow JSON を Playwright で再生し、結果を replays/<replay_name>.json に保存する。

    base_url を指定すると navigate の URL のホスト部だけを差し替える
    （記録時と別環境でのリプレイ）。失敗した step があっても続行する。
    """
    from playwright.sync_api import sync_playwright

    from crawler.page_crawler import BROWSER_LOCALE, USER_AGENT

    steps = list(flow.get("steps") or [])
    ws2d = flow.get("ws2d") or {}
    session = str(ws2d.get("session") or "")
    shots_dir = output_dir / REPLAYS_DIR_NAME / replay_name
    shots_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    passed = failed = skipped = 0
    started = datetime.now(UTC)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless, args=[f"--lang={BROWSER_LOCALE}"])
        try:
            context_kwargs: dict[str, Any] = {"user_agent": USER_AGENT, "locale": BROWSER_LOCALE}
            if auth_state is not None and auth_state.exists():
                context_kwargs["storage_state"] = str(auth_state)
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            page.set_default_timeout(step_timeout_ms)
            for order, step in enumerate(steps, start=1):
                step_result = _replay_step(
                    page, step, order, base_url, shots_dir, step_timeout_ms
                )
                results.append(step_result)
                status = step_result["status"]
                if status == "passed":
                    passed += 1
                elif status == "failed":
                    failed += 1
                else:
                    skipped += 1
        finally:
            browser.close()

    finished = datetime.now(UTC)
    result: dict[str, Any] = {
        "replay": replay_name,
        "session": session,
        "ran_at": started.isoformat(timespec="seconds"),
        "base_url": base_url,
        "summary": {
            "total": len(steps),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "duration_ms": int((finished - started).total_seconds() * 1000),
        },
        "steps": results,
    }
    replay_path = output_dir / REPLAYS_DIR_NAME / f"{replay_name}.json"
    replay_path.parent.mkdir(parents=True, exist_ok=True)
    replay_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def latest_session_flow(output_dir: Path) -> Path | None:
    """sessions/session_*.flow.json のうち番号最大（最新）のものを返す。無ければ None。"""
    from capture.session_recorder import SESSIONS_DIR_NAME

    sessions_dir = output_dir / SESSIONS_DIR_NAME
    candidates = sorted(sessions_dir.glob("session_*.flow.json"))
    return candidates[-1] if candidates else None


def _replay_step(
    page: Any,
    step: dict[str, Any],
    order: int,
    base_url: str | None,
    shots_dir: Path,
    timeout_ms: int,
) -> dict[str, Any]:
    """1 step を再生し、結果 dict を返す（例外は握って failed として続行する）。"""
    step_type = str(step.get("type") or "")
    ws2d = step.get("ws2d") or {}
    selectors = step.get("selectors") or []
    selector_desc = str(selectors[0][0]) if selectors and selectors[0] else ""
    status = "skipped"
    reason = ""
    error = ""
    start = time.monotonic()
    try:
        if step_type == "setViewport":
            page.set_viewport_size(
                {"width": int(step.get("width") or 1280), "height": int(step.get("height") or 800)}
            )
            status = "passed"
        elif step_type == "navigate":
            url = _rebase_url(str(step.get("url") or ""), base_url)
            page.goto(url, timeout=timeout_ms)
            _warn_if_path_mismatch(page, step)
            status = "passed"
        elif step_type == "click":
            locator, selector_desc = _resolve_locator(page, selectors)
            if locator is None:
                status, reason = "failed", "selector_not_found"
            else:
                locator.click(timeout=timeout_ms)
                status = "passed"
        elif step_type == "change":
            value, skip_reason = _resolve_change_value(step, ws2d)
            if skip_reason:
                status, reason = "skipped", skip_reason
            else:
                locator, selector_desc = _resolve_locator(page, selectors)
                if locator is None:
                    status, reason = "failed", "selector_not_found"
                else:
                    _apply_change(locator, value, str(ws2d.get("input_type") or ""), timeout_ms)
                    status = "passed"
        elif step_type in {"keyDown", "keyUp"}:
            if step_type == "keyDown":
                page.keyboard.press(str(step.get("key") or ""))
            status = "passed"
        elif step_type == "hover":
            locator, selector_desc = _resolve_locator(page, selectors)
            if locator is None:
                status, reason = "failed", "selector_not_found"
            else:
                locator.hover(timeout=timeout_ms)
                status = "passed"
        elif step_type == "waitForElement":
            if not selector_desc:
                status, reason = "skipped", "no_selector"
            else:
                locator = _selector_to_locator(page, selector_desc)
                if locator is None:
                    status, reason = "failed", "selector_not_found"
                else:
                    locator.first.wait_for(timeout=timeout_ms, state="visible")
                    status = "passed"
        else:
            status, reason = "skipped", f"unsupported_type:{step_type}"
    except Exception as exc:  # noqa: BLE001  # 失敗しても以降の step を続行する
        status = "failed"
        error = str(exc)

    screenshot_rel = _capture_step_screenshot(page, shots_dir, order)
    duration_ms = int((time.monotonic() - start) * 1000)
    return {
        "order": order,
        "type": step_type,
        "selector": selector_desc,
        "status": status,
        "reason": reason,
        "error": error,
        "screenshot": screenshot_rel,
        "duration_ms": duration_ms,
        "url_after": _safe_url(page),
    }


def _capture_step_screenshot(page: Any, shots_dir: Path, order: int) -> str:
    try:
        shot_path = shots_dir / f"step_{order:04d}.png"
        page.screenshot(path=str(shot_path))
        return str(shot_path.relative_to(shots_dir.parent.parent))
    except Exception:  # noqa: BLE001  # スクショ失敗はリプレイを止めない
        return ""


def _safe_url(page: Any) -> str:
    try:
        return str(page.url)
    except Exception:  # noqa: BLE001
        return ""


def _rebase_url(url: str, base_url: str | None) -> str:
    """base_url があれば url のホスト部だけを差し替える（別環境でのリプレイ用）。"""
    if not base_url or not url:
        return url
    parsed = urlparse(url)
    base = urlparse(base_url)
    if not base.scheme or not base.netloc:
        return url
    return urlunparse((base.scheme, base.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))


def _warn_if_path_mismatch(page: Any, step: dict[str, Any]) -> None:
    for event in step.get("assertedEvents") or []:
        if isinstance(event, dict) and event.get("type") == "navigation":
            expected_path = urlparse(str(event.get("url") or "")).path
            if expected_path and urlparse(_safe_url(page)).path != expected_path:
                logger.warning(
                    "navigate 後の path が一致しません（記録時と異なる可能性）: %s != %s",
                    _safe_url(page),
                    expected_path,
                )
            return


def _resolve_locator(page: Any, selectors: list[list[str]]) -> tuple[Any, str]:
    """候補 selectors を順に試し、count()>0 かつ visible な最初の locator を返す。"""
    for candidate in selectors or []:
        if not candidate:
            continue
        value = str(candidate[0])
        try:
            locator = _selector_to_locator(page, value)
            if locator is not None and locator.count() > 0 and locator.first.is_visible():
                return locator.first, value
        except Exception:  # noqa: BLE001  # 候補が不正でも次を試す
            continue
    return None, ""


def _selector_to_locator(page: Any, value: str) -> Any:
    if value.startswith("aria/"):
        name = value[len("aria/") :]
        for factory in (
            lambda: page.get_by_label(name),
            lambda: page.get_by_text(name, exact=True),
            lambda: page.get_by_title(name),
        ):
            try:
                locator = factory()
                if locator.count() > 0:
                    return locator
            except Exception:  # noqa: BLE001
                continue
        return None
    if value.startswith("xpath/"):
        return page.locator("xpath=" + value[len("xpath/") :])
    if value.startswith("text/"):
        return page.get_by_text(value[len("text/") :], exact=False)
    return page.locator(value)


def _resolve_change_value(step: dict[str, Any], ws2d: dict[str, Any]) -> tuple[str, str]:
    """change の入力値を決める。masked な value は WS2D_REPLAY_SECRET_<NAME> から補う。

    戻り値は (value, skip_reason)。skip_reason が空でなければ status="skipped" とする。
    """
    value = step.get("value")
    value = "" if value is None else str(value)
    if bool(ws2d.get("masked")) and value == _MASK_VALUE:
        env_name = _secret_env_name(step.get("selectors") or [])
        secret = os.environ.get(f"WS2D_REPLAY_SECRET_{env_name}") if env_name else None
        if not secret:
            return "", "secret_missing"
        return secret, ""
    return value, ""


def _secret_env_name(selectors: list[list[str]]) -> str:
    """selectors 候補から id/name を拾い、環境変数名の suffix（大文字）にする。"""
    for candidate in selectors or []:
        if not candidate:
            continue
        value = str(candidate[0])
        if value.startswith("#"):
            return value[1:].upper()
        match = _NAME_ATTR_RE.search(value)
        if match:
            return match.group(1).upper()
    return ""


def _apply_change(locator: Any, value: str, input_type: str, timeout_ms: int) -> None:
    if input_type == "checkbox":
        if value.strip().lower() in {"true", "on", "1", "checked"}:
            locator.check(timeout=timeout_ms)
        else:
            locator.uncheck(timeout=timeout_ms)
    elif input_type in {"select", "radio"}:
        try:
            locator.select_option(value, timeout=timeout_ms)
        except Exception:  # noqa: BLE001  # radio 等は select_option が使えないため check にフォールバック
            locator.check(timeout=timeout_ms)
    else:
        locator.fill(value, timeout=timeout_ms)
