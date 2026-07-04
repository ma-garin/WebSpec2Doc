"""探索カバレッジの集計。

クロール済みインベントリ（report.json = 分母）に、探索セッションの足跡
（visit / action / state イベント = 分子）を重ね、画面・状態ごとの
「触られた回数」と未探索領域を算出する。

画面の照合は正規化 URL パス、画面状態の照合はクロール時と同一アルゴリズムの
状態シグネチャ（crawler.action_explorer.state_signature）で行う。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from capture.session_recorder import SESSIONS_DIR_NAME


def load_session_events(output_dir: Path) -> list[dict[str, Any]]:
    """sessions/ 配下の全セッション JSONL を読み込む。"""
    sessions_dir = output_dir / SESSIONS_DIR_NAME
    events: list[dict[str, Any]] = []
    for session_file in sorted(sessions_dir.glob("session_*.jsonl")):
        for line in session_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                record["session"] = session_file.name
                events.append(record)
    return events


def _screen_path(screen: dict[str, Any]) -> str:
    path = urlparse(str(screen.get("url") or "")).path.rstrip("/").lower()
    return path or "/"


def compute_exploration_coverage(
    report: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    """インベントリと足跡から探索カバレッジを計算する。"""
    screens: list[dict[str, Any]] = list(report.get("screens") or [])
    path_index: dict[str, list[dict[str, Any]]] = {}
    for screen in screens:
        path_index.setdefault(_screen_path(screen), []).append(screen)

    visits: dict[str, int] = {}
    actions: dict[str, int] = {}
    touched_states: dict[str, dict[str, int]] = {}
    unmatched_paths: dict[str, int] = {}

    for event in events:
        path = str(event.get("path") or "")
        matched = path_index.get(path)
        if not matched:
            if event.get("kind") == "visit":
                unmatched_paths[path] = unmatched_paths.get(path, 0) + 1
            continue
        primary = matched[0]
        page_id = str(primary.get("page_id") or "")
        kind = event.get("kind")
        if kind == "visit":
            visits[page_id] = visits.get(page_id, 0) + 1
        elif kind == "action":
            actions[page_id] = actions.get(page_id, 0) + 1
        elif kind == "state":
            state_id = str(event.get("state_id") or "")
            # 同一パスの全画面レコード（別状態の画面を含む）と照合する
            for screen in matched:
                own_id = str(screen.get("page_id") or "")
                state_ids = {str(s.get("state_id") or "") for s in screen.get("page_states") or []}
                state_ids.add(str(screen.get("state_id") or ""))
                if state_id in state_ids:
                    per_screen = touched_states.setdefault(own_id, {})
                    per_screen[state_id] = per_screen.get(state_id, 0) + 1

    coverage_screens: list[dict[str, Any]] = []
    visited_count = 0
    total_states = 0
    touched_state_count = 0
    for screen in screens:
        page_id = str(screen.get("page_id") or "")
        visit_count = visits.get(page_id, 0)
        action_count = actions.get(page_id, 0)
        screen_touched_states = touched_states.get(page_id, {})
        states_detail = []
        for state in screen.get("page_states") or []:
            state_id = str(state.get("state_id") or "")
            touch = screen_touched_states.get(state_id, 0)
            total_states += 1
            if touch:
                touched_state_count += 1
            states_detail.append(
                {
                    "state_id": state_id,
                    "kind": str(state.get("kind") or ""),
                    "touched": touch,
                }
            )
        explored = visit_count > 0 or action_count > 0 or bool(screen_touched_states)
        if explored:
            visited_count += 1
        coverage_screens.append(
            {
                "page_id": page_id,
                "url": str(screen.get("url") or ""),
                "title": str(screen.get("official_name") or screen.get("title") or ""),
                "visits": visit_count,
                "actions": action_count,
                "states": states_detail,
                "explored": explored,
            }
        )

    total = len(screens)
    return {
        "summary": {
            "total_screens": total,
            "explored_screens": visited_count,
            "unexplored_screens": total - visited_count,
            "coverage_ratio": round(visited_count / total, 3) if total else 0.0,
            "total_states": total_states,
            "touched_states": touched_state_count,
            "session_events": len(events),
        },
        "screens": coverage_screens,
        "unmatched_footprints": [
            {"path": path, "visits": count} for path, count in sorted(unmatched_paths.items())
        ],
    }


def save_exploration_coverage(coverage: dict[str, Any], output_dir: Path) -> None:
    """exploration_coverage.json とヒートマップ HTML を出力する。"""
    from generator.heatmap_reporter import HEATMAP_FILE_NAME, generate_heatmap_html

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "exploration_coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / HEATMAP_FILE_NAME).write_text(generate_heatmap_html(coverage), encoding="utf-8")
