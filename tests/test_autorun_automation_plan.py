"""仕様14: 承認済みテストケースを基に自動化対象を決める。

要点は「未自動化を隠さない」こと。自動化できなかったケースを黙って落とすと
「全部自動化された」と誤読される。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from autorun.automation_plan import build_plan
from autorun.stages import STAGE_TEST_CASES, Pipeline, StageItem


def _pipeline_with_cases(cases: list[dict]) -> Pipeline:
    pipeline = Pipeline.initial()
    stage = pipeline.get(STAGE_TEST_CASES)
    assert stage is not None
    items = tuple(
        StageItem(item_id=f"tc-{i}", title=f"case{i}", data=case)
        for i, case in enumerate(cases, start=1)
    )
    return pipeline.replaced(stage.with_items(items))


CANDIDATES = [
    {"id": "PW-0001", "trace_id": "P001", "title": "トップ表示"},
    {"id": "PW-0002", "trace_id": "P001", "title": "トップ遷移"},
    {"id": "PW-0003", "trace_id": "P002", "title": "予約フォーム"},
    {"id": "PW-0004", "trace_id": "P999", "title": "対応ケースなし"},
]


class TestWithoutApprovedCases:
    """段階承認を使わない従来の実行を壊さない。"""

    def test_uses_all_candidates(self) -> None:
        plan = build_plan(Pipeline.initial(), CANDIDATES)
        assert plan.unfiltered is True
        assert len(plan.selected) == len(CANDIDATES)
        assert "承認済みテストケースがありません" in plan.reason


class TestSelection:
    def test_selects_only_candidates_traced_to_approved_cases(self) -> None:
        pipeline = _pipeline_with_cases([
            {"no": 1, "screen": "トップ", "case_type": "正常系",
             "viewpoint": "表示", "_screen_ids": ["P001"]},
        ])
        plan = build_plan(pipeline, CANDIDATES)
        assert plan.unfiltered is False
        ids = [c["id"] for c in plan.selected]
        assert ids == ["PW-0001", "PW-0002"], "P001 の候補だけが選ばれること"

    def test_does_not_duplicate_shared_candidates(self) -> None:
        pipeline = _pipeline_with_cases([
            {"no": 1, "screen": "トップ", "case_type": "正常系",
             "viewpoint": "表示", "_screen_ids": ["P001"]},
            {"no": 2, "screen": "トップ", "case_type": "異常系",
             "viewpoint": "表示", "_screen_ids": ["P001"]},
        ])
        plan = build_plan(pipeline, CANDIDATES)
        ids = [c["id"] for c in plan.selected]
        assert ids == ["PW-0001", "PW-0002"], "同じ候補を重複させない"


class TestUnautomatedIsReported:
    """自動化できなかったケースを必ず報告する。"""

    def test_case_without_candidate_is_marked_unautomated(self) -> None:
        pipeline = _pipeline_with_cases([
            {"no": 1, "screen": "トップ", "case_type": "正常系",
             "viewpoint": "表示", "_screen_ids": ["P001"]},
            {"no": 2, "screen": "問い合わせ", "case_type": "正常系",
             "viewpoint": "入力検証", "_screen_ids": ["P500"]},
        ])
        plan = build_plan(pipeline, CANDIDATES)
        assert plan.automated_count == 1
        assert [c.case_no for c in plan.unautomated] == [2]

    def test_summary_states_unautomated_is_not_verified(self) -> None:
        pipeline = _pipeline_with_cases([
            {"no": 1, "screen": "トップ", "case_type": "正常系",
             "viewpoint": "表示", "_screen_ids": ["P001"]},
            {"no": 2, "screen": "他", "case_type": "正常系",
             "viewpoint": "表示", "_screen_ids": ["P500"]},
        ])
        text = "\n".join(build_plan(pipeline, CANDIDATES).summary_lines())
        assert "自動化できなかったケース" in text
        assert "自動では確認していない" in text

    def test_coverage_is_serialisable_for_the_report(self) -> None:
        pipeline = _pipeline_with_cases([
            {"no": 1, "screen": "トップ", "case_type": "正常系",
             "viewpoint": "表示", "_screen_ids": ["P001"]},
        ])
        data = build_plan(pipeline, CANDIDATES).to_dict()
        assert data["approved_case_count"] == 1
        assert data["automated_case_count"] == 1
        assert data["coverage"][0]["candidate_ids"] == ["PW-0001", "PW-0002"]


class TestFallbackSafety:
    def test_falls_back_when_nothing_matches(self) -> None:
        """突合が全く成立しないなら、実行不能にするより全候補を使う。"""
        pipeline = _pipeline_with_cases([
            {"no": 1, "screen": "他", "case_type": "正常系",
             "viewpoint": "表示", "_screen_ids": ["P900"]},
        ])
        plan = build_plan(pipeline, CANDIDATES)
        assert plan.unfiltered is True
        assert len(plan.selected) == len(CANDIDATES)
        assert plan.unautomated, "未自動化の事実は残ること"

    def test_handles_cases_without_trace(self) -> None:
        pipeline = _pipeline_with_cases([
            {"no": 1, "screen": "不明", "case_type": "正常系", "viewpoint": "表示"},
        ])
        plan = build_plan(pipeline, CANDIDATES)
        assert plan.unfiltered is True
