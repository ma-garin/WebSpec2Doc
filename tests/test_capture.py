"""操作キャプチャ（セッション記録・探索カバレッジ・ヒートマップ）のユニットテスト。"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from capture.coverage import (
    compute_exploration_coverage,
    load_session_events,
    save_exploration_coverage,
)
from capture.session_recorder import SessionRecorder, normalize_footprint_path
from crawler.action_explorer import state_signature
from generator.heatmap_reporter import HEATMAP_FILE_NAME, generate_heatmap_html

# ---------- 接合キー（状態シグネチャ） ----------


class TestStateSignature:
    def test_empty_parts_is_default(self) -> None:
        assert state_signature(()) == "default"

    def test_order_independent(self) -> None:
        """パーツの順序に依存しない（記録側とクロール側で並びが違っても一致する）。"""
        assert state_signature(("dialog:a", "tab:b")) == state_signature(("tab:b", "dialog:a"))

    def test_signature_is_short_hash(self) -> None:
        sig = state_signature(("dialog:withdraw-modal",))
        assert len(sig) == 8


class TestFootprintPath:
    def test_normalizes_trailing_slash_and_case(self) -> None:
        assert normalize_footprint_path("https://a.example.com/Foo/") == "/foo"
        assert normalize_footprint_path("https://a.example.com") == "/"


# ---------- セッション記録（フェイクページ） ----------


class _FakeRecorderPage:
    """URL・バッファイベント・ライブ状態を注入できるフェイク。"""

    def __init__(self) -> None:
        self.url = "https://a.example.com/top"
        self.buffered: list[dict[str, str]] = []
        self.live_state: list[str] = []
        self.init_scripts: list[str] = []

    def add_init_script(self, script: str) -> None:
        self.init_scripts.append(script)

    def evaluate(self, js: str) -> object:
        if "__ws2dEvents" in js and "push" not in js:
            drained = list(self.buffered)
            self.buffered.clear()
            return drained
        if "querySelectorAll" in js:
            return list(self.live_state)
        return None


class TestSessionRecorder:
    def test_records_visit_action_and_state(self, tmp_path: Path) -> None:
        page = _FakeRecorderPage()
        recorder = SessionRecorder(page=page, session_path=tmp_path / "session_001.jsonl")
        recorder.start()

        page.buffered.append({"type": "click", "selector": "#open-withdraw-modal"})
        page.live_state = ["dialog:withdraw-modal"]
        recorder.poll_once()

        page.url = "https://a.example.com/next"
        page.live_state = []  # 遷移先ではモーダルは表示されていない
        recorder.poll_once()
        recorder.flush()

        lines = [
            json.loads(line)
            for line in (tmp_path / "session_001.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        kinds = [line["kind"] for line in lines]
        assert kinds == ["visit", "action", "state", "visit"]
        state_event = lines[2]
        assert state_event["state_id"] == state_signature(("dialog:withdraw-modal",))
        assert lines[1]["selector"] == "#open-withdraw-modal"

    def test_no_duplicate_state_while_unchanged(self, tmp_path: Path) -> None:
        page = _FakeRecorderPage()
        page.live_state = ["dialog:withdraw-modal"]
        recorder = SessionRecorder(page=page, session_path=tmp_path / "session_001.jsonl")
        recorder.start()
        recorder.poll_once()
        recorder.poll_once()  # 状態が変わらない限り再記録しない
        recorder.flush()
        lines = (tmp_path / "session_001.jsonl").read_text(encoding="utf-8").splitlines()
        state_lines = [line for line in lines if '"state"' in line]
        assert len(state_lines) == 1


class _FakeDatetimeClock:
    """datetime を返す注入用フェイク clock（SPEC-5-2 バーンダウンの ts 検証用）。"""

    def __init__(self, start: datetime) -> None:
        self.current = start

    def __call__(self) -> datetime:
        value = self.current
        self.current += timedelta(seconds=1)
        return value


class TestSessionRecorderTimestamp:
    def test_recorder_appends_timestamp(self, tmp_path: Path) -> None:
        """AC-1: 全レコードに注入した clock 由来の ts（UTC ISO8601）が入る。"""
        page = _FakeRecorderPage()
        fake_clock = _FakeDatetimeClock(datetime(2026, 7, 1, 9, 0, 0, tzinfo=UTC))
        recorder = SessionRecorder(
            page=page, session_path=tmp_path / "session_001.jsonl", clock=fake_clock
        )
        recorder.start()
        page.buffered.append({"type": "click", "selector": "#a"})
        recorder.poll_once()
        recorder.flush()

        lines = [
            json.loads(line)
            for line in (tmp_path / "session_001.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert all("ts" in line for line in lines)
        assert lines[0]["ts"] == "2026-07-01T09:00:00+00:00"
        assert lines[1]["ts"] == "2026-07-01T09:00:01+00:00"


# ---------- カバレッジ集計 ----------


def _inventory() -> dict:
    modal_sig = state_signature(("dialog:withdraw-modal",))
    return {
        "screens": [
            {
                "page_id": "P001",
                "url": "https://a.example.com/dashboard.html",
                "title": "ダッシュボード",
                "page_states": [{"state_id": modal_sig, "kind": "modal"}],
                "state_id": "default",
            },
            {
                "page_id": "P002",
                "url": "https://a.example.com/contact.html",
                "title": "お問い合わせ",
                "official_name": "お問い合わせ画面",
                "page_states": [],
                "state_id": "default",
            },
        ]
    }


def _events() -> list[dict]:
    modal_sig = state_signature(("dialog:withdraw-modal",))
    return [
        {"kind": "visit", "path": "/dashboard.html", "url": "..."},
        {"kind": "action", "path": "/dashboard.html", "selector": "#open-withdraw-modal"},
        {"kind": "state", "path": "/dashboard.html", "state_id": modal_sig},
        {"kind": "visit", "path": "/unknown.html", "url": "..."},
    ]


class TestCoverage:
    def test_explored_and_unexplored(self) -> None:
        coverage = compute_exploration_coverage(_inventory(), _events())
        summary = coverage["summary"]
        assert summary["total_screens"] == 2
        assert summary["explored_screens"] == 1
        assert summary["coverage_ratio"] == 0.5
        dashboard = next(s for s in coverage["screens"] if s["page_id"] == "P001")
        assert dashboard["visits"] == 1
        assert dashboard["actions"] == 1
        assert dashboard["states"][0]["touched"] == 1
        contact = next(s for s in coverage["screens"] if s["page_id"] == "P002")
        assert contact["explored"] is False
        assert contact["title"] == "お問い合わせ画面"  # official_name を優先

    def test_unmatched_footprints_reported(self) -> None:
        coverage = compute_exploration_coverage(_inventory(), _events())
        assert coverage["unmatched_footprints"] == [{"path": "/unknown.html", "visits": 1}]

    def test_state_coverage_counted(self) -> None:
        coverage = compute_exploration_coverage(_inventory(), _events())
        assert coverage["summary"]["total_states"] == 1
        assert coverage["summary"]["touched_states"] == 1

    def test_empty_inventory(self) -> None:
        coverage = compute_exploration_coverage({"screens": []}, _events())
        assert coverage["summary"]["coverage_ratio"] == 0.0

    def test_coverage_result_ignores_ts(self) -> None:
        """AC-6: ts の有無で集計結果は変わらない（coverage は ts を参照しない）。"""
        events_with_ts = [dict(e, ts="2026-07-01T09:00:00+00:00") for e in _events()]
        assert compute_exploration_coverage(_inventory(), events_with_ts) == (
            compute_exploration_coverage(_inventory(), _events())
        )


class TestSessionLoading:
    def test_load_session_events_from_dir(self, tmp_path: Path) -> None:
        sessions = tmp_path / "sessions"
        sessions.mkdir()
        (sessions / "session_001.jsonl").write_text(
            '{"kind": "visit", "path": "/a"}\nnot-json\n', encoding="utf-8"
        )
        events = load_session_events(tmp_path)
        assert len(events) == 1
        assert events[0]["session"] == "session_001.jsonl"


# ---------- ヒートマップ HTML ----------


class TestHeatmapHtml:
    def test_contains_summary_and_warning(self, tmp_path: Path) -> None:
        coverage = compute_exploration_coverage(_inventory(), _events())
        html_text = generate_heatmap_html(coverage)
        assert "探索カバレッジヒートマップ" in html_text
        assert "⚠ 未探索" in html_text  # 色だけでなくアイコン＋ラベルで警告
        assert "地図にない足跡" in html_text
        assert "/unknown.html" in html_text

        save_exploration_coverage(coverage, tmp_path)
        assert (tmp_path / HEATMAP_FILE_NAME).exists()
        assert (tmp_path / "exploration_coverage.json").exists()

    def test_no_external_resources(self) -> None:
        html_text = generate_heatmap_html(compute_exploration_coverage(_inventory(), []))
        assert "http://" not in html_text.replace("http://a.example.com", "")
        assert "<script src" not in html_text
        assert "<link" not in html_text


class TestAboutBlankSkipped:
    def test_about_blank_visit_is_not_recorded(self, tmp_path: Path) -> None:
        """記録開始直後の about:blank は足跡として記録しない。"""
        page = _FakeRecorderPage()
        page.url = "about:blank"
        recorder = SessionRecorder(page=page, session_path=tmp_path / "session_001.jsonl")
        recorder.start()
        page.url = "https://a.example.com/top"
        recorder.poll_once()
        recorder.flush()
        lines = [
            json.loads(line)
            for line in (tmp_path / "session_001.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert [line["kind"] for line in lines] == ["visit"]
        assert lines[0]["path"] == "/top"
