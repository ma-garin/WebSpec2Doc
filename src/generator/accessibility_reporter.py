"""自社 Accessibility チェッカーの実測を独立したアクセシビリティ監査成果物へ変換する。

結果は 3 区分で扱う: 違反 / 合格 / 未実装・判定不能（NOT_EVALUATED）。
未実装・判定不能は「合格」に数えず、全ルールの状態を ``rule_results`` に残す。
旧形式（違反オブジェクトのタプル）の入力も受け付け、従来キーは維持する。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ux.a11y import catalog as _catalog

if TYPE_CHECKING:
    from crawler.page_crawler import PageData

ACCESSIBILITY_AUDIT_FILE_NAME = "accessibility_audit.json"
ENGINE_NAME = "webspec2doc-native-a11y"
DISCLAIMER = (
    "WebSpec2Doc 自社の検査ルールによる、機械判定可能な項目だけの一次スクリーニングです。"
    "WCAG/JIS X 8341-3 への適合を保証せず、未実装・判定不能の項目を含む残りは"
    "人による手動確認が必要です。"
)
_IMPACTS = ("critical", "serious", "moderate", "minor")
_NOT_EVALUATED = ("not_implemented", "cant_tell")


def _s(value: Any) -> str:
    return str(getattr(value, "value", value))


def _spec_map() -> dict[str, Any]:
    return {spec.rule_id: spec for spec in _catalog.RULES}


def _wcag_tags(spec: Any) -> list[str]:
    if spec is None:
        return []
    level = _s(spec.wcag_level)
    tags = {"A": ["wcag2a"], "AA": ["wcag2aa"], "best_practice": ["best-practice"]}.get(level, [])
    tags.extend("wcag" + str(sc).replace(".", "") for sc in spec.wcag_sc)
    return tags


def is_native_result(item: Any) -> bool:
    return hasattr(item, "rules") and not isinstance(item, (tuple, list))


def violation_dicts(item: Any, screenshot_path: str | None = None) -> list[dict[str, Any]]:
    """PageA11yResult または旧形式の違反タプルを、従来互換の違反 dict の一覧へ変換する。"""
    from crawler.page_crawler import evidence_to_dict

    if item is None:
        return []
    if not is_native_result(item):
        return [
            {
                "rule_id": v.rule_id,
                "impact": v.impact,
                "description": v.description,
                "wcag_tags": list(v.wcag_tags),
                "evidence": evidence_to_dict(v.evidence),
                "help_url": getattr(v, "help_url", ""),
                "confidence": getattr(v, "confidence", 1.0),
            }
            for v in item
        ]
    specs = _spec_map()
    out: list[dict[str, Any]] = []
    for rule in item.rules:
        spec = specs.get(rule.rule_id)
        legacy = tuple(getattr(spec, "legacy_axe_ids", ()) or ()) if spec else ()
        for node in rule.nodes:
            if _s(node.status) != "violation":
                continue
            bbox = list(node.bbox) if node.bbox else None
            out.append(
                {
                    "rule_id": legacy[0] if legacy else rule.rule_id,
                    "native_rule_id": rule.rule_id,
                    "impact": _s(node.impact or ""),
                    "description": (spec.description_ja if spec else "") or node.message,
                    "message": node.message,
                    "wcag_tags": _wcag_tags(spec),
                    "evidence": {
                        "selector": node.selector,
                        "html_attribute": None,
                        "screenshot_path": screenshot_path,
                        "bbox": bbox,
                        "observed": dict(node.evidence or {}),
                    },
                    "help_url": "",
                    "confidence": 1.0,
                }
            )
    return out


def rule_result_dicts(result: Any) -> list[dict[str, Any]]:
    """PageA11yResult の全ルールの状態を dict の一覧にする（旧形式では空）。"""
    if not is_native_result(result):
        return []
    specs = _spec_map()
    rows: list[dict[str, Any]] = []
    for rule in result.rules:
        spec = specs.get(rule.rule_id)
        status = _s(rule.status)
        reason = ""
        if status in _NOT_EVALUATED:
            reason = (spec.reason_if_unimplemented if spec else "") or next(
                (n.message for n in rule.nodes if n.message), ""
            )
        rows.append(
            {
                "rule_id": rule.rule_id,
                "status": status,
                "category": _s(spec.category) if spec else "",
                "wcag_sc": list(spec.wcag_sc) if spec else [],
                "wcag_level": _s(spec.wcag_level) if spec else "",
                "implementation": _s(spec.implementation) if spec else "",
                "description": spec.description_ja if spec else "",
                "counts": dict(rule.counts or {}),
                "reason": reason,
            }
        )
    return rows


def catalog_coverage() -> dict[str, int]:
    counts = {"implemented": 0, "partial": 0, "not_implemented": 0}
    for spec in _catalog.RULES:
        key = {"full": "implemented", "partial": "partial"}.get(
            _s(spec.implementation), "not_implemented"
        )
        counts[key] += 1
    return counts


def build_accessibility_audit(
    pages: list[PageData],
    page_ids: dict[str, str],
    a11y_results: dict[str, Any],
) -> dict[str, Any]:
    """画面ごとの結果から accessibility_audit.json 用 dict を構築する。

    a11y_results は URL → PageA11yResult（旧形式: 違反タプル）。
    summary の passed/cant_tell/not_implemented/inapplicable は「画面×ルール」の件数。
    """
    screens: list[dict[str, Any]] = []
    impact_counts = {impact: 0 for impact in _IMPACTS}
    status_counts = {"pass": 0, "cant_tell": 0, "not_implemented": 0, "inapplicable": 0}
    total = 0
    for page in pages:
        item = a11y_results.get(page.url, ())
        violations = violation_dicts(item, page.screenshot_path)
        rule_results = rule_result_dicts(item)
        total += len(violations)
        for violation in violations:
            impact = str(violation.get("impact") or "")
            if impact in impact_counts:
                impact_counts[impact] += 1
        for row in rule_results:
            if row["status"] in status_counts:
                status_counts[row["status"]] += 1
        screen: dict[str, Any] = {
            "page_id": page_ids.get(page.url, ""),
            "url": page.url,
            "title": page.title,
            "screenshot_path": page.screenshot_path,
            "violations": violations,
            "rule_results": rule_results,
        }
        error = getattr(item, "error", None)
        if error:
            screen["error"] = str(error)
        screens.append(screen)
    summary = {
        "violations": total,
        **impact_counts,
        "passed": status_counts["pass"],
        "cant_tell": status_counts["cant_tell"],
        "not_implemented": status_counts["not_implemented"],
        "inapplicable": status_counts["inapplicable"],
    }
    return {
        "meta": {
            "engine": ENGINE_NAME,
            "catalog_version": str(getattr(_catalog, "CATALOG_VERSION", "")),
            "coverage": catalog_coverage(),
            "claim_scope": "automated_detectable_subset_only",
            "disclaimer": DISCLAIMER,
            "manual_review_required": True,
        },
        "summary": summary,
        "screens": screens,
    }


def coverage_notice(audit: dict[str, Any]) -> str:
    """HTML 等に併記する文言。違反 0 件でも「問題なし」と読ませない。"""
    cov = (audit.get("meta") or {}).get("coverage") or {}
    if not cov:
        return "自動検査の対象外の項目は手動確認が必要です。"
    done = int(cov.get("implemented", 0)) + int(cov.get("partial", 0))
    missing = int(cov.get("not_implemented", 0))
    return f"実装 {done} / 未実装 {missing} ルール。未実装・判定不能は手動確認が必要です。"


def unevaluated_rules(audit: dict[str, Any]) -> list[dict[str, str]]:
    """未実装・判定不能のルール（重複なし）。表示用: rule_id・状態・理由。"""
    seen: dict[str, dict[str, str]] = {}
    for screen in audit.get("screens") or []:
        for row in screen.get("rule_results") or []:
            if row.get("status") in _NOT_EVALUATED and row["rule_id"] not in seen:
                seen[row["rule_id"]] = {
                    "rule_id": row["rule_id"],
                    "status": row["status"],
                    "description": row.get("description", ""),
                    "reason": row.get("reason", ""),
                }
    return list(seen.values())


def save_accessibility_audit(payload: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / ACCESSIBILITY_AUDIT_FILE_NAME
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
