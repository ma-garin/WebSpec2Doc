"""承認済みテストケースを基に Playwright 自動化の対象を決める（仕様14）。

**承認したケースが自動化の入力になる**という関係を作るのが目的。

ただし正直に言うべきことがある: 承認済みケースは文章（手順・期待結果）であり、
実行可能なセレクタを持たない。セレクタを持つのは実測から作られた候補
（playwright_candidates.json）の側である。

そこで両者を **画面ID で突き合わせ**、

- 承認済みケースに対応する候補だけを自動化対象にする
- **対応する候補が無い承認済みケースは「未自動化」として必ず報告する**
  （黙って落とすと「全部自動化された」と誤読される）

という設計にする。自動化できなかったことは、欠陥が無いことを意味しない。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autorun.stages import STAGE_TEST_CASES, Pipeline


@dataclass(frozen=True)
class CaseCoverage:
    """承認済みケース1件と、それに対応づいた自動化候補。"""

    case_no: int
    title: str
    screen: str
    case_type: str
    candidate_ids: tuple[str, ...] = ()

    @property
    def automated(self) -> bool:
        return bool(self.candidate_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_no": self.case_no,
            "title": self.title,
            "screen": self.screen,
            "case_type": self.case_type,
            "candidate_ids": list(self.candidate_ids),
            "automated": self.automated,
        }


@dataclass(frozen=True)
class AutomationPlan:
    """自動化計画。selected が spec 生成の入力になる。"""

    selected: tuple[dict[str, Any], ...] = ()
    coverage: tuple[CaseCoverage, ...] = ()
    #: 承認済みケースが無い等で、絞り込みを適用しなかった場合 True
    unfiltered: bool = False
    reason: str = ""

    @property
    def automated_count(self) -> int:
        return sum(1 for c in self.coverage if c.automated)

    @property
    def unautomated(self) -> tuple[CaseCoverage, ...]:
        return tuple(c for c in self.coverage if not c.automated)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_candidate_count": len(self.selected),
            "approved_case_count": len(self.coverage),
            "automated_case_count": self.automated_count,
            "unautomated_case_count": len(self.unautomated),
            "unfiltered": self.unfiltered,
            "reason": self.reason,
            "coverage": [c.to_dict() for c in self.coverage],
        }

    def summary_lines(self) -> list[str]:
        """ログ・レポート向けの要約。未自動化を隠さない。"""
        if self.unfiltered:
            return [f"自動化の絞り込みは適用していません（{self.reason}）。"]
        lines = [
            f"承認済みテストケース {len(self.coverage)} 件のうち "
            f"{self.automated_count} 件を自動化対象にしました"
            f"（候補 {len(self.selected)} 件）。"
        ]
        if self.unautomated:
            lines.append(
                f"自動化できなかったケース: {len(self.unautomated)} 件。"
                "これは「確認不要」ではなく「自動では確認していない」という意味です。"
            )
        return lines


def _approved_cases(pipeline: Pipeline) -> list[dict[str, Any]]:
    stage = pipeline.get(STAGE_TEST_CASES)
    if stage is None:
        return []
    return [dict(item.data) for item in stage.items]


def build_plan(pipeline: Pipeline, candidates: list[dict[str, Any]]) -> AutomationPlan:
    """承認済みケースに対応する候補だけを選び、対応関係を返す。

    承認済みケースが無い場合は絞り込まず、全候補をそのまま使う
    （段階承認を使っていない従来の実行を壊さないため）。
    """
    cases = _approved_cases(pipeline)
    if not cases:
        return AutomationPlan(
            selected=tuple(candidates),
            unfiltered=True,
            reason="承認済みテストケースがありません",
        )

    by_screen: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        by_screen.setdefault(str(candidate.get("trace_id") or ""), []).append(candidate)

    coverage: list[CaseCoverage] = []
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for case in cases:
        screen_ids = [str(s) for s in (case.get("_screen_ids") or [])]
        matched: list[str] = []
        for screen_id in screen_ids:
            for candidate in by_screen.get(screen_id, []):
                cid = str(candidate.get("id") or "")
                matched.append(cid)
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    selected.append(candidate)

        coverage.append(
            CaseCoverage(
                case_no=int(case.get("no") or 0),
                title=str(case.get("viewpoint") or ""),
                screen=str(case.get("screen") or ""),
                case_type=str(case.get("case_type") or ""),
                candidate_ids=tuple(matched),
            )
        )

    if not selected:
        # 突合が全く成立しないなら、絞り込まない方が安全（実行できなくなるより良い）
        return AutomationPlan(
            selected=tuple(candidates),
            coverage=tuple(coverage),
            unfiltered=True,
            reason="承認済みケースと自動化候補を突き合わせられませんでした",
        )

    return AutomationPlan(selected=tuple(selected), coverage=tuple(coverage))
