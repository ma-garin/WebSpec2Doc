"""影響項目につながるテストケースと、テストの観点（DD-004 tests.py）。"""
from __future__ import annotations

from .text import clip


def select(conn, sid: str, item_id: str) -> list[str]:
    """item_id とつながった testcase 種別の項目の code。"""
    rows = conn.execute(
        "SELECT DISTINCT i.code FROM links l"
        " JOIN items i ON i.id = CASE WHEN l.a_item = ? THEN l.b_item ELSE l.a_item END"
        " JOIN documents d ON d.id = i.document_id"
        " WHERE l.system_id = ? AND (l.a_item = ? OR l.b_item = ?) AND d.kind = 'testcase' ORDER BY i.code",
        (item_id, sid, item_id, item_id)).fetchall()
    return [r[0] for r in rows]


def idea(change: dict, item: dict) -> str:
    after = clip(change.get("after") or change.get("before"), 40)
    where = item.get("section") or item.get("location") or item.get("code", "")
    kind = item.get("doc_kind", "")
    if kind == "testcase":
        return f"期待値を変更後の仕様（{after}）に直してから再実行する"
    if kind == "screen":
        return f"{where} で、変更後の条件（{after}）の入力・表示・エラーを確かめる"
    return f"{where} の処理を変更後の条件（{after}）で通し、前後の処理への受け渡しを確かめる"
