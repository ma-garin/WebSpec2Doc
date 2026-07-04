"""実測×実測の画面対応付け（現新比較の中核）。

``ingest/matcher.py::_match_screens``（文書×実測の画面対応付け）と同じ
「スコア降順貪欲法」を、実測（現行）×実測（新）に一般化したもの。
ドメインが異なるため fingerprint 全体（URL 込み）は使えず、構造署名部分
（``analyzer.canonicalizer._structure_signature``）のみを同点タイブレークに使う。
"""

from __future__ import annotations

from dataclasses import dataclass

from analyzer.canonicalizer import _structure_signature
from analyzer.html_analyzer import AnalyzedPage
from analyzer.text_similarity import name_similarity, normalize_path

DEFAULT_THRESHOLD = 0.6

_METHOD_PATH = "path"
_METHOD_TITLE = "title"
_METHOD_FINGERPRINT = "fingerprint"


@dataclass(frozen=True)
class ScreenPair:
    """現行画面と新画面の対応 1 件。"""

    old_page_id: str
    new_page_id: str
    score: float  # 1.0 = パス一致、それ以外は名称類似度
    method: str  # "path" / "title" / "fingerprint"（同点タイブレークで確定した場合）


def match_page_pairs(
    old_pages: list[AnalyzedPage],
    new_pages: list[AnalyzedPage],
    threshold: float = DEFAULT_THRESHOLD,
) -> tuple[list[ScreenPair], list[str], list[str]]:
    """スコア降順貪欲法で現行×新の 1 対 1 画面対応を作る。

    戻り値: (pairs, removed_page_ids, added_page_ids)。
    removed_page_ids は現行にしかない画面、added_page_ids は新にしかない画面。
    """
    candidates = _build_candidates(old_pages, new_pages, threshold)
    is_ambiguous = _mark_ambiguous(candidates)
    # スコア降順・同点時は構造署名が一致する組を優先（タイブレーク）
    order = sorted(
        range(len(candidates)),
        key=lambda idx: (candidates[idx][0], candidates[idx][1]),
        reverse=True,
    )

    used_old: set[str] = set()
    used_new: set[str] = set()
    pairs: list[ScreenPair] = []
    for idx in order:
        score, structure_match, method, old_page, new_page = candidates[idx]
        if old_page.page_id in used_old or new_page.page_id in used_new:
            continue
        used_old.add(old_page.page_id)
        used_new.add(new_page.page_id)
        # 名称類似度が同点で構造署名が一致する組を選んだ場合のみ "fingerprint"
        # とする（タイブレークが実際に効いた場合のみ。単独候補は "title" のまま）
        resolved_method = (
            _METHOD_FINGERPRINT
            if method == _METHOD_TITLE and structure_match and is_ambiguous[idx]
            else method
        )
        pairs.append(
            ScreenPair(
                old_page_id=old_page.page_id,
                new_page_id=new_page.page_id,
                score=round(score, 3),
                method=resolved_method,
            )
        )

    removed_page_ids = [p.page_id for p in old_pages if p.page_id not in used_old]
    added_page_ids = [p.page_id for p in new_pages if p.page_id not in used_new]
    return pairs, removed_page_ids, added_page_ids


_Candidate = tuple[float, bool, str, AnalyzedPage, AnalyzedPage]


def _build_candidates(
    old_pages: list[AnalyzedPage],
    new_pages: list[AnalyzedPage],
    threshold: float,
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    for old_page in old_pages:
        for new_page in new_pages:
            score, method = _pair_score(old_page, new_page)
            if score < threshold:
                continue
            structure_match = _structure_signature(
                old_page.page_data.forms
            ) == _structure_signature(new_page.page_data.forms)
            candidates.append((score, structure_match, method, old_page, new_page))
    return candidates


def _mark_ambiguous(candidates: list[_Candidate]) -> list[bool]:
    """同一画面に対し同スコアの競合候補が他にもあるか（タイブレークが必要か）を判定する。"""
    ambiguous = [False] * len(candidates)
    for i, (score_i, _sm_i, _method_i, old_i, new_i) in enumerate(candidates):
        for j, (score_j, _sm_j, _method_j, old_j, new_j) in enumerate(candidates):
            if i == j or score_i != score_j:
                continue
            if old_i.page_id == old_j.page_id or new_i.page_id == new_j.page_id:
                ambiguous[i] = True
                break
    return ambiguous


def _pair_score(old_page: AnalyzedPage, new_page: AnalyzedPage) -> tuple[float, str]:
    """画面ペアのスコアを返す（正規化 URL パス一致を最優先、次に名称類似）。"""
    if normalize_path(old_page.page_data.url) == normalize_path(new_page.page_data.url):
        return 1.0, _METHOD_PATH
    title_score = name_similarity(old_page.page_data.title, new_page.page_data.title)
    heading_score = max(
        (
            name_similarity(old_heading, new_heading)
            for old_heading in old_page.page_data.headings
            for new_heading in new_page.page_data.headings
        ),
        default=0.0,
    )
    return max(title_score, heading_score), _METHOD_TITLE
