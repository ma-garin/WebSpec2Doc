"""ニールセン 10 原則ヒューリスティック評価（rules フォールバック＋ LLM 応答検証）。

rules 層（generate_ux_findings_by_rules）は DOM 実測から決定的に導出するため
confidence 1.0 固定。LLM 層は OpenAIProvider から呼ばれるスキーマ・幻覚フィルタを提供し、
confidence は 0.9 を上限とする（evidence-only 原則。CONVENTIONS §1-2）。

仕様外判断: SPEC-3-4 5-3 が例示する「タップ領域 44px 未満のボタン（N7）」は、
現行 screen_info のボタン情報が bbox を持たない（PageData.buttons はテキストのみ）ため
実測できず、根拠のない値を出力しない原則（evidence-only）に基づき採用しない。
代わりに、同じく実測可能な「画面に見出しが1件もない」を N1 所見として追加した。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from crawler.page_crawler import SourceEvidence, evidence_from_dict

logger = logging.getLogger(__name__)

_PRINCIPLES = tuple(f"N{i}" for i in range(1, 11))
_SEVERITIES = ("high", "medium", "low")

# rules 層は決定的な DOM 実測に基づくため confidence 1.0 固定。
RULES_UX_CONFIDENCE = 1.0
# LLM 層はスキーマ検証・幻覚フィルタ通過後も文言そのものは生成物のため 0.9 を上限とする。
LLM_UX_CONFIDENCE = 0.8

UX_REVIEW_SCHEMA_NAME = "ux_review_findings"

# OpenAI Structured Outputs（strict）用 JSON Schema
UX_REVIEW_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "principle": {"type": "string", "enum": list(_PRINCIPLES)},
                    "severity": {"type": "string", "enum": list(_SEVERITIES)},
                    "finding": {"type": "string"},
                    "selector": {"type": "string"},
                },
                "required": ["principle", "severity", "finding", "selector"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class UxFinding:
    """ニールセン10原則ヒューリスティックの所見1件。evidence は必須（無い所見は生成段階で破棄）。"""

    principle: str  # "N1" 〜 "N10"
    severity: str  # "high" / "medium" / "low"
    finding: str  # 指摘本文（日本語）
    evidence: SourceEvidence
    source: str  # "rules" / "openai"
    confidence: float


def ux_finding_to_dict(finding: UxFinding) -> dict[str, Any]:
    """UxFinding を JSON シリアライズ可能な dict に変換する。"""
    from crawler.page_crawler import evidence_to_dict

    return {
        "principle": finding.principle,
        "severity": finding.severity,
        "finding": finding.finding,
        "evidence": evidence_to_dict(finding.evidence),
        "source": finding.source,
        "confidence": finding.confidence,
    }


class UxReviewValidationError(ValueError):
    """LLM UX 所見応答のスキーマ違反を表す例外。"""


def build_ux_review_prompt(screen_info: dict[str, Any]) -> str:
    """ニールセン10原則評価用プロンプトを構築する。"""
    payload = {
        "title": screen_info.get("title", ""),
        "headings": list(screen_info.get("headings", [])),
        "fields": screen_info.get("fields", []),
        "buttons": list(screen_info.get("buttons", [])),
        "axe_violation_summary": list(screen_info.get("axe_violation_summary", [])),
        "known_selectors": list(screen_info.get("known_selectors", [])),
    }
    return (
        "あなたはユーザビリティ専門家です。ニールセンの10原則(N1〜N10)に基づき、"
        "以下のWeb画面情報からユーザビリティ上の所見を返してください。\n"
        f"画面情報: {json.dumps(payload, ensure_ascii=False)}\n\n"
        "各所見は以下のキーを持つこと: "
        "principle(N1〜N10のいずれか), severity(high/medium/low), "
        "finding(所見本文、日本語で具体的に), "
        "selector(根拠となる実在の要素セレクタ。known_selectors に含まれるものだけを使うこと)。"
        "axe_violation_summary に記載済みの指摘は重複計上しないこと。"
        "known_selectors に無いセレクタを創作しないこと。"
    )


def validate_ux_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """LLM 応答のスキーマ整合を検証し、所見 dict のリストを返す。

    違反時は UxReviewValidationError を送出する（呼び出し側で rules へフォールバック）。
    """
    items = payload.get("findings")
    if not isinstance(items, list) or not items:
        raise UxReviewValidationError("findings 配列がありません。")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise UxReviewValidationError(f"所見 {index} がオブジェクトではありません。")
        if item.get("principle") not in _PRINCIPLES:
            raise UxReviewValidationError(f"所見 {index} の principle が不正です。")
        if item.get("severity") not in _SEVERITIES:
            raise UxReviewValidationError(f"所見 {index} の severity が不正です。")
        finding = item.get("finding")
        if not isinstance(finding, str) or not finding.strip():
            raise UxReviewValidationError(f"所見 {index} の finding が不正です。")
        selector = item.get("selector")
        if not isinstance(selector, str) or not selector.strip():
            raise UxReviewValidationError(f"所見 {index} の selector が不正です。")
    return items


# 幻覚フィルタで破棄したセレクタの累積記録（ux_review.json meta 集計用）。
# main._run_crawl が画面ごとに provider.generate_ux_review を呼ぶ間に蓄積し、
# レポート出力直前に pop_hallucination_drop_count() で読み出してリセットする。
_hallucination_drops: list[str] = []


def record_hallucination_drop(selector: str) -> None:
    """幻覚フィルタで破棄したセレクタを記録する。"""
    _hallucination_drops.append(selector)


def pop_hallucination_drop_count() -> int:
    """記録済みの破棄件数を返し、内部カウンタをリセットする。"""
    count = len(_hallucination_drops)
    _hallucination_drops.clear()
    return count


def filter_hallucinated_findings(
    items: list[dict[str, Any]], known_selectors: set[str]
) -> list[dict[str, Any]]:
    """known_selectors に存在しない selector を根拠にした所見を破棄する（AC-4）。

    破棄した所見は record_hallucination_drop に記録し、警告ログを出す。
    スキーマ違反（全棄却）とは異なり、該当 1 件のみを破棄する。
    """
    kept: list[dict[str, Any]] = []
    for item in items:
        selector = str(item.get("selector") or "")
        if selector not in known_selectors:
            logger.warning("幻覚フィルタ: 実在しないセレクタ %s を破棄しました", selector)
            record_hallucination_drop(selector)
            continue
        kept.append(item)
    return kept


# ---------- rules フォールバック ----------


def generate_ux_findings_by_rules(screen_info: dict[str, Any]) -> list[UxFinding]:
    """LLM を使わず決定的に生成するニールセン所見（RulesProvider 用）。

    全て DOM 実測（FieldData / headings）から導出するため confidence=1.0 固定。
    evidence の無いフィールドは対象外とする（evidence-only 原則）。
    """
    findings: list[UxFinding] = []
    for raw in screen_info.get("fields", []):
        field = raw if isinstance(raw, dict) else _field_to_dict(raw)
        evidence = _field_evidence(field)
        if evidence is None:
            continue
        findings.extend(_field_findings(field, evidence))

    if not screen_info.get("headings"):
        findings.append(
            UxFinding(
                principle="N1",
                severity="low",
                finding="画面に見出しが1つもなく、ユーザーが現在地を認識しづらい可能性があります。",
                evidence=SourceEvidence(
                    selector="body",
                    screenshot_path=screen_info.get("screenshot_path"),
                ),
                source="rules",
                confidence=RULES_UX_CONFIDENCE,
            )
        )
    return findings


def _field_findings(field: dict[str, Any], evidence: SourceEvidence) -> list[UxFinding]:
    """1 フィールドから導出できるニールセン所見を返す。"""
    findings: list[UxFinding] = []
    has_visible_label = bool(field.get("has_visible_label"))
    aria_label = str(field.get("aria_label") or "")
    placeholder = str(field.get("placeholder") or "")
    required = bool(field.get("required"))
    aria_required = bool(field.get("aria_required"))

    if not has_visible_label and not aria_label:
        if placeholder:
            findings.append(
                UxFinding(
                    principle="N5",
                    severity="medium",
                    finding=(
                        "入力欄のラベルが placeholder のみに依存しています。"
                        "入力を開始するとラベル代わりの文言が消えるため、"
                        "エラー防止の観点で望ましくありません。"
                    ),
                    evidence=evidence,
                    source="rules",
                    confidence=RULES_UX_CONFIDENCE,
                )
            )
        else:
            findings.append(
                UxFinding(
                    principle="N6",
                    severity="high",
                    finding=(
                        "入力欄に可視ラベル・aria-label のいずれもなく、"
                        "何を入力すべきか記憶に頼る負荷（認識より記憶）が高い状態です。"
                    ),
                    evidence=evidence,
                    source="rules",
                    confidence=RULES_UX_CONFIDENCE,
                )
            )

    if required and not aria_required:
        findings.append(
            UxFinding(
                principle="N1",
                severity="medium",
                finding=(
                    "required 属性はありますが aria-required が付与されておらず、"
                    "支援技術に「入力必須」というシステム状態が伝わりません。"
                ),
                evidence=evidence,
                source="rules",
                confidence=RULES_UX_CONFIDENCE,
            )
        )
    return findings


def _field_to_dict(field: Any) -> dict[str, Any]:
    return {
        "has_visible_label": getattr(field, "has_visible_label", False),
        "aria_label": getattr(field, "aria_label", ""),
        "placeholder": getattr(field, "placeholder", ""),
        "required": getattr(field, "required", False),
        "aria_required": getattr(field, "aria_required", False),
        "evidence": getattr(field, "evidence", None),
    }


def _field_evidence(field: dict[str, Any]) -> SourceEvidence | None:
    raw = field.get("evidence")
    if isinstance(raw, SourceEvidence):
        return raw
    return evidence_from_dict(raw)
