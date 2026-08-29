"""ユーザビリティスメルの検出（Kobold, IJHCS 2017 の観測ベース手法）。

実測したユーザー操作イベント列から、ユーザビリティ問題の兆候（スメル）を検出する。
ペルソナ評価と異なり、実際に観測されたイベントだけを根拠にする。

検出するのは兆候のみで、**改善提案（Koboldのrefactoring相当）はしない**。
対処は人に委ねる。各検出には実測数値（何回・どの経路で）を必ず添える。

入力イベントは reverse_generator と同じ形式:
  {session, kind, path, url, selector, action_type, state_id, ...}
  kind: "navigate" / "action" / ...
  action_type: "click" / "input" / "scroll" / ...

主張境界: 観測した操作シグナルに現れた兆候であり、ユーザビリティ問題の確定ではない。
"""

from __future__ import annotations

from collections import Counter
from typing import Any

CLAIM_SCOPE = "observed_interaction_signals_only"

CLAIM_NOTICE = (
    "本結果は実測した操作イベントに現れた兆候であり、"
    "ユーザビリティ問題であることを確定するものではない。改善提案は含まない。"
)

SMELL_MISCLICK = "repeated_misclick"
SMELL_FORM_ABANDON = "form_abandonment"
SMELL_POGO_STICKING = "pogo_sticking"
SMELL_EXCESSIVE_SCROLL = "excessive_scroll"

# 閾値（実測イベントに基づく。根拠を検出結果へ必ず添える）
MISCLICK_MIN_REPEAT = 3  # 同一非遷移セレクタへの連続クリック
SCROLL_MIN_BEFORE_ACTION = 5  # 目的操作前のスクロール回数


def detect_smells(session_events: list[dict[str, Any]]) -> dict[str, Any]:
    """セッションイベント列からスメルを検出する。"""
    by_session: dict[str, list[dict[str, Any]]] = {}
    for event in session_events:
        by_session.setdefault(str(event.get("session") or ""), []).append(event)

    smells: list[dict[str, Any]] = []
    for session in sorted(by_session):
        events = by_session[session]
        smells.extend(_misclicks(session, events))
        smells.extend(_form_abandonment(session, events))
        smells.extend(_pogo_sticking(session, events))
        smells.extend(_excessive_scroll(session, events))

    return {
        "meta": {"claim_scope": CLAIM_SCOPE, "claim_notice": CLAIM_NOTICE},
        "smells": smells,
        "summary": _summary(smells),
    }


def _misclicks(session: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一セレクタへの連続クリックのうち、遷移も状態変化も伴わないもの。"""
    smells: list[dict[str, Any]] = []
    run_selector = ""
    run_count = 0

    def flush() -> None:
        if run_count >= MISCLICK_MIN_REPEAT:
            smells.append(
                {
                    "type": SMELL_MISCLICK,
                    "session": session,
                    "selector": run_selector,
                    "occurrences": run_count,
                    "evidence": f"同一要素へ {run_count} 回連続クリック（反応なし）",
                }
            )

    for event in events:
        if str(event.get("action_type")) != "click":
            flush()
            run_selector, run_count = "", 0
            continue
        selector = str(event.get("selector") or "")
        # 状態変化・遷移があれば「無反応クリック」ではない
        reacted = bool(event.get("state_id")) or str(event.get("kind")) == "navigate"
        if selector == run_selector and not reacted:
            run_count += 1
        else:
            flush()
            run_selector = selector
            run_count = 1 if not reacted else 0
    flush()
    return smells


def _form_abandonment(session: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """フォーム入力を始めた後、送信せずに別ページへ離脱したもの。"""
    smells: list[dict[str, Any]] = []
    inputting_path = ""
    for event in events:
        action = str(event.get("action_type"))
        path = str(event.get("path") or "")
        if action == "input":
            inputting_path = path
        elif action == "submit":
            inputting_path = ""
        elif str(event.get("kind")) == "navigate" and inputting_path and path != inputting_path:
            smells.append(
                {
                    "type": SMELL_FORM_ABANDON,
                    "session": session,
                    "path": inputting_path,
                    "evidence": f"{inputting_path} で入力後、送信せず {path} へ離脱",
                }
            )
            inputting_path = ""
    return smells


def _pogo_sticking(session: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A→B→A の短時間往復（行き来）。"""
    smells: list[dict[str, Any]] = []
    nav_path = [
        str(e.get("path") or "")
        for e in events
        if str(e.get("kind")) == "navigate" and str(e.get("path") or "")
    ]
    seen_patterns: set[tuple[str, str]] = set()
    for i in range(len(nav_path) - 2):
        a, b, c = nav_path[i], nav_path[i + 1], nav_path[i + 2]
        if a == c and a != b and (a, b) not in seen_patterns:
            seen_patterns.add((a, b))
            smells.append(
                {
                    "type": SMELL_POGO_STICKING,
                    "session": session,
                    "path": a,
                    "via": b,
                    "evidence": f"{a} → {b} → {a} の往復を観測",
                }
            )
    return smells


def _excessive_scroll(session: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """目的操作（クリック等）前のスクロールが多いページ。"""
    smells: list[dict[str, Any]] = []
    scroll_by_path: Counter[str] = Counter()
    acted_paths: set[str] = set()
    for event in events:
        path = str(event.get("path") or "")
        action = str(event.get("action_type"))
        if action == "scroll" and path not in acted_paths:
            scroll_by_path[path] += 1
        elif action in ("click", "input", "submit"):
            acted_paths.add(path)
            count = scroll_by_path.get(path, 0)
            if count >= SCROLL_MIN_BEFORE_ACTION:
                smells.append(
                    {
                        "type": SMELL_EXCESSIVE_SCROLL,
                        "session": session,
                        "path": path,
                        "occurrences": count,
                        "evidence": f"目的操作前に {count} 回スクロール",
                    }
                )
    return smells


def _summary(smells: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(smells),
        SMELL_MISCLICK: 0,
        SMELL_FORM_ABANDON: 0,
        SMELL_POGO_STICKING: 0,
        SMELL_EXCESSIVE_SCROLL: 0,
    }
    for smell in smells:
        key = str(smell.get("type", ""))
        if key in summary:
            summary[key] += 1
    return summary
