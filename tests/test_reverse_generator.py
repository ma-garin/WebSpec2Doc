"""記録セッションからのテスト資産逆生成（SPEC-2-1）のユニットテスト。"""

from __future__ import annotations

import json
from pathlib import Path

from capture.reverse_generator import generate_recorded_assets, save_recorded_assets
from crawler.action_explorer import state_signature


def _screen(page_id: str, url: str, title: str, headings: list[str] | None = None) -> dict:
    return {
        "page_id": page_id,
        "url": url,
        "title": title,
        "headings": headings or [],
        "forms": [],
    }


def _report(screens: list[dict]) -> dict:
    return {"screens": screens}


class TestActionBecomesStepWithObserved:
    def test_action_becomes_step_with_observed_state(self) -> None:
        modal_sig = state_signature(("dialog:withdraw-modal",))
        events = [
            {
                "session": "session_001.jsonl",
                "kind": "visit",
                "path": "/dashboard.html",
                "url": "https://a.example.com/dashboard.html",
            },
            {
                "session": "session_001.jsonl",
                "kind": "action",
                "action_type": "click",
                "selector": "#open-withdraw-modal",
                "path": "/dashboard.html",
                "url": "https://a.example.com/dashboard.html",
            },
            {
                "session": "session_001.jsonl",
                "kind": "state",
                "state_id": modal_sig,
                "path": "/dashboard.html",
            },
        ]
        report = _report(
            [_screen("P001", "https://a.example.com/dashboard.html", "ダッシュボード")]
        )
        assets = generate_recorded_assets(report, events)

        assert len(assets["test_cases"]) == 1
        case = assets["test_cases"][0]
        assert len(case["steps"]) == 1
        step = case["steps"][0]
        assert step["selector"] == "#open-withdraw-modal"
        assert modal_sig in step["observed"]


class TestRecordedFlowConfidence:
    def test_recorded_flow_has_confidence_one(self) -> None:
        events = [
            {
                "session": "session_001.jsonl",
                "kind": "visit",
                "path": "/login.html",
                "url": "https://a.example.com/login.html",
            },
            {
                "session": "session_001.jsonl",
                "kind": "visit",
                "path": "/checkout.html",
                "url": "https://a.example.com/checkout.html",
            },
        ]
        report = _report(
            [
                _screen("P001", "https://a.example.com/login.html", "ログイン", ["ログイン"]),
                _screen(
                    "P002",
                    "https://a.example.com/checkout.html",
                    "お支払い",
                    ["クレジットカード番号"],
                ),
            ]
        )
        assets = generate_recorded_assets(report, events)
        assert len(assets["flows"]) == 1
        flow = assets["flows"][0]
        assert flow["source"] == "recorded"
        assert flow["confidence"] == 1.0
        assert flow["priority"] == "高"


class TestCandidateSchema:
    def test_candidates_schema_matches_pw_candidate(self) -> None:
        events = [
            {
                "session": "session_001.jsonl",
                "kind": "visit",
                "path": "/dashboard.html",
                "url": "https://a.example.com/dashboard.html",
            },
            {
                "session": "session_001.jsonl",
                "kind": "action",
                "action_type": "click",
                "selector": "#btn",
                "path": "/dashboard.html",
                "url": "https://a.example.com/dashboard.html",
            },
        ]
        report = _report(
            [_screen("P001", "https://a.example.com/dashboard.html", "ダッシュボード")]
        )
        assets = generate_recorded_assets(report, events)
        candidate = assets["candidates"][0]
        for key in ("id", "title", "trace_id", "automation_status", "steps", "expected"):
            assert key in candidate
        assert candidate["steps"][0].startswith("page.goto(")


class TestStateJoinKey:
    def test_state_join_uses_recorded_state_id(self) -> None:
        """逆生成側で state_id を再計算せず記録値をそのまま使う。"""
        custom_sig = "abcdef12"
        events = [
            {
                "session": "session_001.jsonl",
                "kind": "visit",
                "path": "/x.html",
                "url": "https://a.example.com/x.html",
            },
            {
                "session": "session_001.jsonl",
                "kind": "action",
                "action_type": "click",
                "selector": "#a",
                "path": "/x.html",
                "url": "https://a.example.com/x.html",
            },
            {
                "session": "session_001.jsonl",
                "kind": "state",
                "state_id": custom_sig,
                "path": "/x.html",
            },
        ]
        report = _report([_screen("P001", "https://a.example.com/x.html", "X")])
        assets = generate_recorded_assets(report, events)
        assert custom_sig in assets["test_cases"][0]["steps"][0]["observed"]


