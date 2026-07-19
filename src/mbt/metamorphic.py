"""メタモルフィック関係（MR）に基づく検証候補の生成。

期待値（オラクル）が無くても、**複数の実行結果の間に成り立つべき関係**は
検証できる（Chen et al., ACM Computing Surveys 2018）。evidence-only 原則の
「正解を知らない」制約を保ったまま検証を増やせる、本システムと相性の良い技法。

生成するのは「この画面でこの関係が成り立つはず」という**検証候補**であり、
実行・判定は利用者のレビューを経てから行う。関係の根拠となった実測要素
（フォーム・選択肢・リンク）を必ず併記する。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

CLAIM_SCOPE = "relation_candidates_from_measured_elements"

CLAIM_NOTICE = (
    "本候補は実測した画面要素から機械的に導いた検証関係の案であり、"
    "対象システムの仕様がこの関係を保証すると断定するものではない。"
)

MR_FILTER_SUBSET = "filter_subset"
MR_SORT_INVARIANCE = "sort_invariance"
MR_PAGINATION_CONSISTENCY = "pagination_consistency"
MR_VIEWPORT_CONSISTENCY = "viewport_consistency"

_SEARCH_HINTS = ("search", "q", "query", "keyword", "検索")
_SORT_HINTS = ("sort", "order", "並び", "順")
_PAGINATION_HINTS = re.compile(r"[?&]page=|/page/|ページ|次へ|next", re.IGNORECASE)


def build_metamorphic_candidates(report: dict[str, Any]) -> dict[str, Any]:
    """report.json の実測要素から、適用できそうなMR候補を列挙する。"""
    candidates: list[dict[str, Any]] = []
    for screen in report.get("screens", []):
        if not isinstance(screen, dict):
            continue
        candidates.extend(_candidates_for_screen(screen))

    for index, candidate in enumerate(candidates, 1):
        candidate["mr_id"] = f"MR-{index:03d}"

    return {
        "meta": {"claim_scope": CLAIM_SCOPE, "claim_notice": CLAIM_NOTICE},
        "candidates": candidates,
        "summary": _summary(candidates),
    }


def _candidates_for_screen(screen: dict[str, Any]) -> list[dict[str, Any]]:
    page_id = str(screen.get("page_id", ""))
    page_url = str(screen.get("url", ""))
    found: list[dict[str, Any]] = []

    search_fields = _fields_matching(screen, _SEARCH_HINTS, types=("text", "search"))
    filter_fields = _select_fields(screen, exclude_hints=_SORT_HINTS)
    sort_fields = _fields_matching(screen, _SORT_HINTS, types=("select", "radio"))
    has_pagination = any(_PAGINATION_HINTS.search(str(link)) for link in screen.get("links", []))

    if search_fields and filter_fields:
        found.append(
            _candidate(
                MR_FILTER_SUBSET,
                page_id,
                page_url,
                relation="絞り込みあり検索の結果集合 ⊆ 絞り込みなし検索の結果集合",
                procedure=(
                    "同一キーワードで、(1) 絞り込みなし (2) 絞り込みあり の2回検索し、"
                    "(2) の結果がすべて (1) に含まれることを確認する"
                ),
                evidence={
                    "search_fields": search_fields,
                    "filter_fields": [f["name"] for f in filter_fields],
                },
            )
        )
    if sort_fields:
        found.append(
            _candidate(
                MR_SORT_INVARIANCE,
                page_id,
                page_url,
                relation="並び順を変えても、結果の要素集合と件数は不変",
                procedure=(
                    "並び順の各選択肢で同一条件の一覧を取得し、"
                    "件数と要素集合（順序以外）が一致することを確認する"
                ),
                evidence={"sort_fields": sort_fields},
            )
        )
    if has_pagination:
        found.append(
            _candidate(
                MR_PAGINATION_CONSISTENCY,
                page_id,
                page_url,
                relation="全ページの件数合計 = 表示された総件数 / ページ間で要素は重複しない",
                procedure=(
                    "全ページを巡回して件数を合計し、総件数表示と一致すること、"
                    "同一要素が複数ページに現れないことを確認する"
                ),
                evidence={"pagination_links_detected": True},
            )
        )
    return found


def save_metamorphic_candidates(payload: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "metamorphic_checks.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"metamorphic_checks_json": path}


# ─────────────────── 内部 ───────────────────


def _candidate(
    mr_type: str,
    page_id: str,
    page_url: str,
    *,
    relation: str,
    procedure: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "mr_type": mr_type,
        "page_id": page_id,
        "page_url": page_url,
        "relation": relation,
        "procedure": procedure,
        "evidence": evidence,
        "claim_scope": CLAIM_SCOPE,
    }


def _fields_matching(
    screen: dict[str, Any], hints: tuple[str, ...], types: tuple[str, ...]
) -> list[str]:
    names: list[str] = []
    for field in _all_fields(screen):
        name = str(field.get("name", ""))
        field_type = str(field.get("field_type", ""))
        if field_type not in types:
            continue
        lowered = name.lower()
        if any(hint in lowered for hint in hints):
            names.append(name)
    return names


def _select_fields(screen: dict[str, Any], exclude_hints: tuple[str, ...]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for field in _all_fields(screen):
        if str(field.get("field_type", "")) != "select":
            continue
        name = str(field.get("name", "")).lower()
        if any(hint in name for hint in exclude_hints):
            continue
        if len([v for v in field.get("options", []) if str(v)]) >= 2:
            fields.append(field)
    return fields


def _all_fields(screen: dict[str, Any]) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for form in screen.get("forms", []):
        if isinstance(form, dict):
            collected.extend(f for f in form.get("fields", []) if isinstance(f, dict))
    return collected


def _summary(candidates: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(candidates),
        MR_FILTER_SUBSET: 0,
        MR_SORT_INVARIANCE: 0,
        MR_PAGINATION_CONSISTENCY: 0,
    }
    for candidate in candidates:
        key = str(candidate.get("mr_type", ""))
        if key in summary:
            summary[key] += 1
    return summary
