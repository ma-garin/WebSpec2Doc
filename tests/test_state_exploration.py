"""状態ベース探索（Layer 2）のユニット・受け入れテスト。

モーダル等の画面状態検出・破壊的操作の遮断・バリデーション実測・
状態ベース fingerprint・SPA 遷移捕捉を検証する。
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from analyzer.canonicalizer import (
    FINGERPRINT_VERSION_STATE,
    FINGERPRINT_VERSION_STRUCTURE,
    group_canonical_screens,
    screen_fingerprint,
)
from analyzer.html_analyzer import analyze_pages
from analyzer.test_conditions import attach_observed_validation, derive_conditions_with_evidence
from crawler.action_explorer import (
    DEFAULT_MAX_ACTIONS,
    MAX_ACTIONS_ENV,
    explore_page_actions,
    max_actions_from_env,
    measure_required_validation,
)
from crawler.network_interceptor import (
    ALLOW_MUTATION_ENV,
    MutationBlocker,
    mutations_allowed,
)
from crawler.page_crawler import (
    FieldData,
    FormData,
    PageData,
    SpaTransition,
    ValidationObservation,
)
from crawler.spa_monitor import SpaTransitionMonitor
from graph.transition_graph import STATE_NODE_SEPARATOR, _build_graph_from_pages

_PLAIN_HTML = "<html><body><main><button id='open'>開く</button></main></body></html>"
_MODAL_HTML = (
    "<html><body><main><button id='open'>開く</button>"
    '<div role="dialog" id="confirm-modal">確認</div></main></body></html>'
)


class _FakeHandle:
    """クリックで DOM を変化させるフェイク要素。"""

    def __init__(self, page: _FakePage, descriptor: str, after_html: str) -> None:
        self._page = page
        self._descriptor = descriptor
        self._after_html = after_html

    def evaluate(self, _js: str) -> str:
        return self._descriptor

    def click(self, timeout: int | None = None) -> None:
        self._page.html = self._after_html


class _FakeKeyboard:
    def press(self, _key: str) -> None:
        pass


class _FakePage:
    """Playwright Page の必要最小限を模したフェイク。"""

    def __init__(self, html: str, handles_factory: Any = None) -> None:
        self.html = html
        self.url = "https://example.com/"
        self.keyboard = _FakeKeyboard()
        self._handles_factory = handles_factory
        self.routed: list[str] = []
        self.unrouted: list[str] = []
        self.clicked: list[str] = []
        self.evaluate_result: Any = []

    def query_selector_all(self, _selector: str) -> list[Any]:
        return self._handles_factory(self) if self._handles_factory else []

    def content(self) -> str:
        return self.html

    def wait_for_timeout(self, _ms: int) -> None:
        pass

    def route(self, pattern: str, _handler: Any) -> None:
        self.routed.append(pattern)

    def unroute(self, pattern: str, _handler: Any = None) -> None:
        self.unrouted.append(pattern)

    def click(self, selector: str, timeout: int | None = None) -> None:
        self.clicked.append(selector)

    def evaluate(self, _js: str) -> Any:
        return self.evaluate_result


# ---------- 受け入れ条件: モーダル状態の検出 ----------


class TestModalStateDetection:
    def test_modal_detected_as_separate_state(self) -> None:
        """モーダルを持つフィクスチャで、モーダル状態が別画面状態として検出される。"""
        page = _FakePage(
            _PLAIN_HTML,
            handles_factory=lambda p: [_FakeHandle(p, "#open", _MODAL_HTML)],
        )
        states = explore_page_actions(page, max_actions=5)
        assert len(states) == 1
        assert states[0].kind == "modal"
        assert states[0].trigger_selector == "#open"
        assert states[0].state_id != "default"

    def test_no_dom_change_records_no_state(self) -> None:
        page = _FakePage(
            _PLAIN_HTML,
            handles_factory=lambda p: [_FakeHandle(p, "#open", _PLAIN_HTML)],
        )
        assert explore_page_actions(page, max_actions=5) == ()

    def test_max_actions_zero_disables_exploration(self) -> None:
        page = _FakePage(
            _PLAIN_HTML,
            handles_factory=lambda p: [_FakeHandle(p, "#open", _MODAL_HTML)],
        )
        assert explore_page_actions(page, max_actions=0) == ()

    def test_max_actions_limits_attempts(self) -> None:
        clicks: list[str] = []

        class _CountingHandle(_FakeHandle):
            def click(self, timeout: int | None = None) -> None:
                clicks.append(self._descriptor)

        page = _FakePage(
            _PLAIN_HTML,
            handles_factory=lambda p: [
                _CountingHandle(p, f"#b{i}", _PLAIN_HTML) for i in range(20)
            ],
        )
        explore_page_actions(page, max_actions=3)
        assert len(clicks) == 3

    def test_max_actions_env_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(MAX_ACTIONS_ENV, raising=False)
        assert max_actions_from_env() == DEFAULT_MAX_ACTIONS
        monkeypatch.setenv(MAX_ACTIONS_ENV, "5")
        assert max_actions_from_env() == 5


# ---------- 受け入れ条件: 破壊的操作の遮断 ----------


def _fake_route(method: str, url: str = "https://example.com/api") -> MagicMock:
    route = MagicMock()
    route.request.method = method
    route.request.url = url
    return route


class TestMutationBlocker:
    def test_post_blocked_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """POST 遮断下で dry-run 送信してもサーバへリクエストが到達しない。"""
        monkeypatch.delenv(ALLOW_MUTATION_ENV, raising=False)
        blocker = MutationBlocker()
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            route = _fake_route(method)
            blocker.handle_route(route)
            route.abort.assert_called_once()
            route.continue_.assert_not_called()
        assert len(blocker.blocked) == 4

    def test_get_passes_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ALLOW_MUTATION_ENV, raising=False)
        blocker = MutationBlocker()
        route = _fake_route("GET")
        blocker.handle_route(route)
        route.continue_.assert_called_once()
        route.abort.assert_not_called()

    def test_env_allows_mutation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ALLOW_MUTATION_ENV, "1")
        assert mutations_allowed() is True
        blocker = MutationBlocker()
        route = _fake_route("POST")
        blocker.handle_route(route)
        route.continue_.assert_called_once()
        route.abort.assert_not_called()

    def test_mutation_allowed_recorded_in_audit_log(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from contextlib import contextmanager
        from unittest.mock import patch
        from urllib.robotparser import RobotFileParser

        import crawler.page_crawler as pc

        monkeypatch.setenv(ALLOW_MUTATION_ENV, "1")
        robots = RobotFileParser()
        robots.allow_all = True

        @contextmanager
        def _browser(_auth: Any):
            yield MagicMock()

        with (
            patch.object(pc, "_browser_page", _browser),
            patch.object(pc, "_load_robots_parser", return_value=robots),
            patch.object(pc, "_crawl_page_with_id", return_value=None),
            patch.object(pc.time, "sleep"),
        ):
            pc.crawl_urls(["https://example.com/"], output_dir=tmp_path)
        record = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()[0])
        assert record["mutations_allowed"] is True


# ---------- 受け入れ条件: バリデーション実測の転記 ----------


_REQUIRED_MESSAGE = "このフィールドを入力してください。"


class TestValidationMeasurement:
    def _form(self) -> FormData:
        field = FieldData(field_type="email", name="email", placeholder="", required=True)
        return FormData(action="/send", method="post", fields=(field,))

    def test_dry_run_blocks_requests_and_collects_messages(self) -> None:
        page = _FakePage(_PLAIN_HTML)
        page.evaluate_result = [
            {"name": "email", "message": _REQUIRED_MESSAGE, "selector": "[name='email']"}
        ]
        observations = measure_required_validation(page, (self._form(),))
        # 全リクエスト遮断（route 登録）下で送信し、解除されている
        assert page.routed == ["**/*"]
        assert page.unrouted == ["**/*"]
        assert page.clicked == ["form[action='/send'] [type=submit]"]
        assert len(observations) == 1
        assert observations[0].field_name == "email"
        assert observations[0].message == _REQUIRED_MESSAGE
        assert observations[0].confidence == 1.0
        assert observations[0].evidence is not None
        assert observations[0].evidence.selector == "[name='email']"

    def test_form_without_required_fields_is_skipped(self) -> None:
        page = _FakePage(_PLAIN_HTML)
        field = FieldData(field_type="text", name="q", placeholder="", required=False)
        form = FormData(action="/search", method="get", fields=(field,))
        assert measure_required_validation(page, (form,)) == ()
        assert page.routed == []

    def test_observed_message_transcribed_to_test_condition(self) -> None:
        """必須未入力時のバリデーションメッセージが期待結果（実測）に転記される。"""
        field = FieldData(field_type="email", name="email", placeholder="", required=True)
        observation = ValidationObservation(
            field_name="email",
            message=_REQUIRED_MESSAGE,
            evidence=None,
            confidence=1.0,
        )
        conditions = attach_observed_validation(
            derive_conditions_with_evidence(field), field, [observation]
        )
        required_condition = next(c for c in conditions if "必須チェック" in c.description)
        assert required_condition.observed_result == _REQUIRED_MESSAGE
        assert required_condition.confidence == 1.0

    def test_observed_message_appears_in_json_report(self) -> None:
        from generator.json_reporter import generate_json_report
        from graph.transition_graph import build_graph

        field = FieldData(field_type="email", name="email", placeholder="", required=True)
        form = FormData(action="/send", method="post", fields=(field,))
        page = PageData(
            url="https://example.com/contact",
            title="お問い合わせ",
            headings=(),
            links=(),
            forms=(form,),
            screenshot_path=None,
            validation_observations=(
                ValidationObservation(field_name="email", message=_REQUIRED_MESSAGE),
            ),
        )
        analyzed = analyze_pages([page])
        report = json.loads(generate_json_report(analyzed, build_graph(analyzed), page.url))
        details = report["screens"][0]["forms"][0]["fields"][0]["test_conditions_detail"]
        required_detail = next(d for d in details if "必須チェック" in d["description"])
        assert required_detail["observed_result"] == _REQUIRED_MESSAGE
        assert required_detail["confidence"] == 1.0


# ---------- 受け入れ条件: 状態ベース fingerprint と後方互換 ----------


def _page_with_state(url: str, state_id: str) -> PageData:
    return PageData(
        url=url,
        title="Page",
        headings=(),
        links=(),
        forms=(),
        screenshot_path=None,
        state_id=state_id,
    )


class TestStateBasedFingerprint:
    def test_different_states_get_different_fingerprints(self) -> None:
        pages = analyze_pages(
            [
                _page_with_state("https://example.com/app", "default"),
                _page_with_state("https://example.com/app", "modal123"),
            ]
        )
        fp_default = screen_fingerprint(pages[0], FINGERPRINT_VERSION_STATE)
        fp_modal = screen_fingerprint(pages[1], FINGERPRINT_VERSION_STATE)
        assert fp_default != fp_modal

    def test_v1_ignores_state(self) -> None:
        pages = analyze_pages(
            [
                _page_with_state("https://example.com/app", "default"),
                _page_with_state("https://example.com/app", "modal123"),
            ]
        )
        fp_a = screen_fingerprint(pages[0], FINGERPRINT_VERSION_STRUCTURE)
        fp_b = screen_fingerprint(pages[1], FINGERPRINT_VERSION_STRUCTURE)
        assert fp_a == fp_b

    def test_modal_state_grouped_as_separate_screen(self) -> None:
        from analyzer.html_analyzer import AnalyzedPage

        default_page = _page_with_state("https://example.com/app", "default")
        modal_page = _page_with_state("https://example.com/app", "modal123")
        pages = [
            AnalyzedPage(page_id="P001", page_data=default_page, buttons=(), nav_elements=()),
            AnalyzedPage(page_id="P002", page_data=modal_page, buttons=(), nav_elements=()),
        ]
        grouped = group_canonical_screens(pages)
        assert grouped["P001"].canonical_key != grouped["P002"].canonical_key
        assert grouped["P001"].fingerprint_version == FINGERPRINT_VERSION_STATE

    def test_v1_snapshot_diff_backward_compatible(self, tmp_path: Any) -> None:
        """fingerprint v1 時代のスナップショット（state_id なし）との diff が破綻しない。"""
        from diff.differ import compute_diff
        from diff.snapshot import load_snapshot

        old_payload = [
            {
                "url": "https://example.com/",
                "title": "Home",
                "headings": [],
                "links": [],
                "forms": [
                    {
                        "action": "/send",
                        "method": "post",
                        "fields": [
                            {
                                "field_type": "email",
                                "name": "email",
                                "placeholder": "",
                                "required": True,
                            }
                        ],
                    }
                ],
                "screenshot_path": None,
            }
        ]
        path = tmp_path / "v1-snapshot.json"
        path.write_text(json.dumps(old_payload), encoding="utf-8")
        old_pages = load_snapshot(path)
        assert old_pages[0].state_id == "default"
        assert old_pages[0].page_states == ()

        new_page = PageData(
            url="https://example.com/",
            title="Home",
            headings=(),
            links=(),
            forms=old_pages[0].forms,
            screenshot_path=None,
            state_id="abc123",
        )
        diff = compute_diff(old_pages, [new_page])
        # フィールドは同一なので破壊的変更は検出されない
        assert diff.field_changes == ()
        assert diff.added_pages == ()
        assert diff.removed_pages == ()


# ---------- SPA 遷移の捕捉 ----------


class TestSpaTransitions:
    def test_collect_parses_recorded_transitions(self) -> None:
        page = _FakePage(_PLAIN_HTML)
        page.evaluate_result = [
            {
                "kind": "pushstate",
                "from": "https://example.com/",
                "to": "https://example.com/detail",
            },
            {
                "kind": "hashchange",
                "from": "https://example.com/detail",
                "to": "https://example.com/detail#tab2",
            },
            {"kind": "invalid-kind", "from": "x", "to": "y"},
            "not-a-dict",
        ]
        transitions = SpaTransitionMonitor().collect(page)
        assert len(transitions) == 2
        assert transitions[0].kind == "pushstate"
        assert transitions[1].kind == "hashchange"

    def test_collect_handles_non_list_result(self) -> None:
        page = _FakePage(_PLAIN_HTML)
        page.evaluate_result = None
        assert SpaTransitionMonitor().collect(page) == ()

    def test_spa_transition_becomes_graph_edge(self) -> None:
        page_a = PageData(
            url="https://example.com/",
            title="Home",
            headings=(),
            links=(),
            forms=(),
            screenshot_path=None,
            spa_transitions=(
                SpaTransition(
                    from_url="https://example.com/",
                    to_url="https://example.com/detail",
                    kind="pushstate",
                ),
            ),
        )
        page_b = PageData(
            url="https://example.com/detail",
            title="Detail",
            headings=(),
            links=(),
            forms=(),
            screenshot_path=None,
        )
        graph = _build_graph_from_pages([page_a, page_b])
        assert graph.has_edge("https://example.com/", "https://example.com/detail")
        assert (
            graph.edges["https://example.com/", "https://example.com/detail"]["kind"] == "pushstate"
        )

    def test_page_state_becomes_state_node(self) -> None:
        from crawler.page_crawler import PageState

        page = PageData(
            url="https://example.com/",
            title="Home",
            headings=(),
            links=(),
            forms=(),
            screenshot_path=None,
            page_states=(PageState(state_id="modal123", trigger_selector="#open", kind="modal"),),
        )
        graph = _build_graph_from_pages([page])
        state_node = f"https://example.com/{STATE_NODE_SEPARATOR}modal123"
        assert graph.has_node(state_node)
        assert graph.has_edge("https://example.com/", state_node)
        assert graph.nodes[state_node]["is_state"] is True


# ---------- スナップショット往復（Layer 2 フィールド） ----------


class TestLayer2SnapshotRoundtrip:
    def test_page_states_and_observations_roundtrip(self, tmp_path: Any) -> None:
        from crawler.page_crawler import PageState
        from diff.snapshot import load_snapshot, save_snapshot

        page = PageData(
            url="https://example.com/",
            title="Home",
            headings=(),
            links=(),
            forms=(),
            screenshot_path=None,
            page_states=(PageState(state_id="s1", trigger_selector="#b", kind="modal"),),
            validation_observations=(
                ValidationObservation(field_name="email", message=_REQUIRED_MESSAGE),
            ),
            spa_transitions=(SpaTransition(from_url="a", to_url="b", kind="pushstate"),),
        )
        path = save_snapshot([page], tmp_path)
        loaded = load_snapshot(path)[0]
        assert loaded.page_states == page.page_states
        assert loaded.validation_observations == page.validation_observations
        assert loaded.spa_transitions == page.spa_transitions
