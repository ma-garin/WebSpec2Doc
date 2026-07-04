"""テスト計画ドラフト生成（インベントリ×ROI 係数→工数見積・スコープ表）。

クロール済み report.json（画面一覧・テスト条件・ビジネスフロー優先度）から、
プロジェクトライフサイクルの「計画」フェーズ初稿（画面数×優先度→工数見積・
スコープ表）を Markdown / Excel で生成する。

evidence-only 原則により、見積は「手作業想定分数」の推定係数に基づく値であり
実測ではないことを出力に明記する。係数の既定値は web/services/usage_tracker.py
と同値だが、層分離のため import はせず定数として独自定義する（両者の一致は
tests/test_test_plan_generator.py のパリティテストで担保する）。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llm.screen_classifier import classify_screen_by_rules

logger = logging.getLogger(__name__)

MD_FILE_NAME = "test_plan.md"
XLSX_FILE_NAME = "test_plan.xlsx"

# ---- 見積係数の既定値（1件あたりの手作業想定・分）----
# web/services/usage_tracker.py::MINUTES_PER_SCREEN_SPEC / MINUTES_PER_TEST_CONDITION と同値。
# 層分離のため import はしない（CONVENTIONS.md §1-1・§8 罠1）。
MINUTES_PER_SCREEN_DEFAULT = 45.0
MINUTES_PER_CONDITION_DEFAULT = 10.0

# ---- 優先度重み（本仕様で新設する推定係数。根拠のない断定を避けるため出力に必ず併記する）----
WEIGHT_CRITICAL_DEFAULT = 1.5
WEIGHT_HIGH_DEFAULT = 1.2
WEIGHT_MEDIUM_DEFAULT = 1.0
WEIGHT_LOW_DEFAULT = 0.5

_ENV_MIN_SCREEN = "WEBSPEC2DOC_MIN_PER_SCREEN"
_ENV_MIN_CONDITION = "WEBSPEC2DOC_MIN_PER_CONDITION"
_ENV_WEIGHT_CRITICAL = "WEBSPEC2DOC_PLAN_WEIGHT_CRITICAL"
_ENV_WEIGHT_HIGH = "WEBSPEC2DOC_PLAN_WEIGHT_HIGH"
_ENV_WEIGHT_MEDIUM = "WEBSPEC2DOC_PLAN_WEIGHT_MEDIUM"
_ENV_WEIGHT_LOW = "WEBSPEC2DOC_PLAN_WEIGHT_LOW"

_PRIORITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
_PRIORITY_ORDER = ("critical", "high", "medium", "low")

DISCLAIMER = (
    "この見積は係数に基づく推定値であり実測ではない。"
    "係数は環境変数（WEBSPEC2DOC_MIN_PER_SCREEN 等）で調整できる。"
)


@dataclass(frozen=True)
class PlanCoefficients:
    """見積係数。既定値は usage_tracker と同値（パリティテストで担保）。"""

    minutes_per_screen: float = MINUTES_PER_SCREEN_DEFAULT
    minutes_per_condition: float = MINUTES_PER_CONDITION_DEFAULT
    weight_critical: float = WEIGHT_CRITICAL_DEFAULT
    weight_high: float = WEIGHT_HIGH_DEFAULT
    weight_medium: float = WEIGHT_MEDIUM_DEFAULT
    weight_low: float = WEIGHT_LOW_DEFAULT


@dataclass(frozen=True)
class PlanRow:
    """スコープ表の1行（1 canonical 画面に対応）。"""

    page_id: str
    title: str
    url: str
    screen_type: str
    test_priority: str  # critical/high/medium/low
    priority_source: str  # "画面分類" / "ビジネスフロー: ログイン→決済"
    condition_count: int
    estimated_minutes: float


@dataclass(frozen=True)
class TestPlan:
    """テスト計画ドラフト全体。"""

    rows: tuple[PlanRow, ...]
    total_minutes: float
    total_hours: float  # round(total_minutes / 60.0, 1)
    coefficients: PlanCoefficients
    disclaimer: str


def _env_float(name: str, default: float) -> float:
    """環境変数を float として読む。空・不正値・負値は既定値へフォールバックし警告する。"""
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s の値が不正です（%r）。既定値 %s を使用します。", name, raw, default)
        return default
    if value < 0:
        logger.warning("%s の値が負数です（%r）。既定値 %s を使用します。", name, raw, default)
        return default
    return value


def load_plan_coefficients() -> PlanCoefficients:
    """環境変数を反映した係数を返す。

    既存 env 名（WEBSPEC2DOC_MIN_PER_SCREEN / WEBSPEC2DOC_MIN_PER_CONDITION）を尊重し、
    重みは WEBSPEC2DOC_PLAN_WEIGHT_* で上書きする。
    """
    return PlanCoefficients(
        minutes_per_screen=_env_float(_ENV_MIN_SCREEN, MINUTES_PER_SCREEN_DEFAULT),
        minutes_per_condition=_env_float(_ENV_MIN_CONDITION, MINUTES_PER_CONDITION_DEFAULT),
        weight_critical=_env_float(_ENV_WEIGHT_CRITICAL, WEIGHT_CRITICAL_DEFAULT),
        weight_high=_env_float(_ENV_WEIGHT_HIGH, WEIGHT_HIGH_DEFAULT),
        weight_medium=_env_float(_ENV_WEIGHT_MEDIUM, WEIGHT_MEDIUM_DEFAULT),
        weight_low=_env_float(_ENV_WEIGHT_LOW, WEIGHT_LOW_DEFAULT),
    )


def _priority_rank(priority: str) -> int:
    return _PRIORITY_RANK.get(priority, 0)


def _weight_for(priority: str, coefficients: PlanCoefficients) -> float:
    return {
        "critical": coefficients.weight_critical,
        "high": coefficients.weight_high,
        "medium": coefficients.weight_medium,
        "low": coefficients.weight_low,
    }.get(priority, coefficients.weight_medium)


def _normalize_flow_key(url: str) -> str:
    """business_flows.nodes と画面 URL の照合キー。

    末尾スラッシュ・大文字小文字の差異のみを吸収する（ホスト・パスは保持し、
    複数ドメイン混在時の誤結合を避ける）。仕様外判断（spec §8 参照）。
    """
    text = str(url).strip()
    if len(text) > 1 and text.endswith("/"):
        text = text.rstrip("/")
    return text.lower()


def _build_flow_index(business_flows: list[dict[str, Any]]) -> dict[str, str]:
    """URL（正規化済み）→ flow_name のインデックスを作る。"""
    index: dict[str, str] = {}
    for flow in business_flows:
        flow_name = str(flow.get("flow_name", ""))
        for node in flow.get("nodes") or []:
            key = _normalize_flow_key(str(node))
            index.setdefault(key, flow_name)
    return index


def _condition_count(screen: dict[str, Any]) -> int:
    """テスト条件数の合計。usage_tracker と同じ集計経路（forms[].fields[].test_conditions）。"""
    return sum(
        len(field.get("test_conditions", []))
        for form in screen.get("forms", []) or []
        for field in form.get("fields", []) or []
    )


def _field_names(screen: dict[str, Any]) -> list[str]:
    return [
        str(field.get("name", ""))
        for form in screen.get("forms", []) or []
        for field in form.get("fields", []) or []
    ]


def compute_test_plan(report: dict[str, Any], coefficients: PlanCoefficients) -> TestPlan:
    """report.json の dict から計画を組み立てる純関数（I/O なし・テスト容易）。"""
    screens = [s for s in report.get("screens", []) or [] if s.get("is_canonical", True)]
    business_flows = report.get("meta", {}).get("business_flows") or []
    flow_index = _build_flow_index(business_flows)

    rows: list[PlanRow] = []
    for screen in screens:
        title = str(screen.get("title", ""))
        headings = tuple(str(h) for h in screen.get("headings", []) or [])
        classification = classify_screen_by_rules(title, headings, _field_names(screen))
        test_priority = classification.test_priority
        priority_source = "画面分類"

        url = str(screen.get("url", ""))
        flow_name = flow_index.get(_normalize_flow_key(url))
        if flow_name and _priority_rank(test_priority) < _priority_rank("high"):
            test_priority = "high"
            priority_source = f"ビジネスフロー: {flow_name}"

        condition_count = _condition_count(screen)
        weight = _weight_for(test_priority, coefficients)
        estimated_minutes = (
            weight * coefficients.minutes_per_screen
            + condition_count * coefficients.minutes_per_condition
        )
        rows.append(
            PlanRow(
                page_id=str(screen.get("page_id", "")),
                title=title,
                url=url,
                screen_type=classification.screen_type,
                test_priority=test_priority,
                priority_source=priority_source,
                condition_count=condition_count,
                estimated_minutes=estimated_minutes,
            )
        )

    sorted_rows = tuple(
        sorted(rows, key=lambda r: (-_priority_rank(r.test_priority), -r.estimated_minutes))
    )
    total_minutes = sum(r.estimated_minutes for r in sorted_rows)
    total_hours = round(total_minutes / 60.0, 1)
    return TestPlan(
        rows=sorted_rows,
        total_minutes=total_minutes,
        total_hours=total_hours,
        coefficients=coefficients,
        disclaimer=DISCLAIMER,
    )


def _priority_breakdown(plan: TestPlan) -> list[tuple[str, int, float]]:
    """優先度別（critical→low）の件数・小計分数。"""
    breakdown: list[tuple[str, int, float]] = []
    for priority in _PRIORITY_ORDER:
        subset = [r for r in plan.rows if r.test_priority == priority]
        if subset:
            breakdown.append((priority, len(subset), sum(r.estimated_minutes for r in subset)))
    return breakdown


def _render_markdown(plan: TestPlan) -> str:
    lines = ["# テスト計画ドラフト", ""]
    if not plan.rows:
        lines.append("対象画面 0 件")
        lines.append("")
    else:
        lines.append("## スコープ表")
        lines.append("")
        lines.append(
            "| 画面ID | タイトル | URL | 画面種別 | 優先度 | 優先度根拠 | "
            "テスト条件数 | 見積(分) |"
        )
        lines.append("|---|---|---|---|---|---|---|---|")
        for row in plan.rows:
            lines.append(
                f"| {row.page_id} | {row.title} | {row.url} | {row.screen_type} | "
                f"{row.test_priority} | {row.priority_source} | {row.condition_count} | "
                f"{row.estimated_minutes:.1f} |"
            )
        lines.append("")

    lines.append("## 見積サマリ")
    lines.append("")
    lines.append(f"- 対象画面数: {len(plan.rows)}")
    lines.append(f"- 総見積時間: {plan.total_minutes:.1f} 分（約 {plan.total_hours} 時間）")
    lines.append("- 計算根拠（使用係数）:")
    lines.append(f"  - 1画面あたり: {plan.coefficients.minutes_per_screen} 分")
    lines.append(f"  - テスト条件1件あたり: {plan.coefficients.minutes_per_condition} 分")
    lines.append(
        "  - 優先度重み: "
        f"critical={plan.coefficients.weight_critical} / "
        f"high={plan.coefficients.weight_high} / "
        f"medium={plan.coefficients.weight_medium} / "
        f"low={plan.coefficients.weight_low}"
    )
    breakdown = _priority_breakdown(plan)
    if breakdown:
        lines.append("- 優先度別内訳:")
        for priority, count, subtotal in breakdown:
            lines.append(f"  - {priority}: {count} 画面 / {subtotal:.1f} 分")
    lines.append("")
    lines.append(f"> {plan.disclaimer}")
    lines.append("")
    return "\n".join(lines)


def _write_xlsx(plan: TestPlan, output_dir: Path) -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    scope_sheet = wb.active
    scope_sheet.title = "スコープ表"
    scope_sheet.append(
        [
            "画面ID",
            "タイトル",
            "URL",
            "画面種別",
            "優先度",
            "優先度根拠",
            "テスト条件数",
            "見積(分)",
        ]
    )
    for row in plan.rows:
        scope_sheet.append(
            [
                row.page_id,
                row.title,
                row.url,
                row.screen_type,
                row.test_priority,
                row.priority_source,
                row.condition_count,
                row.estimated_minutes,
            ]
        )

    summary_sheet = wb.create_sheet("見積サマリ")
    summary_sheet.append(["項目", "値"])
    summary_sheet.append(["対象画面数", len(plan.rows)])
    summary_sheet.append(["総見積時間(分)", plan.total_minutes])
    summary_sheet.append(["総見積時間(時間)", plan.total_hours])
    summary_sheet.append(["1画面あたり(分)", plan.coefficients.minutes_per_screen])
    summary_sheet.append(["テスト条件1件あたり(分)", plan.coefficients.minutes_per_condition])
    summary_sheet.append(["重み:critical", plan.coefficients.weight_critical])
    summary_sheet.append(["重み:high", plan.coefficients.weight_high])
    summary_sheet.append(["重み:medium", plan.coefficients.weight_medium])
    summary_sheet.append(["重み:low", plan.coefficients.weight_low])
    for priority, count, subtotal in _priority_breakdown(plan):
        summary_sheet.append([f"内訳:{priority}", f"{count}画面 / {subtotal:.1f}分"])
    summary_sheet.append(["免責", plan.disclaimer])

    wb.save(output_dir / XLSX_FILE_NAME)


def save_test_plan(plan: TestPlan, output_dir: Path) -> None:
    """test_plan.md と test_plan.xlsx を出力する。xlsx 失敗時は md のみ出力し警告する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / MD_FILE_NAME).write_text(_render_markdown(plan), encoding="utf-8")
    try:
        _write_xlsx(plan, output_dir)
    except OSError as exc:
        logger.warning(
            "test_plan.xlsx の書き込みに失敗しました（test_plan.md は出力済みです）: %s", exc
        )
