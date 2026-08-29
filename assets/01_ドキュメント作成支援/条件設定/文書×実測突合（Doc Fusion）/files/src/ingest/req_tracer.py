"""RFP要件トレーサビリティ（SPEC-1-3）: 要件→画面→テストケースの連鎖構築。

文書由来の DocumentedRequirement を、実測画面（ScreenMatch / official_names）
とテストケース（AnalyzedPage の test_conditions 由来の条件件数、および
playwright_candidates.json の candidate id）へマッピングする。

既存の `web/services/traceability.py::RequirementLink`（画面=要件とみなす暫定実装）
とは別物であり、web 側からこのモジュールを import してはならない
（web → src の一方向依存のみ。§CONVENTIONS 1-1）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from analyzer.canonicalizer import group_canonical_screens
from analyzer.html_analyzer import AnalyzedPage
from analyzer.test_conditions import derive_conditions
from ingest.matcher import _SCREEN_NAME_THRESHOLD, FusionResult, _name_similarity
from ingest.models import DocumentBundle, DocumentedRequirement

logger = logging.getLogger(__name__)

STATUS_COVERED = "covered"
STATUS_SCREEN_ONLY = "screen_only"
STATUS_UNIMPLEMENTED_SUSPECT = "unimplemented_suspect"


@dataclass(frozen=True)
class RequirementTrace:
    """1 要件の追跡結果。"""

    requirement: DocumentedRequirement
    status: str  # "covered" / "screen_only" / "unimplemented_suspect"
    page_id: str = ""  # 対応画面（未対応は ""）
    page_url: str = ""
    match_score: float = 0.0
    match_method: str = ""  # "name" / "official_name"
    test_condition_count: int = 0  # 対応画面の test_conditions_detail 相当件数
    candidate_ids: tuple[str, ...] = ()  # playwright_candidates.json の id
    # unimplemented_suspect のときのみ埋まる「近い画面」（しきい値未満でも最有力候補）。
    # 断定を避けるため、判断材料として常に残す（仕様書 §8 の罠対応）。
    near_page_id: str = ""
    near_page_title: str = ""
    near_score: float = 0.0


def _requirement_score(requirement: DocumentedRequirement, candidate: str) -> float:
    """要件と画面候補名（タイトル/見出し/official_name）の類似度を返す。

    RFP要件は「〜ができること」のような文になることが多く、画面名（短い名詞）を
    そのまま _name_similarity にかけると編集距離ベースの ratio が不当に低くなる。
    候補名が要件文にそのまま含まれる場合は包含関係を優先し 1.0 とする
    （_screen_score の URL 完全一致ショートカットと同じ考え方の拡張。仕様外判断）。
    類似度計算そのものは ingest.matcher._name_similarity を再利用する。
    """
    if not candidate:
        return 0.0
    texts = [t for t in (requirement.title, requirement.description) if t]
    if not texts:
        return 0.0
    if any(candidate in text or text in candidate for text in texts):
        return 1.0
    return max(_name_similarity(text, candidate) for text in texts)


def _test_condition_count(page: AnalyzedPage) -> int:
    """画面の全フォーム・全フィールドから導出されるテスト条件の総数。"""
    return sum(
        len(derive_conditions(field)) for form in page.page_data.forms for field in form.fields
    )


def _candidate_ids_for_url(url: str, candidates: list[dict]) -> tuple[str, ...]:
    """playwright_candidates.json の candidates から、steps の URL が一致する id を返す。"""
    ids: list[str] = []
    if not url:
        return ()
    for candidate in candidates:
        cand_id = str(candidate.get("id") or "")
        if not cand_id or cand_id in ids:
            continue
        for step in candidate.get("steps", []):
            if step.get("url", "") == url:
                ids.append(cand_id)
                break
    return tuple(ids)


def _best_match(
    requirement: DocumentedRequirement,
    canonical_pages: list[AnalyzedPage],
    official_names: dict[str, str],
) -> tuple[AnalyzedPage | None, float, str]:
    """要件に最も近い画面（page, score, method）を返す（しきい値判定はしない）。"""
    best_page: AnalyzedPage | None = None
    best_score = 0.0
    best_method = ""
    for page in canonical_pages:
        name_candidates = (page.page_data.title, *page.page_data.headings)
        name_score = max(
            (_requirement_score(requirement, c) for c in name_candidates if c),
            default=0.0,
        )
        official_name = official_names.get(page.page_id, "")
        official_score = _requirement_score(requirement, official_name) if official_name else 0.0
        if official_score > 0 and official_score >= name_score:
            score, method = official_score, "official_name"
        else:
            score, method = name_score, "name"
        if score > best_score:
            best_page, best_score, best_method = page, score, method
    return best_page, best_score, best_method


def _warn_duplicate_req_ids(requirements: tuple[DocumentedRequirement, ...]) -> None:
    """req_id が重複している要件を警告する（後勝ちにせず両方出力するため、ここでは警告のみ）。"""
    seen: set[str] = set()
    for requirement in requirements:
        if requirement.req_id in seen:
            logger.warning(
                "要件IDが重複しています（両方とも出力します）: %s（%s）",
                requirement.req_id,
                requirement.title,
            )
        seen.add(requirement.req_id)


def trace_requirements(
    bundle: DocumentBundle,
    result: FusionResult,
    pages: list[AnalyzedPage],
    candidates: list[dict],
) -> tuple[RequirementTrace, ...]:
    """要件ごとに対応画面とテストケースを解決する。

    類似判定は ingest.matcher._name_similarity・しきい値 _SCREEN_NAME_THRESHOLD(0.6)
    を再利用する。official_names（result.official_names）に一致した場合は
    method="official_name"（スコアは加点なしの生値）、それ以外は method="name"。
    1 要件につき最もスコアの高い画面 1 件のみを対応画面とする
    （複数要件が同じ画面に対応する「多対1」は許容するが、逆はしない）。
    """
    if not bundle.requirements:
        return ()
    _warn_duplicate_req_ids(bundle.requirements)

    canonical_info = group_canonical_screens(pages)
    canonical_pages = [p for p in pages if canonical_info[p.page_id].is_canonical]
    official_names = result.official_names

    traces: list[RequirementTrace] = []
    for requirement in bundle.requirements:
        best_page, best_score, best_method = _best_match(
            requirement, canonical_pages, official_names
        )
        if best_page is not None and best_score >= _SCREEN_NAME_THRESHOLD:
            condition_count = _test_condition_count(best_page)
            candidate_ids = _candidate_ids_for_url(best_page.page_data.url, candidates)
            status = (
                STATUS_COVERED if (condition_count > 0 or candidate_ids) else STATUS_SCREEN_ONLY
            )
            traces.append(
                RequirementTrace(
                    requirement=requirement,
                    status=status,
                    page_id=best_page.page_id,
                    page_url=best_page.page_data.url,
                    match_score=round(best_score, 3),
                    match_method=best_method,
                    test_condition_count=condition_count,
                    candidate_ids=candidate_ids,
                )
            )
        else:
            traces.append(
                RequirementTrace(
                    requirement=requirement,
                    status=STATUS_UNIMPLEMENTED_SUSPECT,
                    near_page_id=best_page.page_id if best_page is not None else "",
                    near_page_title=best_page.page_data.title if best_page is not None else "",
                    near_score=round(best_score, 3),
                )
            )
    return tuple(traces)
