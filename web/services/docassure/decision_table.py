"""複数条件の仕様から判定表の候補を作る（決定論・LLM 不使用）。結果は CANDIDATE。

条件が 1 変数だけの記述は判定表にしない。原文に無い値（否定側・閾値の反対側）は
INFERRED として values_inferred に分けて出す。組合せが 64 を超えるときは pairwise 候補を出す。
"""
from __future__ import annotations

import itertools
import re
from typing import Any

from web.services.docassure.model import CANDIDATE, INFERRED, OBSERVED
from web.services.docassure.state_transition import records

LIMIT = 64
_RULE = re.compile(r"^(?P<c>.+?)(?:の場合|のとき|場合|なら(?:ば)?|であれば)[、,]?\s*(?P<a>.+)$")
_SPLIT = re.compile(r"(?:、)?(?:かつ|および|で、|であり、|で且つ|、)")
_NUM = re.compile(r"^(?P<n>[\d,]+(?:\.\d+)?)\s*(?P<u>[^\d\s以上下未満超]*)(?P<op>以上|以下|未満|超)$")
_FLIP = {"以上": "未満", "未満": "以上", "以下": "超", "超": "以下"}


def _atom(a: str) -> tuple[str, str] | None:
    a = a.strip(" 、,。")
    if not a:
        return None
    m = re.match(r"^(.{1,16}?)(?:が|は|の)(.+)$", a)
    if m:
        return m.group(1), m.group(2).strip()
    return a, "はい"


def _complement(v: str) -> str | None:
    m = _NUM.match(v.replace(",", ""))
    if m:
        return f"{m.group('n')}{m.group('u')}{_FLIP[m.group('op')]}"
    return "いいえ" if v == "はい" else None


def _pairwise(vars_: list[str], vals: dict[str, list[str]]) -> list[dict[str, str]]:
    todo = {(a, x, b, y) for a, b in itertools.combinations(vars_, 2) for x in vals[a] for y in vals[b]}
    out = []
    while todo:
        best, gain = None, -1
        for combo in itertools.product(*(vals[v] for v in vars_)):
            row = dict(zip(vars_, combo))
            g = sum(1 for (a, x, b, y) in todo if row[a] == x and row[b] == y)
            if g > gain:
                best, gain = row, g
        out.append(best)
        todo = {t for t in todo if not (best[t[0]] == t[1] and best[t[2]] == t[3])}
    return out


def _build(rules: list[dict], section: str) -> dict[str, Any] | None:
    vars_ = list(dict.fromkeys(v for r in rules for v in r["when"]))
    if len(vars_) < 2 or not any(len(r["when"]) >= 2 for r in rules):
        return None
    obs: dict[str, list[str]] = {v: [] for v in vars_}
    for r in rules:
        for v, x in r["when"].items():
            if x not in obs[v]:
                obs[v].append(x)
    vals, inferred = {}, {}
    for v in vars_:
        extra = [c for x in obs[v] if (c := _complement(x)) and c not in obs[v]]
        inferred[v] = list(dict.fromkeys(extra))
        vals[v] = obs[v] + inferred[v]
        if len(vals[v]) < 2:
            vals[v].append("その他")
            inferred[v].append("その他")
    total = 1
    for v in vars_:
        total *= len(vals[v])

    def covers(combo: dict) -> bool:
        return any(all(r["when"].get(v, combo[v]) == combo[v] for v in vars_) for r in rules)

    if total <= LIMIT:
        missing = [dict(zip(vars_, c)) for c in itertools.product(*(vals[v] for v in vars_))
                   if not covers(dict(zip(vars_, c)))]
        mode, pw = "full", []
    else:
        pw = _pairwise(vars_, vals)
        missing = [row for row in pw if not covers(row)]
        mode = "pairwise"
    return {
        "section": section, "conditions": [{"name": v, "values": obs[v], "values_inferred": inferred[v]} for v in vars_],
        "actions": list(dict.fromkeys(r["action"] for r in rules)),
        "rules": [{"when": r["when"], "then": r["action"], "location": r["loc"], "provenance": OBSERVED} for r in rules],
        "missing": [{"when": m, "then": "未定義", "provenance": INFERRED} for m in missing],
        "combination_total": total, "mode": mode, "pairwise": pw if mode == "pairwise" else [],
        "status": CANDIDATE,
    }


def extract(src: Any, document_id: str = "doc") -> list[dict[str, Any]]:
    by_sec: dict[str, list[dict]] = {}
    for r in records(src, document_id):
        if r["kind"] != "sentence":
            continue
        m = _RULE.match(r["text"].rstrip("。"))
        if not m:
            continue
        when = {}
        for part in _SPLIT.split(m.group("c")):
            at = _atom(part)
            if at:
                when[at[0]] = at[1]
        if when:
            by_sec.setdefault(r["section"], []).append(
                {"when": when, "action": m.group("a").strip(" 。"), "loc": r["loc"]})
    return [t for sec, rs in by_sec.items() if (t := _build(rs, sec))]
