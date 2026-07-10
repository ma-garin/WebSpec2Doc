from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from web.config import OUTPUT_DIR, SCREEN_ROW_RE


def _count_screens(screens_md: Path) -> int:
    if not screens_md.exists():
        return 0
    return sum(
        1
        for line in screens_md.read_text(encoding="utf-8").splitlines()
        if SCREEN_ROW_RE.match(line)
    )


def _summary_for_domain(domain: str, base_dir: Path | None = None) -> dict[str, int]:
    """最新の生成結果（report.json）を唯一の真実源として集計する。
    結果ページのサマリー／概要／マトリクス／履歴をすべて一致させるため。
    report.json が無い旧データのみ snapshot → screens.md にフォールバック。

    base_dir: テナントスコープ済み出力ディレクトリ。リクエストコンテキスト外
    （ストリーミング応答・バックグラウンド処理）から呼ぶ場合に明示的に渡す。"""
    domain_dir = (base_dir if base_dir is not None else OUTPUT_DIR) / domain
    report_json = domain_dir / "report.json"
    if report_json.exists():
        try:
            data = json.loads(report_json.read_text(encoding="utf-8"))
            screens = data.get("screens", [])
            # クエリ重複を統合した「正規化済み画面」のみで集計する。
            # 旧 report.json（is_canonical 無し）は全画面を canonical 扱いにフォールバック。
            canonical = [s for s in screens if s.get("is_canonical", True)]
            meta = data.get("meta", {})
            return {
                "screens": meta.get("screen_count", len(canonical)),
                "forms": sum(len(s.get("forms", [])) for s in canonical),
                "fields": sum(
                    len(f.get("fields", [])) for s in canonical for f in s.get("forms", [])
                ),
                "buttons": sum(len(s.get("buttons", [])) for s in canonical),
            }
        except (OSError, json.JSONDecodeError):
            pass
    snaps_dir = domain_dir / "snapshots"
    snaps = sorted(snaps_dir.glob("*.json")) if snaps_dir.is_dir() else []
    if not snaps:
        return {
            "screens": _count_screens(domain_dir / "screens.md"),
            "forms": 0,
            "fields": 0,
            "buttons": 0,
        }
    try:
        pages = json.loads(snaps[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"screens": 0, "forms": 0, "fields": 0, "buttons": 0}
    forms = sum(len(p.get("forms", [])) for p in pages)
    fields = sum(len(f.get("fields", [])) for p in pages for f in p.get("forms", []))
    buttons = sum(len(p.get("buttons", [])) for p in pages)
    return {"screens": len(pages), "forms": forms, "fields": fields, "buttons": buttons}


def _fmt_snap_ts(stem: str) -> str:
    try:
        return datetime.strptime(stem, "%Y%m%d-%H%M%S").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return stem
