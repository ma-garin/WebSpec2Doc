"""状態遷移の抽出と検査（決定論・LLM 不使用）。結果はすべて候補（CANDIDATE）。

入力は Markdown 文字列か RequirementUnit のリスト。仕様に無い初期状態を補った場合は
provenance=INFERRED を明示する。`records` は他の解析器（decision_table 等）も共用する。
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable

from web.services.docassure.model import CANDIDATE, INFERRED, OBSERVED

_HEAD = re.compile(r"^(#{1,6})\s+(.*)$")
_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])\s+")


def _sha(t: str) -> str:
    return hashlib.sha1(t.encode("utf-8")).hexdigest()[:12]


def location(doc: str, section: str, line: int, text: str) -> dict[str, Any]:
    snip = text.strip()[:120]
    return {"document_id": doc, "section": section, "line_start": line, "line_end": line,
            "snippet": snip, "snippet_hash": _sha(snip)}


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def records(src: Any, document_id: str = "doc") -> list[dict[str, Any]]:
    """文 {kind:'sentence',text,loc} と表の行 {kind:'row',cells,headers,text,loc} に正規化する。"""
    if not isinstance(src, str):
        out = []
        for u in src:
            loc = u.location
            out.append({"kind": "sentence", "text": u.raw_text, "section": loc.section,
                        "loc": location(loc.document_id or document_id, loc.section,
                                        loc.line_start, loc.snippet or u.raw_text)})
        return out
    out, heads, headers, in_code = [], [], None, False
    for no, raw in enumerate(src.splitlines(), start=1):
        line = raw.rstrip()
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = _HEAD.match(line)
        if m:
            lv = len(m.group(1))
            heads = heads[:lv - 1] + [m.group(2).strip()]
            headers = None
            continue
        section = " > ".join(heads)
        if line.lstrip().startswith("|"):
            cells = _cells(line)
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            if headers is None:
                headers = cells
                continue
            out.append({"kind": "row", "cells": cells, "headers": headers, "section": section,
                        "text": " ".join(c for c in cells if c), "loc": location(document_id, section, no, line)})
            continue
        headers = None
        body = _ITEM.sub("", line.strip(), 1)
        for s in re.findall(r"[^。]+。?", body):
            s = s.strip()
            if s:
                out.append({"kind": "sentence", "text": s, "section": section,
                            "loc": location(document_id, section, no, s)})
    return out


# --- 状態遷移 ---
_ST = r"[「『]?([^\s、,「」『』をがはにへ]{1,16}?)[」』]?"
_SENT = re.compile(
    r"^(?:(?P<pre>.+?)(?:とき|場合|際|と)[、,]?\s*)?(?:状態が)?" + _ST.replace("(", "(?P<f>", 1) +
    r"から" + _ST.replace("(", "(?P<t>", 1) + r"(?:へ|に)(?:遷移|移行|変化|変わ|変更)(?P<post>.*)$")
_TERMINAL = re.compile(r"完了|終了|キャンセル|削除|終端|クローズ|Done|Closed|Cancel|解約|廃止|退会|失効", re.I)
_ERROR = re.compile(r"エラー|失敗|異常|例外|拒否|却下|差戻|差し戻|タイムアウト|Error|Fail", re.I)
_INIT = re.compile(r"初期|開始|新規|下書き|作成中|Initial|Start|Draft|Idle", re.I)
_DECL = re.compile(r"状態(?:は|として|:|：)\s*(?:次の|以下の)?[:：]?\s*([^。]+(?:[、,・/／][^。]+)+)")
_FROM_H = re.compile(r"現在|遷移元|元の?状態|From|変更前", re.I)
_TO_H = re.compile(r"遷移先|次状態|次の状態|変更後|To\b|移行先", re.I)
_EV_H = re.compile(r"イベント|契機|トリガ|操作|Event|アクション(?!.*結果)", re.I)
_GUARD_H = re.compile(r"条件|ガード|Guard", re.I)
_ACT_H = re.compile(r"動作|処理|結果|Action|副作用", re.I)


def _split_post(post: str) -> tuple[str, str]:
    guard = ""
    g = re.search(r"(?:ただし|但し)[、,]?(.+?)(?:場合|とき)(?:に限る|のみ)?", post)
    if g:
        guard = g.group(1).strip("、, ")
        post = post[:g.start()] + post[g.end():]
    act = re.sub(r"^(?:し|する|する。)?[、,]?\s*", "", post.strip("。 "))
    return guard, act.strip("、, 。")


def _trans(fr, ev, to, guard, action, loc) -> dict[str, Any]:
    return {"from": fr, "event": ev, "to": to, "guard": guard, "action": action,
            "location": loc, "provenance": OBSERVED}


def _from_row(r: dict) -> dict | None:
    h, c = r["headers"], r["cells"]
    if len(h) != len(c):
        return None
    pick = lambda rx: next((v for k, v in zip(h, c) if rx.search(k)), None)
    fr, to = pick(_FROM_H), pick(_TO_H)
    if not fr or not to:
        return None
    return _trans(fr, pick(_EV_H) or "", to, pick(_GUARD_H) or "", pick(_ACT_H) or "", r["loc"])


def extract(src: Any, document_id: str = "doc") -> dict[str, Any]:
    recs = records(src, document_id)
    trans, declared = [], []
    for r in recs:
        if r["kind"] == "row":
            t = _from_row(r)
            if t:
                trans.append(t)
            continue
        txt = r["text"].rstrip("。")
        d = _DECL.search(txt)
        if d:
            declared += [s.strip("「」『』 ") for s in re.split(r"[、,・/／]|および|と", d.group(1)) if s.strip()]
        m = _SENT.match(txt)
        if m:
            guard, action = _split_post(m.group("post") or "")
            trans.append(_trans(m.group("f"), (m.group("pre") or "").strip("、, "),
                                m.group("t"), guard, action, r["loc"]))
    states = list(dict.fromkeys(declared + [s for t in trans for s in (t["from"], t["to"])]))
    events = list(dict.fromkeys(t["event"] for t in trans if t["event"]))
    initial = None
    if trans:
        named = next((s for s in states if _INIT.search(s)), None)
        if named:
            initial = {"state": named, "provenance": INFERRED, "basis": "名称から初期状態と推定"}
        else:
            initial = {"state": trans[0]["from"], "provenance": INFERRED, "basis": "最初の遷移元を初期状態と推定"}
    return {"states": states, "declared_states": list(dict.fromkeys(declared)), "events": events,
            "transitions": trans, "initial": initial, "status": CANDIDATE}


def _f(kind, sev, title, detail, loc=None, **extra) -> dict[str, Any]:
    return {"kind": kind, "severity": sev, "title": title, "detail": detail,
            "location": loc, "status": CANDIDATE, "provenance": OBSERVED, **extra}


def analyze(graph: dict[str, Any]) -> list[dict[str, Any]]:
    trans, out = graph.get("transitions", []), []
    if not trans:
        return out
    states = graph.get("states", [])
    declared = set(graph.get("declared_states") or [])
    adj: dict[str, list[str]] = {}
    for t in trans:
        adj.setdefault(t["from"], []).append(t["to"])
    init = (graph.get("initial") or {}).get("state")
    seen, stack = set(), [init] if init else []
    while stack:
        s = stack.pop()
        if s not in seen:
            seen.add(s)
            stack += adj.get(s, [])
    for s in states:
        if init and s not in seen:
            out.append(_f("unreachable_state", "high", "到達不能な状態",
                          f"状態「{s}」へは初期状態「{init}」から到達できない（初期状態は推定: INFERRED）", state=s))
        if s not in adj and not _TERMINAL.search(s):
            out.append(_f("dead_end", "medium", "行き止まりの状態",
                          f"状態「{s}」から出る遷移が無く終端状態とも読めない", state=s))
        if declared and s not in declared:
            out.append(_f("undefined_state", "high", "未定義の状態",
                          f"遷移で使われる「{s}」が状態一覧に無い", state=s))
    groups: dict[tuple, list[dict]] = {}
    for t in trans:
        groups.setdefault((t["from"], t["event"]), []).append(t)
    for (fr, ev), ts in groups.items():
        if len(ts) < 2:
            continue
        same = {(t["to"], t["guard"]) for t in ts}
        if len(same) < len(ts):
            out.append(_f("duplicate_transition", "low", "重複した遷移",
                          f"「{fr}」×「{ev}」の同一遷移が {len(ts)} 回書かれている", ts[1]["location"]))
        tos = {t["to"] for t in ts}
        no_guard = [t for t in ts if not t["guard"]]
        if len(tos) > 1 and (len(no_guard) > 1 or len({t["guard"] for t in ts}) < len(ts)):
            out.append(_f("conflicting_transition", "high", "競合する遷移",
                          f"「{fr}」×「{ev}」が条件の区別なく {sorted(tos)} へ分岐する", ts[1]["location"]))
    if not any(_ERROR.search(t["event"] + t["to"] + t["action"]) for t in trans):
        out.append(_f("no_error_path", "medium", "エラー経路なし",
                      "失敗・異常・タイムアウトに対応する遷移が記述されていない"))
    return out
