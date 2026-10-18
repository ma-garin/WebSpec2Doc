"""要件定義書⇔基本設計書の対検査。検出器を順に通し、指摘と追跡リンクを返す。

LLM・ネットワークを使わない決定的な検査だけで構成する。
検出器が例外を出しても他の検出器は続け、失敗は errors に名前と内容を残す。
"""
from __future__ import annotations

from collections import defaultdict

from . import contradiction, link, single, table, terms
from .segment import Unit, requirement_units, segment


def _span(u: Unit) -> list[int]:
    return [u.start, u.end]


def _run(name: str, fn, errors: list[dict], *args) -> list:
    try:
        return list(fn(*args))
    except Exception as exc:  # 検出器 1 つの失敗で全体を止めない
        errors.append({"detector": name, "error": f"{type(exc).__name__}: {exc}"})
        return []


def _links_out(links: list[tuple[Unit, Unit, float]]) -> list[dict]:
    grouped: dict[tuple[int, int], list[list[int]]] = defaultdict(list)
    for req, des, _score in links:
        span = _span(des)
        if span not in grouped[(req.start, req.end)]:
            grouped[(req.start, req.end)].append(span)
    return [{"req_lines": list(k), "design_lines": sorted(v)} for k, v in sorted(grouped.items())]


def _dedupe(defects: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for d in defects:
        key = (d["type"], tuple(d.get("req_lines") or ()), tuple(d.get("design_lines") or ()))
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def inspect(req_md: str, design_md: str) -> dict:
    """2 文書を検査し {"defects", "links", "errors"} を返す。"""
    req_all, des_all = segment(req_md), segment(design_md)
    reqs = requirement_units(req_all)
    errors: list[dict] = []
    # 注記・表題・章の導入文を除いた、追跡の対象になる要件だけでリンクを張る
    targets = _run("targets", link.targets, errors, reqs)
    links = _run("link", link.link, errors, targets, des_all)
    defects = [{"type": "MISSING_IN_DESIGN", "req_lines": _span(u), "design_lines": [],
                "reason": "対応する設計が見つからない"}
               for u in _run("missing", link.missing, errors, targets, links)]
    defects += [{"type": "EXTRA_IN_DESIGN", "req_lines": [], "design_lines": _span(u),
                 "reason": "根拠となる要件が見つからない"}
                for u in _run("extra", link.extra, errors, des_all, targets, links)]
    defects += _run("contradiction", contradiction.detect, errors, reqs, des_all, links)
    defects += _run("table", table.detect, errors, req_all, des_all)
    defects += _run("terms", terms.detect, errors, req_all, des_all, links)
    defects += _run("single", single.detect, errors, reqs)
    # 設計に対応の無い要件も、追跡表では「反映なし」の行として残す
    unlinked = [{"req_lines": d["req_lines"], "design_lines": []}
                for d in defects if d["type"] == "MISSING_IN_DESIGN"]
    return {"defects": _dedupe(defects), "links": _links_out(links) + unlinked, "errors": errors}
