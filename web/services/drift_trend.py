"""スペックドリフトの時系列トレンド。

スナップショット（output/{domain}/snapshots/*.json）から画面・フォーム・
フィールド・ボタン数の推移を集計し、監視ダッシュボードに供給する。
「一回生成して終わり」ではなく、継続監視の価値（どの時点で仕様が動いたか）を
可視化するのが目的。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_TREND_POINTS = 60  # 応答肥大防止（直近60スナップショットまで）


def _stem_to_iso(stem: str) -> str:
    try:
        return datetime.strptime(stem, "%Y%m%d-%H%M%S").isoformat()
    except ValueError:
        return stem


def _count_snapshot(pages: list[dict]) -> dict[str, int]:
    forms = sum(len(p.get("forms", [])) for p in pages)
    fields = sum(len(f.get("fields", [])) for p in pages for f in p.get("forms", []))
    buttons = sum(len(p.get("buttons", [])) for p in pages)
    return {"screens": len(pages), "forms": forms, "fields": fields, "buttons": buttons}


def snapshot_trend(domain_dir: Path, limit: int = MAX_TREND_POINTS) -> list[dict]:
    """スナップショットごとの規模指標を古い順に返す。壊れたファイルは黙って飛ばす。"""
    snaps_dir = domain_dir / "snapshots"
    if not snaps_dir.is_dir():
        return []
    points: list[dict] = []
    # 壊れたファイルが混ざっても有効ポイントで limit を満たせるよう、
    # limit の3倍まで遡って読み、最後に有効分だけ切り出す
    files = sorted(snaps_dir.glob("*.json"))[-max(1, limit * 3) :]
    for snap in files:
        try:
            pages = json.loads(snap.read_text(encoding="utf-8"))
            if not isinstance(pages, list):
                continue
        except (OSError, json.JSONDecodeError):
            logger.warning("スナップショットを読めませんでした（トレンドから除外）: %s", snap)
            continue
        points.append(
            {"name": snap.stem, "timestamp": _stem_to_iso(snap.stem)} | _count_snapshot(pages)
        )
    return points[-max(1, limit) :]


def trend_summary(points: list[dict]) -> dict:
    """最新値と直前スナップショットとの差分（監視カードのバッジ用）。"""
    if not points:
        return {"points": 0}
    latest = points[-1]
    summary: dict = {"points": len(points), "latest": latest}
    if len(points) >= 2:
        prev = points[-2]
        summary["delta"] = {
            key: int(latest[key]) - int(prev[key])
            for key in ("screens", "forms", "fields", "buttons")
        }
    return summary
