"""UX 自動エキスパートレビューの出力層（ux_review.json 生成）。

axe-core（rules 層・confidence 1.0）とニールセン10原則評価
（rules または LLM 層・confidence<=0.9）の所見を画面単位で統合し、
別ファイル（output/{domain}/ux_review.json）として永続化する。
report.json のスキーマ・report_hash には一切影響しない（AC-7）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ux.axe_runner import axe_violation_to_dict
from ux.heuristics import pop_hallucination_drop_count

if TYPE_CHECKING:
    from crawler.page_crawler import PageData
    from ux.axe_runner import AxeViolation

logger = logging.getLogger(__name__)

UX_REVIEW_FILE_NAME = "ux_review.json"
JSON_INDENT = 2

# docs/11 §3 Sprint C の免責文言（一次スクリーニングであることを明示する）
UX_REVIEW_DISCLAIMER = "自動検査は a11y 問題の 30〜40% を捕捉する一次スクリーニングです。"


def build_ux_review(
    pages: list[PageData],
    page_ids: dict[str, str],
    axe_results: dict[str, tuple[AxeViolation, ...]],
    ux_findings: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """画面ごとの axe 違反・ニールセン所見を統合した ux_review.json 用 dict を構築する。

    axe_results / ux_findings は正規化済み URL をキーとする（crawl_page の normalized_url）。
    呼び出し後、幻覚フィルタの累積破棄カウンタは pop_hallucination_drop_count() で読み出し
    リセットする（1 回の生成につき 1 回だけ呼ぶこと）。
    """
    screens = []
    for page in pages:
        page_id = page_ids.get(page.url, "")
        axe_list = axe_results.get(page.url, ())
        findings = ux_findings.get(page.url, [])
        screens.append(
            {
                "page_id": page_id,
                "url": page.url,
                "title": page.title,
                "axe_violations": [axe_violation_to_dict(v) for v in axe_list],
                "ux_findings": list(findings),
            }
        )
    return {
        "meta": {
            "disclaimer": UX_REVIEW_DISCLAIMER,
            "hallucination_dropped_count": pop_hallucination_drop_count(),
        },
        "screens": screens,
    }


def build_ux_screen_info(
    page_data: PageData, axe_violations: tuple[AxeViolation, ...]
) -> dict[str, Any]:
    """PageData と axe 検査結果から provider.generate_ux_review 用の screen_info を構築する。

    known_selectors には実在するフィールド・axe 違反のセレクタのみを含める
    （幻覚フィルタが参照する「実在セレクタのインベントリ」§5-3）。
    """
    from crawler.page_crawler import evidence_to_dict

    fields: list[dict[str, Any]] = []
    known_selectors: set[str] = set()
    for form in page_data.forms:
        for field in form.fields:
            evidence = evidence_to_dict(field.evidence)
            selector = str(evidence.get("selector") or "") if evidence else ""
            if selector:
                known_selectors.add(selector)
            fields.append(
                {
                    "name": field.name,
                    "has_visible_label": field.has_visible_label,
                    "aria_label": field.aria_label,
                    "placeholder": field.placeholder,
                    "required": field.required,
                    "aria_required": field.aria_required,
                    "evidence": evidence,
                }
            )
    axe_summary: list[dict[str, Any]] = []
    for violation in axe_violations:
        selector = violation.evidence.selector
        if selector:
            known_selectors.add(selector)
        axe_summary.append(
            {"rule_id": violation.rule_id, "impact": violation.impact, "selector": selector}
        )
    return {
        "title": page_data.title,
        "headings": list(page_data.headings),
        "fields": fields,
        "buttons": list(page_data.buttons),
        "axe_violation_summary": axe_summary,
        "known_selectors": sorted(known_selectors),
        "screenshot_path": page_data.screenshot_path,
    }


def save_ux_outputs(ux_review: dict[str, Any], output_dir: Path) -> Path:
    """ux_review.json を output_dir に保存し、書き込み先パスを返す。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / UX_REVIEW_FILE_NAME
    path.write_text(
        json.dumps(ux_review, ensure_ascii=False, indent=JSON_INDENT),
        encoding="utf-8",
    )
    logger.info("UX 所見を保存しました: %s", path)
    return path
