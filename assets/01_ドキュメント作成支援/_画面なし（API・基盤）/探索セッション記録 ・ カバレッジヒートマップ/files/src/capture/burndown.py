"""探索カバレッジの進捗バーンダウン（セッション日時ベースの時系列推移）。

探索カバレッジ（capture.coverage）は「現時点の消化率」しか出せない。本モジュールは
セッション記録の足跡をセッション別に分割し、代表時刻の昇順に並べ、先頭〜k番目の
累積イベントで既存の compute_exploration_coverage を再利用して k 点目の系列点を作る。

evidence-only 原則: セッションイベントに ts（実測の記録時刻）が無い旧形式ファイルは
ファイルの mtime で代替するが、その点には estimated=True と注記を必ず付ける
（根拠のない日時を事実として出さない）。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from capture.coverage import compute_exploration_coverage

logger = logging.getLogger(__name__)

BURNDOWN_ESTIMATED_NOTE = "日時はファイル更新時刻からの推定"


@dataclass(frozen=True)
class BurndownPoint:
    """バーンダウン系列の 1 点（1 セッション時点での累積カバレッジ）。"""

    session: str
    at: str
    estimated: bool
    explored_screens: int
    touched_states: int
    remaining_screens: int
    remaining_states: int
    coverage_ratio: float


def _session_timestamp(
    session_events: list[dict[str, Any]], session_path: Path
) -> tuple[str, bool]:
    """セッションの代表時刻を返す。

    先頭イベントに妥当な ts があればそれを採用する（estimated=False）。
    ts が無い、またはパース不能な場合はファイルの mtime を採用し、
    estimated=True（推定）と明示する。
    """
    for event in session_events:
        raw_ts = event.get("ts")
        if not raw_ts:
            continue
        try:
            datetime.fromisoformat(str(raw_ts))
        except ValueError:
            logger.warning(
                "セッション %s の ts をパースできません（mtime で代替します）: %r",
                session_path.name,
                raw_ts,
            )
            break
        return str(raw_ts), False
    mtime = datetime.fromtimestamp(session_path.stat().st_mtime, tz=UTC)
    return mtime.isoformat(timespec="seconds"), True


def compute_exploration_burndown(
    report: dict[str, Any], events: list[dict[str, Any]], sessions_dir: Path
) -> dict[str, Any]:
    """セッション日時昇順の累積カバレッジ系列を返す（点列＋分母サマリ）。

    分母（total_screens/total_states）は最新の report.json に対するものであり、
    系列はスナップショットではなく「現インベントリに対する消化史」である
    （再クロールで分母が変わると過去点の remaining も再計算される）。
    """
    by_session: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        session_name = str(event.get("session") or "")
        by_session.setdefault(session_name, []).append(event)

    session_infos: list[tuple[str, str, bool, list[dict[str, Any]]]] = []
    for session_name, session_events in by_session.items():
        session_path = sessions_dir / session_name
        at, estimated = _session_timestamp(session_events, session_path)
        session_infos.append((session_name, at, estimated, session_events))

    # 代表時刻の昇順（同時刻はセッション名昇順で安定ソート）
    session_infos.sort(key=lambda info: (info[1], info[0]))

    points: list[BurndownPoint] = []
    cumulative_events: list[dict[str, Any]] = []
    total_screens = 0
    total_states = 0
    for session_name, at, estimated, session_events in session_infos:
        cumulative_events.extend(session_events)
        coverage = compute_exploration_coverage(report, cumulative_events)
        summary = coverage["summary"]
        total_screens = int(summary["total_screens"])
        total_states = int(summary["total_states"])
        explored_screens = int(summary["explored_screens"])
        touched_states = int(summary["touched_states"])
        points.append(
            BurndownPoint(
                session=session_name,
                at=at,
                estimated=estimated,
                explored_screens=explored_screens,
                touched_states=touched_states,
                remaining_screens=total_screens - explored_screens,
                remaining_states=total_states - touched_states,
                coverage_ratio=float(summary["coverage_ratio"]),
            )
        )

    return {
        "summary": {
            "total_screens": total_screens,
            "total_states": total_states,
            "session_count": len(points),
            "note": (
                "分母（総画面数・総状態数）は最新の report.json に対するもの。"
                "再クロールで分母が変わると過去点の残数も再計算される"
                "（系列はスナップショットではなく現インベントリに対する消化史）。"
            ),
        },
        "points": [
            {
                "session": p.session,
                "at": p.at,
                "estimated": p.estimated,
                "estimated_note": BURNDOWN_ESTIMATED_NOTE if p.estimated else "",
                "explored_screens": p.explored_screens,
                "touched_states": p.touched_states,
                "remaining_screens": p.remaining_screens,
                "remaining_states": p.remaining_states,
                "coverage_ratio": p.coverage_ratio,
            }
            for p in points
        ],
    }


def save_exploration_burndown(burndown: dict[str, Any], output_dir: Path) -> None:
    """exploration_burndown.json と折れ線 HTML を出力する。"""
    from generator.burndown_reporter import BURNDOWN_FILE_NAME, generate_burndown_html

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "exploration_burndown.json").write_text(
        json.dumps(burndown, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / BURNDOWN_FILE_NAME).write_text(generate_burndown_html(burndown), encoding="utf-8")
