"""目標 → 段の列。指揮者はここ以外から段の並びを作らない。

指揮者（状態機械）が知っているのは「N 段の列を順に進める」ことだけで、
どの目標がどの段を持つかはこの表にしかない。目標を増やすときはここへ 1 行足す。
状態機械には触らない。

onboard（保守下に置く）は 01・02 のアダプタが揃った時点で通せるようになった。
「まだ通せない目標」を持つ余地は残す（AVAILABLE_GOALS に無い目標は API が断り、
画面には理由が出る）。
"""

from __future__ import annotations

from typing import Any

from web.services.orchestration.registry import get_agent

#: 目標 → 段の名前の列。名前は registry.AGENTS の鍵と対応する。
GOALS: dict[str, tuple[str, ...]] = {
    "daily": ("run", "healing"),
    "onboard": ("docs", "tests", "run", "healing"),
}

#: 目標の見出し。画面にそのまま出るので内部用語を使わない。
GOAL_LABELS: dict[str, str] = {
    "daily": "今すぐ全部回す",
    "onboard": "保守下に置く",
}

#: いま通せる目標。ここに無いものは API が 400 で断る。
AVAILABLE_GOALS: tuple[str, ...] = ("daily", "onboard")

#: まだ通せない目標があるときの理由。人が読む 1 文。
UNAVAILABLE_REASON = "この目標はまだ使えません"


def steps_for(goal: str) -> tuple[str, ...]:
    """目標の段の列を返す。未知・未対応の目標は日本語で断る。"""
    key = str(goal or "").strip()
    if key not in GOALS:
        known = "・".join(sorted(GOALS))
        raise ValueError(f"「{goal}」という目標はありません。使えるのは {known} です")
    if key not in AVAILABLE_GOALS:
        label = GOAL_LABELS.get(key, key)
        raise ValueError(f"「{label}」はまだ使えません。{UNAVAILABLE_REASON}")
    return GOALS[key]


def step_labels(goal: str) -> list[str]:
    """段の見出しの並び。エージェントが持つ label をそのまま使う。

    見出しをこの表に写し取ると、システム側で名前を変えたときに
    画面だけ古い名前を出し続ける。出どころを 1 つにする。
    """
    return [get_agent(name).label for name in GOALS.get(str(goal or "").strip(), ())]


def catalog() -> list[dict[str, Any]]:
    """画面と API に出す目標の一覧。"""
    items: list[dict[str, Any]] = []
    for goal, _names in GOALS.items():
        entry: dict[str, Any] = {"id": goal, "label": GOAL_LABELS.get(goal, goal)}
        if goal in AVAILABLE_GOALS:
            entry["steps"] = step_labels(goal)
            entry["available"] = True
        else:
            entry["available"] = False
            entry["reason"] = UNAVAILABLE_REASON
        items.append(entry)
    return items
