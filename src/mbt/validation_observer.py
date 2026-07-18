"""送信せずにクライアント側バリデーションだけを観測する。"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any, Protocol


class ValidationPage(Protocol):
    """ブラウザ外部境界。副作用を起こさない操作だけを公開する。"""

    blocked_request_count: int
    blocked_destructive_request_count: int
    observation_active: bool

    def goto(self, url: str) -> None: ...

    def fill(self, locator: str, value: str) -> None: ...

    def blur(self, locator: str) -> None: ...

    def validation_state(self, locator: str) -> dict[str, object]: ...


SessionFactory = Callable[[Path | None], AbstractContextManager[ValidationPage]]


def run_validation_observation(
    cases: list[dict[str, Any]],
    output_dir: Path,
    auth_path: Path | None = None,
    *,
    session_factory: SessionFactory | None = None,
) -> Path:
    """headlessブラウザ境界を開き、観測結果を必ずJSONへ保存する。"""
    factory = session_factory or playwright_validation_session
    try:
        with factory(auth_path) as page:
            observations = observe_validation_cases(cases, page)
    except Exception as exc:
        observations = [_runtime_failure(case, exc) for case in cases]
    return save_validation_observations(observations, output_dir)


class PlaywrightValidationPage:
    """Playwright Pageを非送信操作だけへ狭めるアダプタ。"""

    def __init__(self, page: Any) -> None:
        self._page = page
        self.blocked_request_count = 0
        self.blocked_destructive_request_count = 0
        self.observation_active = False

    def goto(self, url: str) -> None:
        self.observation_active = False
        self._page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    def fill(self, locator: str, value: str) -> None:
        target = self._page.locator(locator)
        # SPAが安全なGET/WSでフォームを遅延描画できるよう、対象の準備完了まで待つ。
        target.wait_for(state="attached", timeout=30_000)
        # 値をDOMへ渡す直前からはGETを含む全HTTP送信を遮断する。
        self.observation_active = True
        target.fill(value)

    def blur(self, locator: str) -> None:
        self._page.locator(locator).evaluate("element => element.blur()")

    def validation_state(self, locator: str) -> dict[str, object]:
        result = self._page.locator(locator).evaluate(
            """element => ({
                observed_value: String(element.value || ''),
                accepted: element.checkValidity(),
                validation_message: element.validationMessage || '',
                input_length: String(element.value || '').length,
            })"""
        )
        return result if isinstance(result, dict) else {}


def guard_validation_request(route: Any, page: ValidationPage) -> None:
    """初期表示の安全な読取通信以外を遮断し、入力値の外部送信を防ぐ。"""
    safe_initial_method = str(route.request.method).upper() in {"GET", "HEAD", "OPTIONS"}
    if page.observation_active or not safe_initial_method:
        page.blocked_request_count += 1
        if not safe_initial_method:
            page.blocked_destructive_request_count += 1
        route.abort("blockedbyclient")
    else:
        route.continue_()


def guard_validation_websocket(websocket_route: Any, page: ValidationPage) -> None:
    """フォーム準備前は中継し、入力開始後のクライアント送信だけを遮断する。"""
    server_route = websocket_route.connect_to_server()

    def forward_before_observation(message: str | bytes) -> None:
        if page.observation_active:
            page.blocked_request_count += 1
            return
        server_route.send(message)

    websocket_route.on_message(forward_before_observation)


@contextmanager
def playwright_validation_session(auth_path: Path | None) -> Iterator[ValidationPage]:
    """破壊的HTTPメソッドを遮断したheadless Chromiumセッション。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        # Service Worker 経由の通信は context.route で捕捉できないため無効化し、
        # 入力・blurで発火した破壊的通信を必ず下のルートガードへ通す。
        context = None
        try:
            context_options: dict[str, Any] = {"service_workers": "block"}
            if auth_path is not None and auth_path.is_file():
                context_options["storage_state"] = str(auth_path)
            context = browser.new_context(**context_options)
            page_adapter = PlaywrightValidationPage(context.new_page())
            context.route("**/*", lambda route: guard_validation_request(route, page_adapter))
            context.route_web_socket(
                "**/*", lambda route: guard_validation_websocket(route, page_adapter)
            )
            yield page_adapter
        finally:
            try:
                if context is not None:
                    context.close()
            finally:
                browser.close()


