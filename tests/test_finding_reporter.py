"""気づき→バグ票変換（SPEC-2-3: capture.finding_reporter）の単体テスト。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from capture.finding_reporter import (
    CSV_ENCODING,
    FindingTicket,
    build_finding_tickets,
    save_findings,
)


def _session_events() -> list[dict]:
    """visit → action×2 → finding の 1 セッション分のイベント列。"""
    return [
        {
            "session": "session_001.jsonl",
            "kind": "visit",
            "url": "https://a.example.com/checkout.html",
            "path": "/checkout.html",
        },
        {
            "session": "session_001.jsonl",
            "kind": "action",
            "action_type": "click",
            "selector": "#add-to-cart",
            "url": "https://a.example.com/checkout.html",
            "path": "/checkout.html",
        },
        {
            "session": "session_001.jsonl",
            "kind": "action",
            "action_type": "input",
            "selector": "input[name='quantity']",
            "url": "https://a.example.com/checkout.html",
            "path": "/checkout.html",
        },
        {
            "session": "session_001.jsonl",
            "kind": "finding",
            "note": "数量をマイナスにしても送信できてしまう",
            "url": "https://a.example.com/checkout.html",
            "path": "/checkout.html",
            "state_id": "default",
        },
    ]


class TestBuildFindingTickets:
    def test_repro_steps_from_preceding_actions(self) -> None:
        """visit→action×2→finding から手順 3 件（URL＋操作 2）が生成される（AC-3）。"""
        tickets = build_finding_tickets(_session_events())
        assert len(tickets) == 1
        ticket = tickets[0]
        assert ticket.finding_id == "F001"
        assert len(ticket.repro_steps) == 3
        assert ticket.repro_steps[0] == "1. https://a.example.com/checkout.html を開く"
        assert ticket.repro_steps[1] == "2. 「#add-to-cart」をクリック"
        assert ticket.repro_steps[2] == "3. 「input[name='quantity']」を入力"
        assert ticket.evidence_selector == "input[name='quantity']"
        assert ticket.confidence == 1.0

    def test_untitled_finding_kept(self) -> None:
        """note が空でも気づきは棄却されず自動命名される（AC-5）。"""
        events = [
            {
                "session": "session_001.jsonl",
                "kind": "visit",
                "url": "https://a.example.com/checkout.html",
                "path": "/checkout.html",
            },
            {
                "session": "session_001.jsonl",
                "kind": "finding",
                "note": "",
                "url": "https://a.example.com/checkout.html",
                "path": "/checkout.html",
                "state_id": "default",
            },
        ]
        tickets = build_finding_tickets(events)
        assert len(tickets) == 1
        assert tickets[0].title == "無題の気づき（/checkout.html）"
        assert tickets[0].note == ""

    def test_title_truncated_to_40_chars(self) -> None:
        long_note = "あ" * 60
        events = [
            {
                "session": "session_001.jsonl",
                "kind": "visit",
                "url": "https://a.example.com/checkout.html",
                "path": "/checkout.html",
            },
            {
                "session": "session_001.jsonl",
                "kind": "finding",
                "note": long_note,
                "url": "https://a.example.com/checkout.html",
                "path": "/checkout.html",
                "state_id": "default",
            },
        ]
        tickets = build_finding_tickets(events)
        assert tickets[0].title == long_note[:40]

    def test_no_preceding_action_annotated(self) -> None:
        """finding 前に操作が 1 件も無い場合、手順に「操作記録なし」の注記が付く。"""
        events = [
            {
                "session": "session_001.jsonl",
                "kind": "visit",
                "url": "https://a.example.com/top.html",
                "path": "/top.html",
            },
            {
                "session": "session_001.jsonl",
                "kind": "finding",
                "note": "レイアウト崩れ",
                "url": "https://a.example.com/top.html",
                "path": "/top.html",
                "state_id": "default",
            },
        ]
        tickets = build_finding_tickets(events)
        ticket = tickets[0]
        assert ticket.evidence_selector == ""
        assert ticket.repro_steps[-1] == "2. 操作記録なし（未確認）"

    def test_zero_findings_completes(self) -> None:
        """finding の無いイベント列では空リストになる（AC-6）。"""
        events = [
            {"session": "session_001.jsonl", "kind": "visit", "url": "...", "path": "/a"},
            {
                "session": "session_001.jsonl",
                "kind": "action",
                "action_type": "click",
                "selector": "#a",
                "url": "...",
                "path": "/a",
            },
        ]
        assert build_finding_tickets(events) == []
        assert build_finding_tickets([]) == []

    def test_finding_ids_ordered_by_session_then_row(self) -> None:
        """連番はセッション名昇順→行順で振られる。"""
        events = [
            {
                "session": "session_002.jsonl",
                "kind": "visit",
                "url": "https://a.example.com/x",
                "path": "/x",
            },
            {
                "session": "session_002.jsonl",
                "kind": "finding",
                "note": "2番目セッションの気づき",
                "url": "https://a.example.com/x",
                "path": "/x",
                "state_id": "default",
            },
            {
                "session": "session_001.jsonl",
                "kind": "visit",
                "url": "https://a.example.com/y",
                "path": "/y",
            },
            {
                "session": "session_001.jsonl",
                "kind": "finding",
                "note": "1番目セッションの気づき",
                "url": "https://a.example.com/y",
                "path": "/y",
                "state_id": "default",
            },
        ]
        tickets = build_finding_tickets(events)
        assert [(t.finding_id, t.session) for t in tickets] == [
            ("F001", "session_001.jsonl"),
            ("F002", "session_002.jsonl"),
        ]

    def test_multiple_findings_in_one_session_accumulate_steps(self) -> None:
        """同一セッション内の 2 件目の気づきは、先頭からの累積手順を含む。"""
        events = [
            {
                "session": "session_001.jsonl",
                "kind": "visit",
                "url": "https://a.example.com/top",
                "path": "/top",
            },
            {
                "session": "session_001.jsonl",
                "kind": "action",
                "action_type": "click",
                "selector": "#a",
                "url": "https://a.example.com/top",
                "path": "/top",
            },
            {
                "session": "session_001.jsonl",
                "kind": "finding",
                "note": "1個目",
                "url": "https://a.example.com/top",
                "path": "/top",
                "state_id": "default",
            },
            {
                "session": "session_001.jsonl",
                "kind": "action",
                "action_type": "click",
                "selector": "#b",
                "url": "https://a.example.com/top",
                "path": "/top",
            },
            {
                "session": "session_001.jsonl",
                "kind": "finding",
                "note": "2個目",
                "url": "https://a.example.com/top",
                "path": "/top",
                "state_id": "default",
            },
        ]
        tickets = build_finding_tickets(events)
        assert len(tickets) == 2
        assert len(tickets[0].repro_steps) == 2  # 訪問＋#a クリック
        assert len(tickets[1].repro_steps) == 3  # 訪問＋#a＋#b クリック（累積）

    def test_severity_column_always_empty(self, tmp_path: Path) -> None:
        """CSV の重要度列は常に空欄（推定値を出さない。§3 スコープ外）。"""
        tickets = build_finding_tickets(_session_events())
        save_findings(tickets, tmp_path)
        with (tmp_path / "findings.csv").open(encoding=CSV_ENCODING, newline="") as f:
            rows = list(csv.reader(f))
        assert rows[0][-1] == "重要度"
        assert rows[1][-1] == ""


class TestSaveFindings:
    def test_zero_findings_writes_files_with_count_zero(self, tmp_path: Path) -> None:
        save_findings([], tmp_path)
        assert (tmp_path / "findings.json").exists()
        assert (tmp_path / "findings.csv").exists()
        data = json.loads((tmp_path / "findings.json").read_text(encoding="utf-8"))
        assert data["count"] == 0
        assert data["findings"] == []
        with (tmp_path / "findings.csv").open(encoding=CSV_ENCODING, newline="") as f:
            rows = list(csv.reader(f))
        assert len(rows) == 1  # ヘッダのみ

    def test_csv_multiline_and_comma_safe(self, tmp_path: Path) -> None:
        """note に改行・カンマを含んでも csv モジュールのクォートで 1 行 9 列に収まる（AC-4）。"""
        ticket = FindingTicket(
            finding_id="F001",
            session="session_001.jsonl",
            title="カンマ,改行\nテスト",
            note='1行目\n2行目,カンマ入り"引用符"',
            url="https://a.example.com/x",
            path="/x",
            state_id="default",
            repro_steps=("1. https://a.example.com/x を開く",),
            evidence_selector="",
        )
        save_findings([ticket], tmp_path)
        with (tmp_path / "findings.csv").open(encoding=CSV_ENCODING, newline="") as f:
            rows = list(csv.reader(f))
        assert len(rows) == 2
        data_row = rows[1]
        assert len(data_row) == 9
        assert data_row[5] == '1行目\n2行目,カンマ入り"引用符"'

    def test_json_contains_all_fields(self, tmp_path: Path) -> None:
        tickets = build_finding_tickets(_session_events())
        save_findings(tickets, tmp_path)
        data = json.loads((tmp_path / "findings.json").read_text(encoding="utf-8"))
        assert data["count"] == 1
        entry = data["findings"][0]
        assert entry["finding_id"] == "F001"
        assert entry["confidence"] == 1.0
        assert entry["repro_steps"] == list(tickets[0].repro_steps)
