"""UX 自動エキスパートレビュー（自社実装の WCAG 検査＋ニールセン 10 原則ヒューリスティック）。

rules 層（a11y）は実測由来のため confidence 1.0 固定、
LLM 層（heuristics のニールセン評価）は confidence 0.9 を上限とする。
"""

from __future__ import annotations
