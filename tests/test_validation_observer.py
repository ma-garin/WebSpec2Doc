"""第3弾 S3: 送信しないクライアントバリデーション観測の公開契約。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mbt.validation_observer import (
    PlaywrightValidationPage,
    guard_validation_request,
    guard_validation_websocket,
    observe_validation_cases,
    playwright_validation_session,
    run_validation_observation,
    save_validation_observations,
)


class FakeValidationPage:
    """Playwright境界の偽物。許可操作だけを記録する。"""

    def __init__(self) -> None:
        self.operations: list[tuple[str, str, str]] = []
        self.blocked_request_count = 0
        self.blocked_destructive_request_count = 0
        self.observation_active = False

    def goto(self, url: str) -> None:
        self.operations.append(("goto", url, ""))

    def fill(self, locator: str, value: str) -> None:
        self.operations.append(("fill", locator, value))

    def blur(self, locator: str) -> None:
        self.operations.append(("blur", locator, ""))

    def validation_state(self, locator: str) -> dict[str, object]:
        self.operations.append(("validation_state", locator, ""))
        return {
            "observed_value": "あああ",
            "accepted": False,
            "validation_message": "3文字以内で入力してください",
            "input_length": 4,
        }


def test_playwright_adapter_records_dom_value_and_activates_network_block() -> None:
    raw_page = MagicMock()
    raw_page.locator.return_value.evaluate.return_value = {
        "observed_value": "normalized",
        "accepted": True,
        "validation_message": "",
        "input_length": 10,
    }
    page = PlaywrightValidationPage(raw_page)

    page.goto("https://example.com/form")
    assert page.observation_active is False
    page.fill("#field", "attempted")
    state = page.validation_state("#field")

    assert page.observation_active is True
    assert state["observed_value"] == "normalized"


def test_observe_validation_uses_only_navigation_fill_blur_and_read_operations() -> None:
    page = FakeValidationPage()
    cases = [
        {
            "case_id": "TD-0001",
            "page_id": "P001",
            "page_url": "https://example.com/contact",
            "field_name": "message",
            "locator": "#message",
            "value": "ああああ",
            "expected_client_behavior": "reject_candidate",
            "source_constraint": "maxlength=3",
        }
    ]

    observations = observe_validation_cases(cases, page)

    assert page.operations == [
        ("goto", "https://example.com/contact", ""),
        ("fill", "#message", "ああああ"),
        ("blur", "#message", ""),
        ("validation_state", "#message", ""),
    ]
    assert observations == [
        {
            "case_id": "TD-0001",
            "page_id": "P001",
            "field_name": "message",
            "expected_client_behavior": "reject_candidate",
            "attempted_value": "ああああ",
            "observed_value": "あああ",
            "accepted": False,
            "validation_message": "3文字以内で入力してください",
            "input_length": 4,
            "blocked_request_count": 0,
            "blocked_destructive_request_count": 0,
            "source_constraint": "maxlength=3",
            "claim_scope": "client_observed_without_submit",
            "status": "observed",
        }
    ]


def test_missing_measured_locator_is_recorded_as_skipped_without_browser_operation() -> None:
    page = FakeValidationPage()
    cases = [
        {
            "case_id": "TD-0002",
            "page_id": "P002",
            "page_url": "https://example.com/profile",
            "field_name": "nickname",
            "locator": "",
            "value": "あ",
            "expected_client_behavior": "accept_candidate",
            "source_constraint": "type=text",
        }
    ]

    observations = observe_validation_cases(cases, page)

    assert page.operations == []
    assert observations[0]["status"] == "skipped"
    assert observations[0]["error"] == "missing_page_url_or_locator"
    assert observations[0]["accepted"] is None
    assert observations[0]["claim_scope"] == "client_observed_without_submit"


def test_browser_failure_is_sanitized_and_next_case_can_continue() -> None:
    class FailingPage(FakeValidationPage):
        def fill(self, locator: str, value: str) -> None:
            raise RuntimeError("secret-token must not escape")

    page = FailingPage()
    cases = [
        {
            "case_id": "TD-0003",
            "page_id": "P003",
            "page_url": "https://example.com/failing",
            "field_name": "code",
            "locator": "#code",
            "value": "123",
            "expected_client_behavior": "accept_candidate",
            "source_constraint": "maxlength=3",
        }
    ]

    observations = observe_validation_cases(cases, page)

    assert observations[0]["status"] == "failed"
    assert observations[0]["error"] == "browser_observation_failed"
    assert observations[0]["error_type"] == "RuntimeError"
    assert "secret-token" not in str(observations[0])


def test_save_observations_records_scope_counts_and_blocked_requests(tmp_path: Path) -> None:
    observations = [
        {
            "case_id": "TD-1",
            "status": "observed",
            "blocked_request_count": 0,
            "blocked_destructive_request_count": 0,
            "claim_scope": "client_observed_without_submit",
        },
        {
            "case_id": "TD-2",
            "status": "failed",
            "blocked_request_count": 1,
            "blocked_destructive_request_count": 1,
            "claim_scope": "client_observed_without_submit",
        },
    ]

    path = save_validation_observations(observations, tmp_path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["meta"] == {
        "claim_scope": "client_observed_without_submit",
        "observation_count": 2,
        "observed": 1,
        "skipped": 0,
        "failed": 1,
        "blocked_outbound_requests": 1,
        "blocked_destructive_requests": 1,
    }
    assert payload["observations"] == observations


def test_runtime_uses_injected_browser_boundary_and_persists_result(tmp_path: Path) -> None:
    page = FakeValidationPage()
    cases = [
        {
            "case_id": "TD-0004",
            "page_id": "P004",
            "page_url": "https://example.com/input",
            "field_name": "name",
            "locator": "#name",
            "value": "あ",
            "expected_client_behavior": "accept_candidate",
            "source_constraint": "type=text",
        }
    ]

    @contextmanager
    def fake_session(_auth_path: Path | None) -> Iterator[FakeValidationPage]:
        yield page

    path = run_validation_observation(cases, tmp_path, session_factory=fake_session)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["meta"]["observed"] == 1
    assert payload["observations"][0]["case_id"] == "TD-0004"


def test_network_guard_allows_initial_get_then_blocks_all_observation_traffic() -> None:
    class Request:
        def __init__(self, method: str) -> None:
            self.method = method

    class Route:
        def __init__(self, method: str) -> None:
            self.request = Request(method)
            self.actions: list[str] = []

        def abort(self, _reason: str) -> None:
            self.actions.append("abort")

        def continue_(self) -> None:
            self.actions.append("continue")

    page = FakeValidationPage()
    post_route = Route("POST")
    get_route = Route("GET")

    guard_validation_request(post_route, page)
    guard_validation_request(get_route, page)

    assert post_route.actions == ["abort"]
    assert get_route.actions == ["continue"]
    assert page.blocked_request_count == 1
    assert page.blocked_destructive_request_count == 1

    page.observation_active = True
    observed_get = Route("GET")
    guard_validation_request(observed_get, page)
    assert observed_get.actions == ["abort"]
    assert page.blocked_request_count == 2
    assert page.blocked_destructive_request_count == 1


def test_websocket_guard_forwards_before_input_and_blocks_after_input() -> None:
    class ServerRoute:
        def __init__(self) -> None:
            self.sent: list[str | bytes] = []

        def send(self, message: str | bytes) -> None:
            self.sent.append(message)

    class WebSocketRoute:
        def __init__(self) -> None:
            self.server = ServerRoute()
            self.handler = None

        def connect_to_server(self) -> ServerRoute:
            return self.server

        def on_message(self, handler) -> None:
            self.handler = handler

    page = FakeValidationPage()
    route = WebSocketRoute()

    guard_validation_websocket(route, page)
    route.handler("initialization")
    page.observation_active = True
    route.handler("input value")

    assert route.server.sent == ["initialization"]
    assert page.blocked_request_count == 1
    assert page.blocked_destructive_request_count == 0


def test_session_closes_browser_when_context_creation_fails() -> None:
    manager = MagicMock()
    playwright = manager.__enter__.return_value
    browser = playwright.chromium.launch.return_value
    browser.new_context.side_effect = RuntimeError("context failed")

    with (
        patch("playwright.sync_api.sync_playwright", return_value=manager),
        pytest.raises(RuntimeError, match="context failed"),
        playwright_validation_session(None),
    ):
        pass

    browser.close.assert_called_once_with()
