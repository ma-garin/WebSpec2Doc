"""進捗バーンダウン（探索カバレッジの時系列推移）のユニット・結合テスト（SPEC-5-2）。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from capture.burndown import (
    BURNDOWN_ESTIMATED_NOTE,
    compute_exploration_burndown,
    save_exploration_burndown,
)
from crawler.action_explorer import state_signature
from generator.burndown_reporter import BURNDOWN_FILE_NAME, generate_burndown_html


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
                "page_states": [],
                "state_id": "default",
            },
        ]
    }


def _write_session(sessions_dir: Path, name: str, lines: list[dict]) -> Path:
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = sessions_dir / name
    path.write_text(
        "\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n",
        encoding="utf-8",
    )
    return path


def _load_events_with_session_tag(sessions_dir: Path) -> list[dict]:
    """load_session_events と同じく各レコードへ session ファイル名を付与して読む。"""
    events = []
    for session_file in sorted(sessions_dir.glob("session_*.jsonl")):
        for line in session_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            record["session"] = session_file.name
            events.append(record)
    return events


class TestBurndownOrdering:
    def test_burndown_orders_sessions_by_ts(self, tmp_path: Path) -> None:
        """AC-2: ts が逆順（ファイル名の昇順とは逆）の 2 セッションでも時刻昇順に並ぶ。"""
        sessions_dir = tmp_path / "sessions"
        # ファイル名は session_001 が先だが、ts は session_002 の方が早い
        _write_session(
            sessions_dir,
            "session_001.jsonl",
            [
                {
                    "kind": "visit",
                    "path": "/contact.html",
                    "ts": "2026-07-02T09:00:00+00:00",
                }
            ],
        )
        _write_session(
            sessions_dir,
            "session_002.jsonl",
            [
                {
                    "kind": "visit",
                    "path": "/dashboard.html",
                    "ts": "2026-07-01T09:00:00+00:00",
                }
            ],
        )
        events = _load_events_with_session_tag(sessions_dir)
        burndown = compute_exploration_burndown(_inventory(), events, sessions_dir)
        points = burndown["points"]
        assert [p["session"] for p in points] == ["session_002.jsonl", "session_001.jsonl"]
        # 1 点目は dashboard のみ探索済み、2 点目で contact も探索済みになる
        assert points[0]["explored_screens"] == 1
        assert points[0]["remaining_screens"] == 1
        assert points[1]["explored_screens"] == 2
        assert points[1]["remaining_screens"] == 0


class TestBurndownEstimatedFallback:
    def test_burndown_mtime_fallback_marked_estimated(self, tmp_path: Path) -> None:
        """AC-3: ts の無い旧形式セッションは mtime 代替＋estimated=True＋注記が付く。"""
        sessions_dir = tmp_path / "sessions"
        session_path = _write_session(
            sessions_dir,
            "session_001.jsonl",
            [{"kind": "visit", "path": "/dashboard.html"}],
        )
        events = _load_events_with_session_tag(sessions_dir)
        burndown = compute_exploration_burndown(_inventory(), events, sessions_dir)
        point = burndown["points"][0]
        assert point["estimated"] is True
        assert point["estimated_note"] == BURNDOWN_ESTIMATED_NOTE
        expected_at = datetime.fromtimestamp(session_path.stat().st_mtime, tz=UTC).isoformat(
            timespec="seconds"
        )
        assert point["at"] == expected_at

    def test_invalid_ts_falls_back(self, tmp_path: Path) -> None:
        """パース不能な ts は mtime 代替＋estimated=True になる。"""
        sessions_dir = tmp_path / "sessions"
        _write_session(
            sessions_dir,
            "session_001.jsonl",
            [{"kind": "visit", "path": "/dashboard.html", "ts": "broken"}],
        )
        events = _load_events_with_session_tag(sessions_dir)
        burndown = compute_exploration_burndown(_inventory(), events, sessions_dir)
        point = burndown["points"][0]
        assert point["estimated"] is True
        assert point["estimated_note"] == BURNDOWN_ESTIMATED_NOTE


class TestBurndownMonotonic:
    def test_burndown_monotonic(self, tmp_path: Path) -> None:
        """AC-4: 3 セッション累積で explored/touched は非減少、remaining は非増加。"""
        sessions_dir = tmp_path / "sessions"
        modal_sig = state_signature(("dialog:withdraw-modal",))
        _write_session(
            sessions_dir,
            "session_001.jsonl",
            [{"kind": "visit", "path": "/dashboard.html", "ts": "2026-07-01T09:00:00+00:00"}],
        )
        _write_session(
            sessions_dir,
            "session_002.jsonl",
            [{"kind": "visit", "path": "/contact.html", "ts": "2026-07-02T09:00:00+00:00"}],
        )
        _write_session(
            sessions_dir,
            "session_003.jsonl",
            [
                {
                    "kind": "state",
                    "path": "/dashboard.html",
                    "state_id": modal_sig,
                    "ts": "2026-07-03T09:00:00+00:00",
                }
            ],
        )
        events = _load_events_with_session_tag(sessions_dir)
        burndown = compute_exploration_burndown(_inventory(), events, sessions_dir)
        points = burndown["points"]
        assert len(points) == 3

        explored = [p["explored_screens"] for p in points]
        touched = [p["touched_states"] for p in points]
        remaining_screens = [p["remaining_screens"] for p in points]
        remaining_states = [p["remaining_states"] for p in points]

        assert explored == sorted(explored)
        assert touched == sorted(touched)
        assert remaining_screens == sorted(remaining_screens, reverse=True)
        assert remaining_states == sorted(remaining_states, reverse=True)
        assert explored[-1] == 2
        assert touched[-1] == 1
        assert remaining_screens[-1] == 0
        assert remaining_states[-1] == 0


class TestBurndownSinglePoint:
    def test_single_session_single_point(self, tmp_path: Path) -> None:
        """AC-5: セッション 1 件なら系列は 1 点で HTML 生成が例外なく行える。"""
        sessions_dir = tmp_path / "sessions"
        _write_session(
            sessions_dir,
            "session_001.jsonl",
            [{"kind": "visit", "path": "/dashboard.html", "ts": "2026-07-01T09:00:00+00:00"}],
        )
        events = _load_events_with_session_tag(sessions_dir)
        burndown = compute_exploration_burndown(_inventory(), events, sessions_dir)
        assert len(burndown["points"]) == 1
        html_text = generate_burndown_html(burndown)
        assert "<svg" in html_text
        assert "探索カバレッジ進捗バーンダウン" in html_text


class TestBurndownHtmlSelfContained:
    def test_html_self_contained(self, tmp_path: Path) -> None:
        """生成 HTML は外部リソース参照（src/href）を含まない。"""
        sessions_dir = tmp_path / "sessions"
        _write_session(
            sessions_dir,
            "session_001.jsonl",
            [{"kind": "visit", "path": "/dashboard.html", "ts": "2026-07-01T09:00:00+00:00"}],
        )
        _write_session(
            sessions_dir,
            "session_002.jsonl",
            [{"kind": "visit", "path": "/contact.html"}],  # ts なし → estimated 点も含める
        )
        events = _load_events_with_session_tag(sessions_dir)
        burndown = compute_exploration_burndown(_inventory(), events, sessions_dir)
        html_text = generate_burndown_html(burndown)
        assert "<script src" not in html_text
        assert "<link" not in html_text
        assert "http://" not in html_text
        assert "推定" in html_text  # estimated 点のラベルが色だけに依存しない


class TestSaveExplorationBurndown:
    def test_save_writes_json_and_html(self, tmp_path: Path) -> None:
        sessions_dir = tmp_path / "sessions"
        _write_session(
            sessions_dir,
            "session_001.jsonl",
            [{"kind": "visit", "path": "/dashboard.html", "ts": "2026-07-01T09:00:00+00:00"}],
        )
        events = _load_events_with_session_tag(sessions_dir)
        burndown = compute_exploration_burndown(_inventory(), events, sessions_dir)
        save_exploration_burndown(burndown, tmp_path)
        assert (tmp_path / "exploration_burndown.json").exists()
        assert (tmp_path / BURNDOWN_FILE_NAME).exists()
        saved = json.loads((tmp_path / "exploration_burndown.json").read_text(encoding="utf-8"))
        assert saved["points"][0]["session"] == "session_001.jsonl"


# ---------- CLI 結合テスト ----------


class TestCliBurndownOutput:
    def test_cli_outputs_burndown_files(self, tmp_path: Path, monkeypatch) -> None:
        """AC-2: --exploration-coverage 実行で exploration_burndown.{json,html} も出力される。"""
        import argparse

        from main import _exploration_coverage

        monkeypatch.chdir(tmp_path)
        url = "https://a.example.com/"
        output_dir = tmp_path / "output" / "a.example.com"
        output_dir.mkdir(parents=True)
        (output_dir / "report.json").write_text(
            json.dumps(_inventory(), ensure_ascii=False), encoding="utf-8"
        )
        sessions_dir = output_dir / "sessions"
        _write_session(
            sessions_dir,
            "session_001.jsonl",
            [{"kind": "visit", "path": "/dashboard.html", "ts": "2026-07-01T09:00:00+00:00"}],
        )
        _write_session(
            sessions_dir,
            "session_002.jsonl",
            [{"kind": "visit", "path": "/contact.html", "ts": "2026-07-02T09:00:00+00:00"}],
        )

        args = argparse.Namespace(url=url, output=str(tmp_path / "output"))
        _exploration_coverage(args)

        assert (output_dir / "exploration_burndown.json").exists()
        assert (output_dir / "exploration_burndown.html").exists()
        # 既存出力も無変化で存在する（AC-6）
        assert (output_dir / "exploration_coverage.json").exists()
        assert (output_dir / "exploration_heatmap.html").exists()

        burndown = json.loads(
            (output_dir / "exploration_burndown.json").read_text(encoding="utf-8")
        )
        assert len(burndown["points"]) == 2
