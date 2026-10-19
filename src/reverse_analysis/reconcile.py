"""静的 API 候補と runtime 観測の限定突合（純粋関数）。

method/path の完全一致は同一性の証明ではない。既存 snapshot は API の origin を
記録しないため、一意に一致しても classification は inferred に留め、
matched（method/origin/path 等の識別根拠が揃う将来用の予約状態）は出さない。
path の percent decode・末尾 slash 除去・動的 parameter 化・prefix 補完はしない。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import TypeVar

from reverse_analysis.models import (
    BASIS_DYNAMIC_EXPRESSION,
    BASIS_METHOD_MISSING,
    BASIS_METHOD_PATH_ONLY,
    BASIS_PATH_UNRESOLVED,
    BASIS_QUERY_DEPENDENT,
    BASIS_RUNTIME_ONLY,
    BASIS_STATIC_ONLY,
    LIMIT_AUTO_MATCH_WITHHELD,
    LIMIT_MULTIPLE_CANDIDATES,
    LIMIT_MULTIPLE_OBSERVATIONS,
    LIMIT_NO_STATIC_CANDIDATE,
    LIMIT_NOT_IDENTITY_PROOF,
    LIMIT_NOT_OBSERVED,
    LIMIT_RUNTIME_ORIGIN_NOT_RECORDED,
    LIMIT_RUNTIME_QUERY_NOT_RETAINED,
    Relation,
    RuntimeObservation,
    StaticCandidate,
    Summary,
    make_id,
)

_MatchKey = tuple[str, str]
_T = TypeVar("_T", StaticCandidate, RuntimeObservation)
BASIS_ROUTE_STATIC_ONLY = "route_static_only"
ROUTE_LIMITS = ("route_not_compared_to_runtime_api", "route_navigation_not_in_snapshot")
_TEMPLATE_MARKERS = ("${", "{", "}", "`", "*")


def reconcile(
    static_candidates: Iterable[StaticCandidate],
    runtime_observations: Iterable[RuntimeObservation],
) -> tuple[Relation, ...]:
    """API 候補だけを runtime 観測と比べ、関係を決定的な順序で返す。"""
    candidates = _unique(tuple(static_candidates), "静的候補")
    observations = _unique(tuple(runtime_observations), "runtime 観測")
    api_candidates = [c for c in candidates if c.kind == "api"]

    relations: list[Relation] = []
    eligible: dict[_MatchKey, list[StaticCandidate]] = defaultdict(list)
    for candidate in api_candidates:
        reason = _unknown_reason(candidate)
        if reason is None:
            eligible[(_normalize_method(candidate.method), str(candidate.path))].append(candidate)
        else:
            relations.append(
                _relation((candidate.id,), (), "unknown", reason, (LIMIT_AUTO_MATCH_WITHHELD,))
            )

    observed: dict[_MatchKey, list[RuntimeObservation]] = defaultdict(list)
    for observation in observations:
        observed[(_normalize_method(observation.method), observation.path)].append(observation)

    for key, group in eligible.items():
        matches = observed.get(key, [])
        if matches:
            relations.append(_matched_group_relation(group, matches))
            continue
        # 未観測の候補は 1 件ずつ残す（別 origin の候補を 1 件へ潰さない）
        for candidate in group:
            relations.append(
                _relation((candidate.id,), (), "inferred", BASIS_STATIC_ONLY, (LIMIT_NOT_OBSERVED,))
            )
    for key, group in observed.items():
        if key not in eligible:
            for observation in group:
                relations.append(
                    _relation(
                        (),
                        (observation.id,),
                        "unknown",
                        BASIS_RUNTIME_ONLY,
                        (LIMIT_NO_STATIC_CANDIDATE,),
                    )
                )
    relations.extend(route_relations(candidates))
    return tuple(sorted(relations, key=lambda r: r.id))


def route_relations(candidates: Iterable[StaticCandidate]) -> tuple[Relation, ...]:
    """route 候補の関係（runtime の API とは比べない）。

    同じ path の route 候補が複数あれば ambiguous、1 件なら関連先が不明なので unknown、
    path が確定しない候補も unknown。画面遷移の実測は snapshot に無いので inferred にはしない。
    """
    by_path: dict[str, list[StaticCandidate]] = defaultdict(list)
    relations: list[Relation] = []
    for candidate in candidates:
        if candidate.kind != "route":
            continue
        if candidate.resolution != "exact" or not candidate.path:
            relations.append(
                _relation((candidate.id,), (), "unknown", BASIS_PATH_UNRESOLVED, ROUTE_LIMITS)
            )
        else:
            by_path[candidate.path].append(candidate)
    for group in by_path.values():
        ids = tuple(sorted(c.id for c in group))
        if len(group) > 1:
            limits = ROUTE_LIMITS + (LIMIT_MULTIPLE_CANDIDATES,)
            relations.append(_relation(ids, (), "ambiguous", BASIS_ROUTE_STATIC_ONLY, limits))
        else:
            relations.append(_relation(ids, (), "unknown", BASIS_ROUTE_STATIC_ONLY, ROUTE_LIMITS))
    return tuple(relations)


def summarize(
    static_candidates: Iterable[StaticCandidate],
    runtime_observations: Iterable[RuntimeObservation],
    relations: Iterable[Relation],
) -> Summary:
    """件数の要約。observed_api_records は取得レコード数（API 総数ではない）。"""
    classes = [relation.classification for relation in relations]
    return Summary(
        static_candidates=len(tuple(static_candidates)),
        observed_api_records=len(tuple(runtime_observations)),
        inferred_relations=classes.count("inferred"),
        ambiguous_relations=classes.count("ambiguous"),
        unknown_relations=classes.count("unknown"),
        matched_relations=classes.count("matched"),
    )


def _matched_group_relation(
    candidates: list[StaticCandidate], observations: list[RuntimeObservation]
) -> Relation:
    static_ids = tuple(sorted(c.id for c in candidates))
    runtime_ids = tuple(sorted(o.id for o in observations))
    base = (
        LIMIT_RUNTIME_ORIGIN_NOT_RECORDED,
        LIMIT_RUNTIME_QUERY_NOT_RETAINED,
        LIMIT_NOT_IDENTITY_PROOF,
    )
    if len(candidates) == 1 and len(observations) == 1:
        return _relation(static_ids, runtime_ids, "inferred", BASIS_METHOD_PATH_ONLY, base)
    multiplicity: tuple[str, ...] = ()
    if len(candidates) > 1:
        multiplicity += (LIMIT_MULTIPLE_CANDIDATES,)
    if len(observations) > 1:
        multiplicity += (LIMIT_MULTIPLE_OBSERVATIONS,)
    return _relation(
        static_ids, runtime_ids, "ambiguous", BASIS_METHOD_PATH_ONLY, base + multiplicity
    )


def _unknown_reason(candidate: StaticCandidate) -> str | None:
    """自動対応を保留する理由。対応可能なら None。"""
    if candidate.resolution != "exact":
        return BASIS_DYNAMIC_EXPRESSION
    if not candidate.method or not candidate.method.strip():
        return BASIS_METHOD_MISSING
    if candidate.query_dependent or (candidate.path is not None and "?" in candidate.path):
        return BASIS_QUERY_DEPENDENT
    if not candidate.path:
        return BASIS_PATH_UNRESOLVED
    if any(marker in candidate.path for marker in _TEMPLATE_MARKERS):
        return BASIS_DYNAMIC_EXPRESSION
    return None


def _normalize_method(method: str | None) -> str:
    """明示値を大文字化するだけ。欠損を GET と推定しない。"""
    return (method or "").strip().upper()


def _relation(
    static_ids: tuple[str, ...],
    runtime_ids: tuple[str, ...],
    classification: str,
    basis: str,
    limitations: tuple[str, ...],
) -> Relation:
    relation_id = make_id(
        "rel", ",".join(static_ids), ",".join(runtime_ids), classification, basis
    )
    return Relation(
        id=relation_id,
        static_ids=static_ids,
        runtime_ids=runtime_ids,
        classification=classification,
        epistemic_state="unknown" if classification == "unknown" else "inferred",
        basis=basis,
        limitations=limitations,
    )


def _unique(items: tuple[_T, ...], label: str) -> tuple[_T, ...]:
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label}の ID が重複しています")
    return items
