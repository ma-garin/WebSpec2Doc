"""UX 自動エキスパートレビュー（axe-core 検査＋ニールセン 10 原則ヒューリスティック）。

rules 層（axe_runner）は実測由来のため confidence 1.0 固定、
LLM 層（heuristics のニールセン評価）は confidence 0.9 を上限とする。
"""

from __future__ import annotations
