"""文書由来の業務ルールをテスト条件へ注入する（Doc Fusion Phase 2）。

SPEC-1-1 で抽出した DocumentedRule（計算式・限度値・権限条件）を、
突合済みの画面・項目に対応づけてテスト条件（TestCondition）として
注入する。計算式の評価（式をパースして期待値を計算すること）は行わない
（根拠のない推定値になるため。原文提示に留める）。
"""

from __future__ import annotations

import logging

from analyzer.html_analyzer import AnalyzedPage
from analyzer.test_conditions import SOURCE_DOCUMENT, TestCondition
from ingest.matcher import FusionResult, _name_similarity
from ingest.models import DocumentBundle, DocumentedRule
from ingest.tables import parse_max_length

logger = logging.getLogger(__name__)

_FIELD_NAME_THRESHOLD = 0.6  # ingest.matcher._FIELD_NAME_THRESHOLD と同じしきい値
_UNIT_WORDS = ("万", "千", "億")


def boundary_conditions_from_limit(rule: DocumentedRule) -> tuple[str, ...]:
    """expression から数値を抽出し、境界値 3 点の条件文を返す。

    単位語（万・千・億）を伴う表現は換算を推測せず、数値化不能として
    空 tuple を返す（呼び出し側が原文提示の条件に倒す）。
    """
    if any(unit in rule.expression for unit in _UNIT_WORDS):
        return ()
    value = parse_max_length(rule.expression)
    if value is None:
        return ()
    return (f"文書ルール境界値({rule.expression}): {value - 1}/{value}/{value + 1}",)


def condition_from_rule(
    rule: DocumentedRule, descriptions: tuple[str, ...]
) -> tuple[TestCondition, ...]:
    """source=SOURCE_DOCUMENT・confidence=rule.confidence の TestCondition 群を返す。

    evidence（文書根拠）の無いルールは条件を生成しない（evidence-only 原則）。
    """
    if rule.evidence is None:
        return ()
    return tuple(
        TestCondition(
            description=description,
            source=SOURCE_DOCUMENT,
            confidence=rule.confidence,
            evidence=None,
            doc_evidence=rule.evidence,
        )
        for description in descriptions
    )


def _descriptions_for_rule(rule: DocumentedRule) -> tuple[str, ...]:
    if rule.kind == "limit":
        boundary = boundary_conditions_from_limit(rule)
        if boundary:
            return boundary
        logger.warning("数値化不能な限度値ルール（原文参照に倒す）: %s", rule.rule_id)
        if not rule.description:
            return ()
        return (f"{rule.description}（数値化不能・原文参照）",)
    if rule.expression:
        return (f"{rule.description}: {rule.expression}",)
    if rule.description:
        return (rule.description,)
    return ()


def _match_field_for_rule(rule: DocumentedRule, page: AnalyzedPage | None) -> str:
    """rule.field_name に最も類似したフィールド名を返す（しきい値未満は "" = ページレベル）。"""
    if not rule.field_name or page is None:
        return ""
    best_name = ""
    best_score = 0.0
    for form in page.page_data.forms:
        for field in form.fields:
            score = max(
                _name_similarity(rule.field_name, field.name),
                _name_similarity(rule.field_name, field.aria_label),
                _name_similarity(rule.field_name, field.placeholder),
            )
            if score > best_score:
                best_score = score
                best_name = field.name
    return best_name if best_score >= _FIELD_NAME_THRESHOLD else ""


def build_rule_conditions(
    result: FusionResult,
    bundle: DocumentBundle,
    pages: list[AnalyzedPage],
) -> dict[tuple[str, str], tuple[TestCondition, ...]]:
    """抽出ルールを画面対応（result.screen_matches）に沿って各フィールドへ割り当てる。

    画面対応: rule.screen_name と ScreenMatch.screen.name / screen_id の一致。
    項目対応: rule.field_name と FieldData.name / aria_label / placeholder の類似
    （しきい値 0.6）。項目対応が無いルールは (page_id, "") のページレベル条件にする。
    どの画面にも対応しないルールは注入しない。
    """
    screen_to_page: dict[str, str] = {}
    for match in result.screen_matches:
        for key in (match.screen.name, match.screen.screen_id):
            if key:
                screen_to_page[key] = match.page_id
    pages_by_id = {p.page_id: p for p in pages}

    injected: dict[tuple[str, str], list[TestCondition]] = {}
    for rule in bundle.rules:
        if rule.evidence is None:
            logger.warning("根拠のないルールを除外: %s", rule.rule_id)
            continue
        page_id = screen_to_page.get(rule.screen_name)
        if page_id is None:
            logger.warning("注入先画面なし: %s", rule.rule_id)
            continue
        descriptions = _descriptions_for_rule(rule)
        if not descriptions:
            continue
        conditions = condition_from_rule(rule, descriptions)
        if not conditions:
            continue
        field_name = _match_field_for_rule(rule, pages_by_id.get(page_id))
        key = (page_id, field_name)
        injected.setdefault(key, []).extend(conditions)
    return {key: tuple(value) for key, value in injected.items()}
