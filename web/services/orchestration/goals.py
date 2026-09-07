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
    #: 段階承認のあと、解析をやり直さずに続ける（ワークフロー画面の
    #: approve_stage から起こす）。
    "continue": ("tests", "run", "healing"),
    #: 「分析して直す」でコードの場所が無いと分かり、接続先を作った直後に
    #: 起こす（ワークフロー画面の connect から起こす）。解析・テスト設計・
    #: 実行はやり直さず、healing だけをやり直す。
    "heal": ("healing",),
}

#: 目標の見出し。画面にそのまま出るので内部用語を使わない。
GOAL_LABELS: dict[str, str] = {
    "daily": "今すぐ全部回す",
    "onboard": "保守下に置く",
    "continue": "続きから",
    "heal": "分析して直す",
}

#: いま通せる目標。ここに無いものは API が 400 で断る。
AVAILABLE_GOALS: tuple[str, ...] = ("daily", "onboard", "continue", "heal")

#: まだ通せない目標があるときの理由。人が読む 1 文。
UNAVAILABLE_REASON = "この目標はまだ使えません"

#: 目標ごとに「周回」として繰り返す末尾の段の数。daily は全 2 段、onboard は
#: 末尾の run・healing の 2 段だけを繰り返す（docs・tests は初回だけでよい）。
_REPEAT_TAIL: dict[str, int] = {"daily": 2, "onboard": 2}

_MIN_ROUNDS = 1
_MAX_ROUNDS = 5


def _clamp_rounds(rounds: int) -> int:
    try:
        n = int(rounds)
    except (TypeError, ValueError):
        n = 1
    return max(_MIN_ROUNDS, min(_MAX_ROUNDS, n))


def steps_for(goal: str, rounds: int = 1) -> tuple[str, ...]:
    """目標の段の列を返す。未知・未対応の目標は日本語で断る。

    rounds > 1 なら、周回対象の末尾段（_REPEAT_TAIL）を rounds 回繰り返す。
    既定の rounds=1 では従来と同じ列を返す。
    """
    key = str(goal or "").strip()
    if key not in GOALS:
        known = "・".join(sorted(GOALS))
        raise ValueError(f"「{goal}」という目標はありません。使えるのは {known} です")
    if key not in AVAILABLE_GOALS:
        label = GOAL_LABELS.get(key, key)
        raise ValueError(f"「{label}」はまだ使えません。{UNAVAILABLE_REASON}")
    base = GOALS[key]
    tail_len = _REPEAT_TAIL.get(key, 0)
    n = _clamp_rounds(rounds)
    if tail_len <= 0 or n <= 1:
        return base
    head, tail = base[:-tail_len], base[-tail_len:]
    return head + tail * n


def step_names_and_labels(goal: str, rounds: int = 1) -> list[tuple[str, str]]:
    """段の名前と表示名の列。周回対象の段には「（N 周目）」を付ける。

    conductor.start がここから StepRecord を組み立てる。表示名の作り直しを
    2 か所に置かないよう、周回の見出しはここでしか作らない。
    """
    key = str(goal or "").strip()
    names = steps_for(goal, rounds)
    tail_len = _REPEAT_TAIL.get(key, 0)
    n = _clamp_rounds(rounds)
    multi = tail_len > 0 and n > 1
    head_count = len(names) - tail_len * n if multi else len(names)
    result: list[tuple[str, str]] = []
    for index, name in enumerate(names):
        label = get_agent(name).label
        if multi and index >= head_count:
            round_no = (index - head_count) // tail_len + 1
            label = f"{label}（{round_no} 周目）"
        result.append((name, label))
    return result


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
