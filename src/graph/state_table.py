"""状態遷移表（State Table）— ISTQB 状態遷移テストの成果物一式を実測から導く。

遷移の一覧だけでは状態遷移テストの成果物として不足する。ISTQB / ISO 29119-4 が
求めるのは次の 5 点で、本モジュールはそのすべてを report.json の実測から生成する。

1. 状態一覧（初期状態・終了状態の判定を含む）
2. イベント一覧（画面をまたいで正規化した操作）
3. **状態遷移表** = 状態 × イベントの全マトリクス。定義の無いセルは無効遷移
4. **無効遷移の一覧** — 「起きてはいけない遷移」の検証は状態遷移テストの主目的の一つで、
   有効遷移だけを並べた表からは決して得られない
5. 0-switch / 1-switch カバレッジと、それぞれのテストパス

共通ナビゲーション（全状態から使えるイベント）を**除外しない**。遷移図では
可読性のために間引くことがあるが、状態遷移表では「どの状態からでも同じイベントが
受け付けられる」ことこそ表の核心であり、除外すると被覆が欠ける。共通ナビか否かは
`is_common` として印を付けるに留める。

生成は純関数・決定的。観測されていない状態・イベントは作らない（evidence-only）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: 無効遷移（そのイベントがその状態で定義されていない）を表すセル。
INVALID_CELL = "－"

#: 1-switch のテストパスを列挙する上限。組合せで増えるため制限し、超過は必ず報告する。
MAX_ONE_SWITCH_PATHS = 200

EVENT_LINK = "リンク"
EVENT_SUBMIT = "フォーム送信"
#: 画面内アクション（モーダル・タブ・アコーディオンの開閉など）による状態遷移。
EVENT_ACTION = "画面内アクション"
#: pushState / replaceState / hashchange による SPA 遷移。
EVENT_SPA = "SPA遷移"


@dataclass(frozen=True)
class State:
    """1 つの状態。

    URL 単位の画面だけを状態にすると、同じ URL でモーダルが開いている / 閉じている
    といった差が 1 状態に潰れる。`page_states`（クリック等で出現した DOM 状態）を
    子状態として分け、`kind` で由来を示す。
    """

    state_id: str
    title: str
    url: str
    is_initial: bool
    is_final: bool
    #: "screen"（URL 単位の画面） / "modal" / "tabpanel" / "accordion" / "dom_change"
    kind: str = "screen"
    #: 子状態の場合の親画面。画面そのものなら空。
    parent: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_id": self.state_id,
            "title": self.title,
            "url": self.url,
            "is_initial": self.is_initial,
            "is_final": self.is_final,
            "kind": self.kind,
            "parent": self.parent,
        }


@dataclass(frozen=True)
class Event:
    """1 つのイベント（＝操作）。状態をまたいで同一視できる粒度で正規化する。"""

    event_id: str
    kind: str  # EVENT_LINK / EVENT_SUBMIT
    label: str
    #: この イベントを受け付ける状態の数。全状態で受け付けるものが共通ナビ。
    source_count: int
    is_common: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "kind": self.kind,
            "label": self.label,
            "source_count": self.source_count,
            "is_common": self.is_common,
        }


@dataclass(frozen=True)
class Transition:
    """有効遷移 1 件。"""

    from_state: str
    event_id: str
    to_state: str
    action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_state,
            "event": self.event_id,
            "to": self.to_state,
            "action": self.action,
        }


@dataclass(frozen=True)
class InvalidTransition:
    """無効遷移 1 件（状態 × イベントで定義されていない組）。"""

    from_state: str
    event_id: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"from": self.from_state, "event": self.event_id, "reason": self.reason}


@dataclass(frozen=True)
class StateTable:
    """状態遷移表一式。"""

    states: tuple[State, ...]
    events: tuple[Event, ...]
    transitions: tuple[Transition, ...]
    invalid: tuple[InvalidTransition, ...]

    def cell(self, state_id: str, event_id: str) -> str:
        for transition in self.transitions:
            if transition.from_state == state_id and transition.event_id == event_id:
                return transition.to_state
        return INVALID_CELL

    def matrix(self) -> list[dict[str, Any]]:
        """行 = 状態、列 = イベントの表本体。"""
        return [
            {
                "state_id": state.state_id,
                "title": state.title,
                "cells": [
                    {
                        "event_id": event.event_id,
                        "to": self.cell(state.state_id, event.event_id),
                        "valid": self.cell(state.state_id, event.event_id) != INVALID_CELL,
                    }
                    for event in self.events
                ],
            }
            for state in self.states
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "states": [s.to_dict() for s in self.states],
            "events": [e.to_dict() for e in self.events],
            "transitions": [t.to_dict() for t in self.transitions],
            "invalid_transitions": [i.to_dict() for i in self.invalid],
            "matrix": self.matrix(),
        }


# =========================================================================
# 構築
# =========================================================================
def _screen_id(screen: dict[str, Any]) -> str:
    return str(screen.get("page_id", ""))


def _title_of(screen: dict[str, Any]) -> str:
    return str(screen.get("title") or _screen_id(screen))


def _page_states_of(screen: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """画面内アクションで出現した状態を (子状態ID, 元データ) の列で返す。"""
    out: list[tuple[str, dict[str, Any]]] = []
    for page_state in screen.get("page_states") or []:
        if not isinstance(page_state, dict):
            continue
        raw_id = str(page_state.get("state_id") or "").strip()
        if not raw_id:
            continue
        out.append((f"{_screen_id(screen)}#{raw_id}", page_state))
    return out


def _page_state_label(page_state: dict[str, Any]) -> str:
    description = str(page_state.get("description") or "").strip()
    if description:
        return description
    kind = str(page_state.get("kind") or "dom_change")
    return {
        "modal": "モーダル",
        "tabpanel": "タブ",
        "accordion": "アコーディオン",
    }.get(kind, "DOM 変化後の状態")


def _id_for_url(by_id: dict[str, dict[str, Any]], url: str) -> str:
    if not url:
        return ""
    return next((sid for sid, sc in by_id.items() if str(sc.get("url", "")) == url), "")


def _is_common_event(
    event_id: str, event_sources: set[str], states_with_exits: set[str]
) -> bool:
    """遷移元になりうる全状態がそのイベントを受け付けるなら共通ナビとみなす。

    フォーム送信は特定画面にしか存在しないため常に共通ではない。
    """
    if not event_id.startswith("link:"):
        return False
    target = event_id.split(":", 1)[1]
    candidates = states_with_exits - {target}
    if len(candidates) < 2:  # 遷移元が 1 つしかなければ共通か否かを論じない
        return False
    return candidates <= event_sources


def build_state_table(screens: list[dict[str, Any]]) -> StateTable:
    """report.json の screens から状態遷移表を構築する。"""
    valid_screens = [s for s in screens if isinstance(s, dict) and _screen_id(s)]
    if not valid_screens:
        return StateTable((), (), (), ())

    by_id = {_screen_id(s): s for s in valid_screens}
    linked_to: set[str] = set()
    for screen in valid_screens:
        transitions = screen.get("transitions")
        if isinstance(transitions, dict):
            linked_to.update(str(t) for t in (transitions.get("to") or []))

    # ---- 状態 ----
    # 他から張られていない画面を初期状態とする。ただしトップへ戻る導線が全画面に
    # あるサイトでは該当が 0 件になるため、その場合は観測の起点（先頭の画面）を採る。
    unlinked = [_screen_id(s) for s in valid_screens if _screen_id(s) not in linked_to]
    initial_ids = set(unlinked) or {_screen_id(valid_screens[0])}
    screen_states = [
        State(
            state_id=_screen_id(screen),
            title=_title_of(screen),
            url=str(screen.get("url", "")),
            is_initial=_screen_id(screen) in initial_ids,
            is_final=not ((screen.get("transitions") or {}).get("to") or []),
            kind="screen",
        )
        for screen in valid_screens
    ]
    # 画面内アクションで出現した DOM 状態を子状態として分ける。URL は同じでも
    # 「モーダルが開いている」状態は別状態であり、潰すと遷移の被覆が実態と合わない。
    child_states: list[State] = []
    for screen in valid_screens:
        for child_id, page_state in _page_states_of(screen):
            child_states.append(
                State(
                    state_id=child_id,
                    title=f"{_title_of(screen)}／{_page_state_label(page_state)}",
                    url=str(screen.get("url", "")),
                    is_initial=False,
                    # 閉じる操作は観測できていないため、出口なしとして扱う（捏造しない）。
                    is_final=True,
                    kind=str(page_state.get("kind") or "dom_change"),
                    parent=_screen_id(screen),
                )
            )
    states = tuple([*screen_states, *child_states])

    # ---- イベントと有効遷移 ----
    transitions: list[Transition] = []
    link_sources: dict[str, set[str]] = {}
    submit_sources: dict[str, set[str]] = {}
    event_labels: dict[str, tuple[str, str]] = {}  # event_id -> (kind, label)

    for screen in valid_screens:
        source = _screen_id(screen)
        # 画面内アクション（モーダル等）による親→子の遷移
        for index, (child_id, page_state) in enumerate(_page_states_of(screen), start=1):
            event_id = f"action:{source}:{index}"
            event_labels[event_id] = (
                EVENT_ACTION,
                f"「{_title_of(screen)}」で {_page_state_label(page_state)} を開く"
                f"（{page_state.get('trigger_selector') or 'セレクタ未記録'}）",
            )
            submit_sources.setdefault(event_id, set()).add(source)
            transitions.append(
                Transition(
                    from_state=source,
                    event_id=event_id,
                    to_state=child_id,
                    action=str(page_state.get("trigger_selector") or ""),
                )
            )
        # SPA 遷移（pushState / replaceState / hashchange）
        for spa in screen.get("spa_transitions") or []:
            if not isinstance(spa, dict):
                continue
            target_id = _id_for_url(by_id, str(spa.get("to_url") or ""))
            if not target_id:
                continue
            event_id = f"spa:{target_id}"
            event_labels[event_id] = (
                EVENT_SPA,
                f"{spa.get('kind') or 'pushstate'} で「{_title_of(by_id[target_id])}」へ遷移する",
            )
            link_sources.setdefault(event_id, set()).add(source)
            transitions.append(
                Transition(
                    from_state=source,
                    event_id=event_id,
                    to_state=target_id,
                    action=str(spa.get("to_url") or ""),
                )
            )
        for target in (screen.get("transitions") or {}).get("to") or []:
            target_id = str(target)
            if target_id not in by_id:
                continue
            event_id = f"link:{target_id}"
            event_labels[event_id] = (
                EVENT_LINK,
                f"「{_title_of(by_id[target_id])}」へのリンクを押す",
            )
            link_sources.setdefault(event_id, set()).add(source)
            transitions.append(
                Transition(
                    from_state=source,
                    event_id=event_id,
                    to_state=target_id,
                    action=str(by_id[target_id].get("url", "")),
                )
            )
        for index, form in enumerate(screen.get("forms") or [], start=1):
            if not isinstance(form, dict):
                continue
            method = str(form.get("method") or "GET").upper()
            action = str(form.get("action") or "")
            event_id = f"submit:{source}:{index}"
            event_labels[event_id] = (
                EVENT_SUBMIT,
                f"「{_title_of(screen)}」のフォームを {method} 送信する",
            )
            submit_sources.setdefault(event_id, set()).add(source)
            target_id = next(
                (sid for sid, sc in by_id.items() if str(sc.get("url", "")) == action), ""
            )
            transitions.append(
                Transition(
                    from_state=source,
                    event_id=event_id,
                    to_state=target_id or source,
                    action=action or "(遷移先未観測・同一画面に留まる想定)",
                )
            )

    sources = {**link_sources, **submit_sources}
    # 共通ナビの判定は「割合」ではなく「取りうる遷移元をすべて満たすか」で行う。
    # 割合を閾値にすると、画面数が少ないサイトで通常のリンクまで共通ナビ扱いになる。
    # 遷移元になりうるのは、外向きの遷移を 1 つでも持つ状態（自分自身は除く）。
    states_with_exits = {
        _screen_id(s) for s in valid_screens if (s.get("transitions") or {}).get("to")
    }
    events = tuple(
        Event(
            event_id=event_id,
            kind=event_labels[event_id][0],
            label=event_labels[event_id][1],
            source_count=len(sources[event_id]),
            is_common=_is_common_event(event_id, sources[event_id], states_with_exits),
        )
        for event_id in sorted(sources)
    )

    # ---- 無効遷移（表の空セル）----
    defined = {(t.from_state, t.event_id) for t in transitions}
    invalid: list[InvalidTransition] = []
    for state in states:
        for event in events:
            if (state.state_id, event.event_id) in defined:
                continue
            reason = (
                "この画面には当該フォームが存在しない"
                if event.kind == EVENT_SUBMIT
                else "この画面から当該画面へのリンクが観測されていない"
            )
            invalid.append(InvalidTransition(state.state_id, event.event_id, reason))

    return StateTable(
        states=states,
        events=events,
        transitions=tuple(transitions),
        invalid=tuple(invalid),
    )


# =========================================================================
# カバレッジ
# =========================================================================
def zero_switch_paths(table: StateTable) -> tuple[dict[str, Any], ...]:
    """0-switch: 各有効遷移を 1 回ずつ通るテストパス。"""
    return tuple(
        {
            "path_id": f"SW0-{index:02d}",
            "steps": [t.from_state, t.to_state],
            "event": t.event_id,
            "expected": f"{t.to_state} へ遷移する",
        }
        for index, t in enumerate(table.transitions, start=1)
    )


def one_switch_paths(
    table: StateTable,
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]]:
    """1-switch: 連続する 2 遷移の全組合せ。

    上限を超えた分は件数だけでなく**どの経路を捨てたか**を返す。件数しか残さないと
    「打ち切った」ことは分かっても、後から手動で補うべき対象が特定できない。
    """
    by_source: dict[str, list[Transition]] = {}
    for transition in table.transitions:
        by_source.setdefault(transition.from_state, []).append(transition)

    paths: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for first in table.transitions:
        for second in by_source.get(first.to_state, []):
            entry = {
                "steps": [first.from_state, first.to_state, second.to_state],
                "events": [first.event_id, second.event_id],
                "expected": f"{second.to_state} へ到達する",
            }
            if len(paths) >= MAX_ONE_SWITCH_PATHS:
                dropped.append({**entry, "reason": f"上限 {MAX_ONE_SWITCH_PATHS} 件を超過"})
                continue
            paths.append({"path_id": f"SW1-{len(paths) + 1:02d}", **entry})
    return tuple(paths), tuple(dropped)


def invalid_transition_cases(table: StateTable) -> tuple[dict[str, Any], ...]:
    """無効遷移の検証ケース。

    「導線が画面に無い」ことの確認だけでは不十分で、URL を直接開けば到達できて
    しまう場合がある。認可の観点ではむしろ後者が本命なので、UI 上の確認と
    直接アクセスの確認を必ず 2 本立てで出す。
    """
    url_of = {s.state_id: s.url for s in table.states}
    label_of = {e.event_id: e.label for e in table.events}
    cases: list[dict[str, Any]] = []
    for index, item in enumerate(table.invalid, start=1):
        target = _event_target(item.event_id)
        target_url = url_of.get(target, "")
        direct = (
            {
                "applicable": True,
                "steps": [
                    f"{item.from_state} を開いた状態のセッションを保つ",
                    f"アドレスバーに {target_url} を直接入力して開く",
                ],
                "expected": (
                    "認可が必要な画面なら拒否または認証要求になる。到達できる場合は"
                    "「導線が無いだけで誰でも開ける」ことを意味するため、意図した設計か確認する"
                ),
            }
            if target_url
            else {
                "applicable": False,
                "reason": "遷移先が URL を持たない操作（フォーム送信・画面内アクション）のため直接アクセスの概念がない",
            }
        )
        cases.append(
            {
                "case_id": f"INV-{index:02d}",
                "state": item.from_state,
                "event": item.event_id,
                "event_label": label_of.get(item.event_id, item.event_id),
                "reason": item.reason,
                "ui_check": {
                    "steps": [f"{item.from_state} を開く", "画面上の操作導線を確認する"],
                    "expected": "当該操作の導線が画面上に存在しない（存在すれば設計との不一致）",
                },
                "direct_access_check": direct,
                "expected": "導線が存在せず、かつ直接アクセスが意図どおりに制御されている",
            }
        )
    return tuple(cases)


def _event_target(event_id: str) -> str:
    """イベント ID から遷移先の状態 ID を取り出す（link/spa のみ意味を持つ）。"""
    if event_id.startswith(("link:", "spa:")):
        return event_id.split(":", 1)[1]
    return ""


# =========================================================================
# 統合エントリ
# =========================================================================
def build_state_transition_report(screens: list[dict[str, Any]]) -> dict[str, Any]:
    """画面一覧から状態遷移テストの成果物一式を返す。"""
    table = build_state_table(screens)
    if not table.states:
        return {
            "applicable": False,
            "reason": "状態（画面）が観測されていません。",
        }
    zero = zero_switch_paths(table)
    one, dropped = one_switch_paths(table)
    invalid_cases = invalid_transition_cases(table)
    cell_total = len(table.states) * len(table.events)
    return {
        "applicable": True,
        "technique": "状態遷移テスト",
        **table.to_dict(),
        "summary": {
            "state_count": len(table.states),
            "event_count": len(table.events),
            "valid_transition_count": len(table.transitions),
            "invalid_transition_count": len(table.invalid),
            "cell_total": cell_total,
            "initial_states": [s.state_id for s in table.states if s.is_initial],
            "final_states": [s.state_id for s in table.states if s.is_final],
            "common_events": [e.event_id for e in table.events if e.is_common],
            "screen_state_count": len([s for s in table.states if s.kind == "screen"]),
            "child_state_count": len([s for s in table.states if s.kind != "screen"]),
        },
        "coverage": {
            "zero_switch": {
                "paths": list(zero),
                "count": len(zero),
                "description": "各有効遷移を 1 回以上通る（0-switch 被覆）",
            },
            "one_switch": {
                "paths": list(one),
                "count": len(one),
                "dropped": len(dropped),
                "dropped_paths": list(dropped),
                "description": "連続する 2 遷移の全組合せを通る（1-switch 被覆）",
            },
            "invalid": {
                "cases": list(invalid_cases),
                "count": len(invalid_cases),
                "description": "定義されていない状態 × イベントに導線が無いことを確認する",
            },
        },
        "notice": (
            f"1-switch のテストパスを上限 {MAX_ONE_SWITCH_PATHS} 件で打ち切り、"
            f"{len(dropped)} 件を除外した（除外した経路は dropped_paths に全件記録している）。"
            if dropped
            else ""
        ),
    }
