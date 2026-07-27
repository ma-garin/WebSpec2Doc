"""ユースケーステスト — 観測した遷移から基本フロー・代替フロー・例外フローを導く。

状態遷移テストが「遷移を 1 回ずつ通る」被覆であるのに対し、ユースケーステストは
「利用者が目的を達成する一連の流れ」を単位に検証する。ISTQB では仕様ベース技法の
一つで、通常は仕様書のユースケース記述を入力に使う。

本システムは仕様書を前提にできないため、**実測した遷移グラフとフォームから
フロー候補を導く**。目的（ゴール）はシステム側からは判定できないので:

- ゴール候補 = 遷移先を持たない画面（終端）、または送信フォームを持つ画面の遷移先
- 基本フロー = 入口からゴール候補への最短経路
- 代替フロー = 同じゴールへ到達する別経路
- 例外フロー = フォームの検証違反で同じ画面に留まる経路（実測した必須項目から導く）

**フローは候補であり、業務上のユースケースと一致する保証はない。**
その旨を出力に必ず含め、採否はレビューに委ねる（evidence-only）。生成は純関数で決定的。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

TECHNIQUE_USE_CASE = "ユースケーステスト"

#: 1 ユースケースあたりに載せる代替フローの上限。経路は組合せで増えるため制限する。
MAX_ALTERNATIVE_FLOWS = 3
#: 導出するユースケース候補の上限。
MAX_USE_CASES = 10

FLOW_BASIC = "基本フロー"
FLOW_ALTERNATIVE = "代替フロー"
FLOW_EXCEPTION = "例外フロー"


@dataclass(frozen=True)
class Flow:
    """1 本のフロー。`steps` は画面 ID の列。"""

    flow_type: str
    steps: tuple[str, ...]
    description: str
    expected: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.flow_type,
            "steps": list(self.steps),
            "description": self.description,
            "expected": self.expected,
        }


@dataclass(frozen=True)
class UseCase:
    """1 つのユースケース候補。"""

    use_case_id: str
    title: str
    actor: str
    entry: str
    goal: str
    flows: tuple[Flow, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.use_case_id,
            "title": self.title,
            "actor": self.actor,
            "entry": self.entry,
            "goal": self.goal,
            "flows": [f.to_dict() for f in self.flows],
            "case_count": len(self.flows),
        }


# =========================================================================
# グラフ操作
# =========================================================================
def _build_graph(screens: list[dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    graph: dict[str, tuple[str, ...]] = {}
    for screen in screens:
        source = str(screen.get("page_id", ""))
        if not source:
            continue
        transitions = screen.get("transitions")
        targets: list[str] = []
        if isinstance(transitions, dict):
            targets = [str(t) for t in (transitions.get("to") or [])]
        graph[source] = tuple(dict.fromkeys(targets))
    return graph


def _shortest_path(
    graph: dict[str, tuple[str, ...]], start: str, goal: str
) -> tuple[str, ...] | None:
    """幅優先探索。決定的にするため、隣接は観測順のまま辿る。"""
    if start == goal:
        return (start,)
    queue: deque[tuple[str, ...]] = deque([(start,)])
    seen = {start}
    while queue:
        path = queue.popleft()
        for nxt in graph.get(path[-1], ()):
            if nxt in seen:
                continue
            if nxt == goal:
                return (*path, nxt)
            seen.add(nxt)
            queue.append((*path, nxt))
    return None


def _alternative_paths(
    graph: dict[str, tuple[str, ...]], start: str, goal: str, basic: tuple[str, ...]
) -> list[tuple[str, ...]]:
    """基本フローと異なる経路を、経路長の短い順に列挙する（単純路のみ）。"""
    found: list[tuple[str, ...]] = []
    queue: deque[tuple[str, ...]] = deque([(start,)])
    while queue and len(found) < MAX_ALTERNATIVE_FLOWS:
        path = queue.popleft()
        if len(path) > len(basic) + 2:  # 極端に長い迂回は採らない
            continue
        for nxt in graph.get(path[-1], ()):
            if nxt in path:  # 単純路のみ（閉路を辿らない）
                continue
            extended = (*path, nxt)
            if nxt == goal:
                if extended != basic:
                    found.append(extended)
            else:
                queue.append(extended)
    return found


def _screen_index(screens: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(s.get("page_id", "")): s for s in screens if s.get("page_id")}


def _title_of(screen: dict[str, Any] | None, page_id: str) -> str:
    if not screen:
        return page_id
    return str(screen.get("title") or page_id)


def _required_fields(screen: dict[str, Any] | None) -> list[str]:
    if not screen:
        return []
    out: list[str] = []
    for form in screen.get("forms") or []:
        if not isinstance(form, dict):
            continue
        for field in form.get("fields") or []:
            if isinstance(field, dict) and field.get("required"):
                out.append(str(field.get("name") or field.get("label") or ""))
    return [name for name in out if name]


# =========================================================================
# 構築
# =========================================================================
def build_use_cases(screens: list[dict[str, Any]]) -> tuple[UseCase, ...]:
    """遷移グラフからユースケース候補を導く。"""
    graph = _build_graph(screens)
    if not graph:
        return ()
    index = _screen_index(screens)

    targets = {t for ts in graph.values() for t in ts}
    entries = [s for s in graph if s not in targets] or sorted(graph)[:1]
    goals = [s for s, ts in graph.items() if not ts]
    if not goals:  # 終端が無い（循環のみ）場合は、フォームを持つ画面をゴール候補にする
        goals = [s for s in graph if _required_fields(index.get(s))]

    use_cases: list[UseCase] = []
    counter = 0
    for entry in entries:
        for goal in goals:
            if entry == goal:
                continue
            basic = _shortest_path(graph, entry, goal)
            if basic is None:
                continue
            counter += 1
            if counter > MAX_USE_CASES:
                return tuple(use_cases)

            flows: list[Flow] = [
                Flow(
                    flow_type=FLOW_BASIC,
                    steps=basic,
                    description="入口からゴール候補への最短経路",
                    expected=f"「{_title_of(index.get(goal), goal)}」へ到達する",
                )
            ]
            for alternative in _alternative_paths(graph, entry, goal, basic):
                flows.append(
                    Flow(
                        flow_type=FLOW_ALTERNATIVE,
                        steps=alternative,
                        description="同じゴールへ到達する別経路",
                        expected=f"基本フローと同じ「{_title_of(index.get(goal), goal)}」へ到達する",
                    )
                )
            for step in basic:
                required = _required_fields(index.get(step))
                if not required:
                    continue
                flows.append(
                    Flow(
                        flow_type=FLOW_EXCEPTION,
                        steps=(step, step),
                        description=(
                            f"「{_title_of(index.get(step), step)}」で必須項目"
                            f"（{'、'.join(required[:3])}）を空にして送信する"
                        ),
                        expected="同じ画面に留まり、必須エラーが表示される。入力済みの値は失われない",
                    )
                )

            use_cases.append(
                UseCase(
                    use_case_id=f"UC{counter}",
                    title=(
                        f"{_title_of(index.get(entry), entry)} から "
                        f"{_title_of(index.get(goal), goal)} まで"
                    ),
                    actor="利用者（観測されたセッションの権限）",
                    entry=entry,
                    goal=goal,
                    flows=tuple(flows),
                )
            )
    return tuple(use_cases)


# =========================================================================
# 統合エントリ
# =========================================================================
def use_case_testing(screens: list[dict[str, Any]]) -> dict[str, Any]:
    """`techniques.apply_all` から呼ぶ辞書インタフェース。"""
    use_cases = build_use_cases(screens)
    if not use_cases:
        return {
            "applicable": False,
            "technique": TECHNIQUE_USE_CASE,
            "reason": "入口とゴールを結ぶ遷移が観測されていません。",
        }
    total_flows = sum(len(u.flows) for u in use_cases)
    return {
        "applicable": True,
        "technique": TECHNIQUE_USE_CASE,
        "use_cases": [u.to_dict() for u in use_cases],
        "use_case_count": len(use_cases),
        "case_count": total_flows,
        "coverage": (
            f"ユースケース候補 {len(use_cases)} 件・フロー {total_flows} 本"
            "（基本 / 代替 / 例外）"
        ),
        "notice": (
            "フローは観測した遷移から機械的に導いた候補であり、"
            "業務上のユースケースと一致することを保証しない。レビューで採否を判断すること。"
        ),
    }
