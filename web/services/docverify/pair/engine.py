"""要件定義書⇔基本設計書の対検査。検出器を順に通し、指摘と追跡リンクを返す。

LLM・ネットワークを使わない決定的な検査だけで構成する。
検出器が例外を出しても他の検出器は続け、失敗は errors に名前と内容を残す。
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256

from . import contradiction, link, semantic, single, table, terms
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


def _semantic_on(errors: list[dict]) -> bool:
    """二段目（埋め込み）を使うか。使えないときは errors に理由を足す（明示 off は足さない）。"""
    if semantic.disabled():
        return False
    if not semantic.available():
        errors.append({"detector": "semantic", "error": semantic.NO_KEY_ERROR})
        return False
    return True


def _generic_links(baseline: list[Unit], target: list[Unit]) -> list[tuple[Unit, Unit, float]]:
    """Literal text correspondence candidates, independent of document type and heading vocabulary."""
    if not baseline or not target:
        return []
    index = link._Index([u.text for u in [*baseline, *target]])
    right = [(u, index.vec(u.text)) for u in target]
    found = []
    for unit in baseline:
        vector = index.vec(unit.text)
        scores = [(other, link._cos(vector, vec)) for other, vec in right]
        best = max((score for _, score in scores), default=0)
        found.extend((unit, other, score) for other, score in scores if score >= 0.35 and score >= best * 0.5)
    return found


def inspect(req_md: str, design_md: str, purpose: str = "legacy_requirement_design") -> dict:
    """2 文書を検査し {"defects", "links", "errors"} を返す。"""
    req_all, des_all = segment(req_md), segment(design_md)
    legacy = purpose == "legacy_requirement_design"
    reqs = requirement_units(req_all) if legacy else req_all
    errors: list[dict] = []
    # 注記・表題・章の導入文を除いた、追跡の対象になる要件だけでリンクを張る
    targets = _run("targets", link.targets, errors, reqs) if legacy else reqs
    links = _run("link", link.link if legacy else _generic_links, errors, targets, des_all)
    defects = []
    if legacy or purpose == "coverage":
        defects = [{"type": "MISSING_IN_DESIGN", "req_lines": _span(u), "design_lines": [],
                    "reason": "対応する記述が確認対象に見つからない"}
                   for u in _run("missing", link.missing, errors, targets, links)]
    use_sem = _semantic_on(errors) if legacy else False
    if legacy:
        extra_fn, extra_name = (semantic.extra, "semantic_extra") if use_sem else (link.extra, "extra")
        defects += [{"type": "EXTRA_IN_DESIGN", "req_lines": [], "design_lines": _span(u),
                     "reason": "根拠となる要件が見つからない"}
                    for u in _run(extra_name, extra_fn, errors, des_all, targets, links)]
    defects += _run("contradiction", contradiction.detect, errors, reqs, des_all, links)
    defects += _run("table", table.detect, errors, req_all, des_all)
    defects += _run("terms", terms.detect, errors, req_all, des_all, links)
    if use_sem:
        defects += _run("semantic_terms", semantic.term_defects, errors, req_all, des_all, links)
    if legacy:
        defects += _run("single", single.detect, errors, reqs)
    # 設計に対応の無い要件も、追跡表では「反映なし」の行として残す
    unlinked = [{"req_lines": d["req_lines"], "design_lines": []}
                for d in defects if d["type"] == "MISSING_IN_DESIGN"]
    reasons = []
    if purpose not in ("legacy_requirement_design", "consistency", "coverage"):
        reasons.append("選択された検査目的に対応する検査器がありません。")
    if not targets:
        reasons.append("判定不能（検査対象 0 件）: 基準側から検査対象を抽出できませんでした。")
    if not des_all:
        reasons.append("判定不能（検査対象 0 件）: 確認対象から検査対象を抽出できませんでした。")
    if not links:
        reasons.append("比較可能な記述の対応がなく、文書間の検査を実行できませんでした。")
    if errors:
        reasons.append("一部の検査が未実行または失敗しました。")
    assessment = {"purpose": purpose, "status": "unverified" if reasons else "complete",
                  "baseline_units": len(targets), "target_units": len(des_all),
                  "compared_pairs": len(links), "reasons": reasons,
                  "unverified_reason": reasons[0] if reasons else None,
                  "detectors": ["contradiction", "table", "terms"] + (["missing"] if purpose == "coverage" else []),
                  "limits": ["意味全体の整合性や同義表現の網羅性は未検証です。"],
                  "baseline_sha256": sha256(req_md.encode()).hexdigest(),
                  "target_sha256": sha256(design_md.encode()).hexdigest()}
    return {"defects": _dedupe(defects), "links": _links_out(links) + unlinked,
            "errors": errors, "assessment": assessment}
