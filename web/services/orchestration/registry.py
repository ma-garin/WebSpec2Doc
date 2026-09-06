"""名前 → エージェント。指揮者はここ以外からエージェントを作らない。

指揮者（O2）が持つのは「名前の並び」だけにする。エージェントの実体を
指揮者が import すると、システムを 1 つ足すたびに状態機械を触ることになる。
"""

from __future__ import annotations

from web.services.orchestration.agents.docs_agent import DocsAgent
from web.services.orchestration.agents.healing_agent import HealingAgent
from web.services.orchestration.agents.run_agent import RunAgent
from web.services.orchestration.agents.tests_agent import TestsAgent
from web.services.orchestration.ports import SystemAgent

AGENTS: dict[str, SystemAgent] = {
    "docs": DocsAgent(),
    "tests": TestsAgent(),
    "run": RunAgent(),
    "healing": HealingAgent(),
}


def get_agent(name: str) -> SystemAgent:
    """名前でエージェントを引く。未知の名前は日本語で断る。"""
    key = str(name or "").strip()
    if key not in AGENTS:
        known = "・".join(sorted(AGENTS))
        raise ValueError(f"「{name}」というシステムはありません。使えるのは {known} です")
    return AGENTS[key]