class TestUnmatchedPathAnnotated:
    def test_unmatched_path_annotated_not_dropped(self) -> None:
        events = [
            {
                "session": "session_001.jsonl",
                "kind": "action",
                "action_type": "click",
                "selector": "#a",
                "path": "/unknown.html",
                "url": "https://a.example.com/unknown.html",
            },
            {
                "session": "session_001.jsonl",
                "kind": "visit",
                "path": "/unknown.html",
                "url": "https://a.example.com/unknown.html",
            },
        ]
        report = _report([])
        assets = generate_recorded_assets(report, events)
        assert len(assets["test_cases"]) == 1
        case = assets["test_cases"][0]
        assert case["page_ids"] == []
        assert any("未確認" in step["observed"] for step in case["steps"])


class TestNoSideEffectOnExistingOutputs:
    def test_no_side_effect_on_existing_outputs(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir()
        session_file = sessions_dir / "session_001.jsonl"
        session_file.write_text(
            json.dumps({"kind": "visit", "path": "/a", "url": "https://a.example.com/a"}) + "\n",
            encoding="utf-8",
        )
        report_path = tmp_path / "report.json"
        report_path.write_text(json.dumps(_report([])), encoding="utf-8")
        session_before = session_file.read_text(encoding="utf-8")
        report_before = report_path.read_text(encoding="utf-8")

        from capture.coverage import load_session_events

        events = load_session_events(tmp_path)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assets = generate_recorded_assets(report, events)
        save_recorded_assets(assets, tmp_path)

        assert session_file.read_text(encoding="utf-8") == session_before
        assert report_path.read_text(encoding="utf-8") == report_before
        assert (tmp_path / "recorded_assets.json").exists()
        assert (tmp_path / "recorded_candidates.json").exists()


class TestNonBusinessSessionNotFlowized:
    def test_non_business_session_not_flowized(self) -> None:
        events = [
            {
                "session": "session_001.jsonl",
                "kind": "visit",
                "path": "/products.html",
                "url": "https://a.example.com/products.html",
            },
        ]
        report = _report(
            [_screen("P001", "https://a.example.com/products.html", "商品一覧", ["一覧"])]
        )
        assets = generate_recorded_assets(report, events)
        assert assets["flows"] == []
        assert len(assets["test_cases"]) == 1


class TestMultipleSessions:
    def test_sessions_get_sequential_case_ids(self) -> None:
        events = [
            {
                "session": "session_001.jsonl",
                "kind": "visit",
                "path": "/a",
                "url": "https://a.example.com/a",
            },
            {
                "session": "session_002.jsonl",
                "kind": "visit",
                "path": "/b",
                "url": "https://a.example.com/b",
            },
        ]
        assets = generate_recorded_assets(_report([]), events)
        case_ids = [c["case_id"] for c in assets["test_cases"]]
        assert case_ids == ["RC001", "RC002"]

    def test_session_without_visit_is_skipped(self) -> None:
        events = [
            {
                "session": "session_001.jsonl",
                "kind": "action",
                "action_type": "click",
                "selector": "#a",
                "path": "/a",
                "url": "https://a.example.com/a",
            },
        ]
        assets = generate_recorded_assets(_report([]), events)
        assert assets["test_cases"] == []


class TestSpecTsCompatibility:
    def test_generate_spec_ts_consumes_recorded_candidates(self, tmp_path: Path) -> None:
        """recorded_candidates.json が generate_spec_ts でエラーなく消費できる（AC-3）。"""
        import sys

        sys.path.insert(0, str(Path(__file__).parent.parent))
        from web.services.spec_ts_generator import generate_spec_ts

        events = [
            {
                "session": "session_001.jsonl",
                "kind": "visit",
                "path": "/dashboard.html",
                "url": "https://a.example.com/dashboard.html",
            },
            {
                "session": "session_001.jsonl",
                "kind": "action",
                "action_type": "click",
                "selector": "#open-withdraw-modal",
                "path": "/dashboard.html",
                "url": "https://a.example.com/dashboard.html",
            },
        ]
        report = _report(
            [_screen("P001", "https://a.example.com/dashboard.html", "ダッシュボード")]
        )
        assets = generate_recorded_assets(report, events)
        save_recorded_assets(assets, tmp_path, domain="a.example.com")

        output_path = tmp_path / "recorded.spec.ts"
        result = generate_spec_ts(
            "a.example.com",
            tmp_path / "recorded_candidates.json",
            output_path,
        )
        content = result.read_text(encoding="utf-8")
        assert "page.goto('https://a.example.com/dashboard.html')" in content
