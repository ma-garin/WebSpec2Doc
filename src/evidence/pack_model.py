"""証跡パックのデータ構造を組み立てる（純関数・副作用なし）。

材料はすべて既存の生成物。欠けているものは黙って埋めず `missing_inputs` に記録し、
該当欄を「未取得」として残す。埋めてしまうと、証跡としての価値が失われるため。
"""

from __future__ import annotations

import platform
import re
import sys
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

CLAIM_SCOPE = "executed_record_only"

CLAIM_NOTICE = (
    "本書はテストを実行した事実の記録であり、" "品質の合否・テストの十分性を判定するものではない。"
)

INPUT_REPORT = "playwright_report"
INPUT_VIEWPOINTS = "quality_viewpoints"
INPUT_META = "autorun_meta"
INPUT_CLASSIFICATIONS = "failure_classifications"
INPUT_SCREENSHOTS = "screenshots"
INPUT_MANUAL = "manual_procedures"
INPUT_MUTATION_CHECK = "mutation_self_check"

_TEST_ID_PATTERN = re.compile(r"^([A-Z]+-\d+)")


def build_evidence_pack(
    report: dict[str, Any] | None,
    viewpoints: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
    classifications: list[dict[str, Any]] | None = None,
    screenshots: dict[str, str] | None = None,
    manual_procedures: str | None = None,
    audit_entries: list[dict[str, Any]] | None = None,
    generated_at: datetime | None = None,
    mutation_check: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """検収提出用の証跡パックを組み立てる。

    report が無い場合でも例外にせず、空の実行記録として返す（欠落は明示する）。
    mutation_check は AutoRun 自身が実行した自己検証（ミューテーションテスト）の
    結果（mutation_verifier.run_self_check の戻り値）。無い場合も欠落として明示する。
    """
    missing: list[str] = []
    if not report:
        missing.append(INPUT_REPORT)
    if not viewpoints:
        missing.append(INPUT_VIEWPOINTS)
    if not meta:
        missing.append(INPUT_META)
    if not classifications:
        missing.append(INPUT_CLASSIFICATIONS)
    if not screenshots:
        missing.append(INPUT_SCREENSHOTS)
    if not manual_procedures:
        missing.append(INPUT_MANUAL)
    if not mutation_check or not mutation_check.get("applicable", True):
        missing.append(INPUT_MUTATION_CHECK)

    report = report or {}
    meta_by_test = _meta_by_test_id(meta)
    viewpoints_by_page = _viewpoints_by_page(viewpoints)
    category_by_test = _category_by_test_id(classifications)

    cases: list[dict[str, Any]] = []
    for raw in report.get("tests", []):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title", ""))
        test_id = _test_id_from_title(title)
        info = meta_by_test.get(test_id, {})
        page_id = str(info.get("page_id", ""))
        screenshot = (screenshots or {}).get(page_id, "")
        status = str(raw.get("status", ""))
        has_real_assertion = bool(info.get("has_real_assertion", False))
        cases.append(
            {
                "case_id": test_id,
                "title": str(info.get("title", "")) or title,
                "page_id": page_id,
                "page_url": str(info.get("url", "")),
                "result": status,
                "duration_sec": round(float(raw.get("duration_ms", 0) or 0) / 1000, 3),
                "viewpoint_ids": viewpoints_by_page.get(page_id, []),
                "screenshot_path": screenshot,
                "failure_category": category_by_test.get(test_id, "") if status == "failed" else "",
                "error_excerpt": _excerpt(str(raw.get("error", ""))),
                "has_real_assertion": has_real_assertion,
            }
        )

    total_cases = len(cases)
    verified_cases = sum(1 for case in cases if case["has_real_assertion"])
    verification_rate = round(100 * verified_cases / total_cases, 1) if total_cases else 0.0

    return {
        "meta": {
            "generated_at": _timestamp(generated_at),
            "domain": str((meta or {}).get("domain", "")),
            "claim_scope": CLAIM_SCOPE,
            "claim_notice": CLAIM_NOTICE,
            "missing_inputs": missing,
        },
        "summary": {
            "total": int(report.get("total", len(cases)) or 0),
            "passed": int(report.get("passed", 0) or 0),
            "failed": int(report.get("failed", 0) or 0),
            "skipped": int(report.get("skipped", 0) or 0),
            "duration_sec": round(float(report.get("duration_ms", 0) or 0) / 1000, 3),
            # 「合格」件数だけでは、そのテストが実質的な検証をしていたか判定できない
            # （2026-07-20 の監査で発覚：body可視性だけの合格が334件検出0件だった）。
            # 有意なアサーション（値の受理／拒否・実在確認）を伴うテストの割合を明示する。
            "verified_cases": verified_cases,
            "verification_rate": verification_rate,
            # AutoRun自身が実行した自己検証（対象を破壊しても検出できるか）のスコア。
            # 「検証実行率」は静的な判定（アサーションの有無）だが、こちらは動的に
            # 実測した検出力であり、より強い裏付けになる。
            "self_check_score": (
                mutation_check.get("score")
                if mutation_check and mutation_check.get("applicable", True)
                else None
            ),
            "self_check_survivor_count": (
                mutation_check.get("survivor_count")
                if mutation_check and mutation_check.get("applicable", True)
                else None
            ),
        },
        "cases": cases,
        "environment": _environment(),
        "manual_section": manual_procedures or "",
        "audit_excerpt": [item for item in (audit_entries or []) if isinstance(item, dict)][:50],
    }


# ─────────────────── 材料の正規化 ───────────────────


def _meta_by_test_id(meta: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in (meta or {}).get("tests", []):
        if isinstance(item, dict) and str(item.get("test_id", "")):
            result[str(item["test_id"])] = item
    return result


def _viewpoints_by_page(viewpoints: dict[str, Any] | None) -> dict[str, list[str]]:
    """画面IDごとの観点ID一覧。screen_risks / items のどちらの形にも対応する。"""
    result: dict[str, list[str]] = {}
    for risk in (viewpoints or {}).get("screen_risks", []):
        if not isinstance(risk, dict):
            continue
        page_id = str(risk.get("page_id", ""))
        if not page_id:
            continue
        ids = [
            str(value)
            for value in risk.get("viewpoint_ids", risk.get("viewpoints", []))
            if str(value)
        ]
        if ids:
            result.setdefault(page_id, []).extend(ids)
    return {page_id: sorted(set(ids)) for page_id, ids in result.items()}


def _category_by_test_id(
    classifications: list[dict[str, Any]] | None,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in classifications or []:
        if not isinstance(item, dict):
            continue
        test_id = _test_id_from_title(str(item.get("test_id", "") or item.get("title", "")))
        category = str(item.get("category", "") or item.get("failure_category", ""))
        if test_id and category:
            result[test_id] = category
    return result


def _test_id_from_title(title: str) -> str:
    """'PW-0001 画面表示スモーク [P001]' のような表題から試験IDを取り出す。"""
    match = _TEST_ID_PATTERN.match(title.strip())
    return match.group(1) if match else ""


def _excerpt(error: str, limit: int = 400) -> str:
    text = " ".join(error.split())
    return text[:limit]


def _environment() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "executable": sys.executable,
    }


def _timestamp(generated_at: datetime | None) -> str:
    moment = generated_at or datetime.now(ZoneInfo("Asia/Tokyo"))
    return moment.isoformat(timespec="seconds")
