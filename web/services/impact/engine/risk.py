"""影響度・発生可能性・優先度（DD-004 risk.py、BD「発生可能性の決め方」）。"""
from __future__ import annotations

from .text import HARM, SHARED, norm

KIND_BASE = {"delete": (3, "削除"), "modify": (3, "条件変更"), "text": (3, "条件変更"), "add": (2, "追加")}
DEPTH_PENALTY = {0: 0, 1: 0, 2: 1}


def impact_level(text: str, doc_kind: str, evidence: list[dict], llm_level: int | None = None) -> tuple[int, str]:
    """LLM 判定があればその値。無ければ規則: 変わった規則の語 3／つながり・意味の近さ 2／それ以外 1、
    共有の語で +1（最大 3）、害の大きい語で 4、テストケースは最大 3。"""
    t = norm(text)
    parts = []
    if llm_level is not None:
        level = max(1, min(int(llm_level), 4))
        parts.append("LLM の判定")
    else:
        details = [e.get("detail", "") for e in evidence]
        if any(d == "変更箇所そのもの" or "差分語" in d for d in details):
            level = 3
            parts.append("変わった規則の語に触れる")
        elif any(e.get("type") in ("link", "semantic") for e in evidence):
            level = 2
            parts.append("つながり・内容の近さで到達")
        else:
            level = 1
            parts.append("主題の語だけが一致")
        shared = [w for w in SHARED if w in t]
        if shared:
            level = min(level + 1, 3)
            parts.append(f"「{shared[0]}」とあり同じ部品を使う")
        harm = [w for w in HARM if w in t]
        if harm and level >= 2:
            level = 4
            parts.append(f"{harm[0]}に関わる")
    if doc_kind == "testcase" and level > 3:
        level = 3
        parts.append("テストケースは最大 3")
    return level, f"影響度 {level}（{'・'.join(parts)}）"


def likelihood(change_kind: str, wording_only: bool, depth: int, has_test: bool) -> tuple[int, str]:
    """L = 変更の種類の基準値 − 段数の減点 + テストなしの加点、を 1〜3 に丸める。"""
    if wording_only:
        base, label = 1, "文言のみ"
    else:
        base, label = KIND_BASE.get(change_kind, (3, "条件変更"))
    d = max(int(depth or 0), 0)
    pen = DEPTH_PENALTY.get(d, 2)
    expr = f"{label} {base}"
    if d >= 1:
        expr += f" − {d} 段目 {pen}"
    value = base - pen
    if not has_test:
        value += 1
        expr += " ＋ テストなし 1"
    value = max(1, min(value, 3))
    return value, f"発生可能性 {value}（{expr}）"


def priority(risk: int, p1_min: int, p2_min: int) -> int:
    if risk >= p1_min:
        return 1
    if risk >= p2_min:
        return 2
    return 3