def save_validation_observations(observations: list[dict[str, Any]], output_dir: Path) -> Path:
    """非送信の観測結果と主張境界をJSONへ保存する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "validation_observations.json"
    statuses = [str(item.get("status", "")) for item in observations]
    blocked = max((int(item.get("blocked_request_count", 0)) for item in observations), default=0)
    destructive = max(
        (int(item.get("blocked_destructive_request_count", 0)) for item in observations),
        default=0,
    )
    payload = {
        "meta": {
            "claim_scope": "client_observed_without_submit",
            "observation_count": len(observations),
            "observed": statuses.count("observed"),
            "skipped": statuses.count("skipped"),
            "failed": statuses.count("failed"),
            "blocked_outbound_requests": blocked,
            "blocked_destructive_requests": destructive,
        },
        "observations": observations,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _runtime_failure(case: dict[str, Any], exc: Exception) -> dict[str, Any]:
    return {
        "case_id": str(case.get("case_id", "")),
        "page_id": str(case.get("page_id", "")),
        "field_name": str(case.get("field_name", "")),
        "expected_client_behavior": str(case.get("expected_client_behavior", "")),
        "attempted_value": str(case.get("value", "")),
        "observed_value": "",
        "accepted": None,
        "validation_message": "",
        "input_length": 0,
        "blocked_request_count": 0,
        "blocked_destructive_request_count": 0,
        "source_constraint": str(case.get("source_constraint", "")),
        "claim_scope": "client_observed_without_submit",
        "status": "failed",
        "error": "validation_runtime_unavailable",
        "error_type": type(exc).__name__,
    }


def observe_validation_cases(
    cases: list[dict[str, Any]], page: ValidationPage
) -> list[dict[str, Any]]:
    """許可された4操作だけで各入力値のクライアント挙動を観測する。"""
    observations: list[dict[str, Any]] = []
    for case in cases:
        url = str(case.get("page_url", ""))
        locator = str(case.get("locator", ""))
        if not url or not locator:
            observations.append(
                {
                    "case_id": str(case.get("case_id", "")),
                    "page_id": str(case.get("page_id", "")),
                    "field_name": str(case.get("field_name", "")),
                    "expected_client_behavior": str(case.get("expected_client_behavior", "")),
                    "attempted_value": str(case.get("value", "")),
                    "observed_value": "",
                    "accepted": None,
                    "validation_message": "",
                    "input_length": 0,
                    "blocked_request_count": page.blocked_request_count,
                    "blocked_destructive_request_count": page.blocked_destructive_request_count,
                    "source_constraint": str(case.get("source_constraint", "")),
                    "claim_scope": "client_observed_without_submit",
                    "status": "skipped",
                    "error": "missing_page_url_or_locator",
                }
            )
            continue
        value = str(case.get("value", ""))
        try:
            page.goto(url)
            page.fill(locator, value)
            page.blur(locator)
            state = page.validation_state(locator)
        except Exception as exc:
            observations.append(
                {
                    "case_id": str(case.get("case_id", "")),
                    "page_id": str(case.get("page_id", "")),
                    "field_name": str(case.get("field_name", "")),
                    "expected_client_behavior": str(case.get("expected_client_behavior", "")),
                    "attempted_value": value,
                    "observed_value": "",
                    "accepted": None,
                    "validation_message": "",
                    "input_length": 0,
                    "blocked_request_count": page.blocked_request_count,
                    "blocked_destructive_request_count": page.blocked_destructive_request_count,
                    "source_constraint": str(case.get("source_constraint", "")),
                    "claim_scope": "client_observed_without_submit",
                    "status": "failed",
                    "error": "browser_observation_failed",
                    "error_type": type(exc).__name__,
                }
            )
            continue
        raw_input_length = state.get("input_length", len(value))
        try:
            input_length = int(str(raw_input_length))
        except ValueError:
            input_length = len(value)
        observations.append(
            {
                "case_id": str(case.get("case_id", "")),
                "page_id": str(case.get("page_id", "")),
                "field_name": str(case.get("field_name", "")),
                "expected_client_behavior": str(case.get("expected_client_behavior", "")),
                "attempted_value": value,
                "observed_value": str(state.get("observed_value", "")),
                "accepted": bool(state.get("accepted", False)),
                "validation_message": str(state.get("validation_message", "")),
                "input_length": input_length,
                "blocked_request_count": page.blocked_request_count,
                "blocked_destructive_request_count": page.blocked_destructive_request_count,
                "source_constraint": str(case.get("source_constraint", "")),
                "claim_scope": "client_observed_without_submit",
                "status": "observed",
            }
        )
    return observations
