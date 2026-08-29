"""気づきマーク → 再現手順付きバグ票（キャプチャ Phase 3: 気づき→バグ票自動起票）。

探索セッション中にテスターが気づきマーク（`kind: "finding"` イベント）を
残した箇所について、そのセッションの先頭（最初の visit）から気づき時点までの
visit/action イベントを再現手順として自動生成し、汎用 JSON/CSV のバグ票として
出力する（特定ベンダー依存の起票 API は使わない。evidence-only 原則: 推定・
言い換えをせず記録されたイベント列をそのまま転記する）。

再現手順の手順文字列化（アクション種別→動詞）は capture.reverse_generator の
変換テーブルを再利用し、二重実装しない（docs/specs/CONVENTIONS.md §1-3）。

CSV の文字エンコーディングは generator.csv_reporter.CSV_ENCODING と同じ値
（utf-8-sig）を使うが、src/capture（入力層）から src/generator（出力層）への
import は層方向の掟に反する（CONVENTIONS §1-1「crawler から generator を呼ばない」
と同種の禁止）ため、値のみをこのモジュール内に複製する（仕様外判断）。
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from capture.reverse_generator import _ACTION_VERBS

logger = logging.getLogger(__name__)

# generator.csv_reporter.CSV_ENCODING と同じ値（層方向制約のため直接 import しない）
CSV_ENCODING = "utf-8-sig"

FINDINGS_JSON_FILE_NAME = "findings.json"
FINDINGS_CSV_FILE_NAME = "findings.csv"

_TITLE_MAX_LEN = 40
_NO_ACTION_NOTE = "操作記録なし（未確認）"

_FINDING_CSV_HEADER = [
    "ID",
    "タイトル",
    "再現手順",
    "URL",
    "画面状態",
    "気づきメモ",
    "根拠セレクタ",
    "セッション",
    "重要度",
]


@dataclass(frozen=True)
class FindingTicket:
    """1 件の気づき票（実測由来・confidence 1.0 固定）。"""

    finding_id: str
    session: str
    title: str
    note: str
    url: str
    path: str
    state_id: str
    repro_steps: tuple[str, ...]
    evidence_selector: str
    confidence: float = 1.0


def build_finding_tickets(events: list[dict[str, Any]]) -> list[FindingTicket]:
    """セッションイベントから気づき票を構築する。finding が無ければ空リスト。

    連番はセッション名昇順→行順（capture.reverse_generator.generate_recorded_assets
    と同じ並び方針）。repro_steps はセッション開始（最初の visit）から気づき時点
    までの visit/action イベントを行順のまま手順文字列化したもの。
    """
    sessions: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        sessions.setdefault(str(event.get("session") or ""), []).append(event)

    tickets: list[FindingTicket] = []
    finding_seq = 0
    for session_name in sorted(sessions):
        for ticket_data in _build_session_tickets(session_name, sessions[session_name]):
            finding_seq += 1
            tickets.append(
                FindingTicket(
                    finding_id=f"F{finding_seq:03d}",
                    session=ticket_data["session"],
                    title=ticket_data["title"],
                    note=ticket_data["note"],
                    url=ticket_data["url"],
                    path=ticket_data["path"],
                    state_id=ticket_data["state_id"],
                    repro_steps=tuple(ticket_data["repro_steps"]),
                    evidence_selector=ticket_data["evidence_selector"],
                )
            )
    return tickets


def _build_session_tickets(
    session_name: str, session_events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """1 セッション分のイベント列から気づき票（辞書中間表現）を順に構築する。"""
    tickets: list[dict[str, Any]] = []
    steps: list[str] = []
    last_action_selector = ""
    has_action = False

    for event in session_events:
        kind = event.get("kind")
        if kind == "visit":
            url = str(event.get("url") or "")
            steps.append(f"{len(steps) + 1}. {url} を開く")
        elif kind == "action":
            has_action = True
            selector = str(event.get("selector") or "")
            last_action_selector = selector
            verb = _ACTION_VERBS.get(str(event.get("action_type") or ""), "操作")
            steps.append(f"{len(steps) + 1}. 「{selector}」を{verb}")
        elif kind == "finding":
            repro_steps = list(steps)
            if not has_action:
                repro_steps.append(f"{len(repro_steps) + 1}. {_NO_ACTION_NOTE}")
            note = str(event.get("note") or "")
            path = str(event.get("path") or "")
            tickets.append(
                {
                    "session": session_name,
                    "title": _build_title(note, path),
                    "note": note,
                    "url": str(event.get("url") or ""),
                    "path": path,
                    "state_id": str(event.get("state_id") or "default"),
                    "repro_steps": repro_steps,
                    "evidence_selector": last_action_selector,
                }
            )
        # 未知 kind（state 等）は再現手順に含めない（AC-3 は visit/action のみ）

    return tickets


def _build_title(note: str, path: str) -> str:
    """note 先頭 40 文字をタイトルにする。空なら無題の気づきとして自動命名する。"""
    trimmed = note.strip()
    if trimmed:
        return trimmed[:_TITLE_MAX_LEN]
    return f"無題の気づき（{path}）"


def save_findings(tickets: list[FindingTicket], output_dir: Path) -> None:
    """findings.json と findings.csv を出力する（0 件でもファイルは生成し件数 0 を明示）。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / FINDINGS_JSON_FILE_NAME).write_text(
        json.dumps(
            {"count": len(tickets), "findings": [_ticket_to_dict(t) for t in tickets]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    with (output_dir / FINDINGS_CSV_FILE_NAME).open(
        "w", newline="", encoding=CSV_ENCODING
    ) as handle:
        writer = csv.writer(handle)
        writer.writerow(_FINDING_CSV_HEADER)
        for ticket in tickets:
            writer.writerow(
                [
                    ticket.finding_id,
                    ticket.title,
                    "\n".join(ticket.repro_steps),
                    ticket.url,
                    ticket.state_id,
                    ticket.note,
                    ticket.evidence_selector,
                    ticket.session,
                    "",  # 重要度は常に空欄（推定値を出さない。§3 スコープ外）
                ]
            )
    logger.info(
        "気づき票を出力しました: %s / %s（%d 件）",
        output_dir / FINDINGS_JSON_FILE_NAME,
        output_dir / FINDINGS_CSV_FILE_NAME,
        len(tickets),
    )


def _ticket_to_dict(ticket: FindingTicket) -> dict[str, Any]:
    return {
        "finding_id": ticket.finding_id,
        "session": ticket.session,
        "title": ticket.title,
        "note": ticket.note,
        "url": ticket.url,
        "path": ticket.path,
        "state_id": ticket.state_id,
        "repro_steps": list(ticket.repro_steps),
        "evidence_selector": ticket.evidence_selector,
        "confidence": ticket.confidence,
    }
