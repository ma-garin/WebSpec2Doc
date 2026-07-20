"""AutoRun 段階承認パイプライン（仕様7〜13）のテスト。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from autorun.qf_schema import COLUMN_KEYS, COLUMN_LABELS, TestCaseRow, renumber, to_csv
from autorun.stages import (
    STAGE_BASIC_DESIGN,
    STAGE_DETAIL_DESIGN,
    STAGE_FEATURES,
    STAGE_ORDER,
    STAGE_TEST_CASES,
    STAGE_TEST_OBJECTIVE,
    STAGE_TEST_PLAN,
    STAGE_VIEWPOINTS,
    STATUS_APPROVED,
    STATUS_PENDING,
    Pipeline,
    build_stage,
    observation_from_report,
)
# pytest が `test_` 始まりの関数をテストとして収集しないよう別名で取り込む
from autorun.stages import test_case_rows as collect_test_case_rows

REPORT = {
    "screens": [
        {
            "page_id": "P001",
            "url": "https://example.com/",
            "title": "トップ",
            "forms": [],
            "transitions": {"to": ["P002"], "from": []},
        },
        {
            "page_id": "P002",
            "url": "https://example.com/reserve.html",
            "title": "宿泊予約",
            "forms": [
                {
                    "inputs": [
                        {"name": "date", "required": True},
                        {"name": "nights", "required": True},
                        {"name": "mail", "required": False},
                    ]
                }
            ],
            "transitions": {"to": ["P003"], "from": ["P001"]},
        },
        {
            "page_id": "P003",
            "url": "https://example.com/reserve.html?plan=2",
            "title": "宿泊予約（プラン2）",
            "forms": [{"inputs": [{"name": "date", "required": True}]}],
            "transitions": {"to": [], "from": ["P002"]},
        },
    ]
}


@pytest.fixture()
def obs():
    return observation_from_report(REPORT, url="https://example.com/")


def _approve_all_items(pipeline: Pipeline, stage_id: str) -> Pipeline:
    stage = pipeline.get(stage_id)
    assert stage is not None
    for item in stage.items:
        stage = stage.with_item(item.with_approval(True))
    return pipeline.replaced(stage)


def _run_through(obs, upto: str) -> Pipeline:
    """指定段階まで生成・承認して進める。"""
    pipeline = Pipeline.initial()
    for stage_id in STAGE_ORDER:
        pipeline = pipeline.replaced(build_stage(stage_id, obs, pipeline))
        stage = pipeline.get(stage_id)
        assert stage is not None
        if stage.definition.requires_item_approval:
            pipeline = _approve_all_items(pipeline, stage_id)
            stage = pipeline.get(stage_id)
        assert stage is not None
        pipeline = pipeline.replaced(stage.with_status(STATUS_APPROVED))
        if stage_id == upto:
            break
    return pipeline


class TestObservation:
    def test_counts_screens_inputs_and_transitions(self, obs) -> None:
        assert obs.screen_count == 3
        assert obs.input_count == 4
        assert obs.required_input_count == 3
        assert obs.transition_count == 2

    def test_reads_fields_key_used_by_real_reports(self) -> None:
        """report.json は `fields` を使う。`inputs` 決め打ちだと 0 件になる。"""
        report = {
            "screens": [
                {
                    "page_id": "P001",
                    "url": "https://example.com/a",
                    "title": "A",
                    "forms": [
                        {
                            "action": "/submit",
                            "method": "post",
                            "fields": [
                                {"name": "x", "required": True},
                                {"name": "y", "required": False},
                            ],
                        }
                    ],
                    "transitions": {"to": [], "from": []},
                }
            ]
        }
        obs = observation_from_report(report)
        assert obs.input_count == 2
        assert obs.required_input_count == 1

    def test_accepts_inputs_key_as_fallback(self) -> None:
        report = {
            "screens": [
                {
                    "page_id": "P001",
                    "url": "https://example.com/a",
                    "title": "A",
                    "forms": [{"inputs": [{"name": "x", "required": True}]}],
                    "transitions": {"to": [], "from": []},
                }
            ]
        }
        obs = observation_from_report(report)
        assert obs.input_count == 1


class TestPipelineBasics:
    def test_starts_pending_at_first_stage(self) -> None:
        pipeline = Pipeline.initial()
        assert pipeline.current_stage_id == STAGE_TEST_OBJECTIVE
        assert not pipeline.all_approved
        assert all(s.status == STATUS_PENDING for s in pipeline.stages)

    def test_has_seven_stages_in_spec_order(self) -> None:
        assert len(STAGE_ORDER) == 7
        assert STAGE_ORDER[0] == STAGE_TEST_OBJECTIVE
        assert STAGE_ORDER[-1] == STAGE_TEST_CASES

    def test_round_trips_through_dict(self, obs) -> None:
        pipeline = _run_through(obs, STAGE_FEATURES)
        restored = Pipeline.from_dict(pipeline.to_dict())
        assert restored.current_stage_id == pipeline.current_stage_id
        assert len(restored.get(STAGE_FEATURES).items) == len(pipeline.get(STAGE_FEATURES).items)


class TestTestObjective:
    """仕様7: テスト目的の提示。"""

    def test_proposes_istqb_objectives(self, obs) -> None:
        stage = build_stage(STAGE_TEST_OBJECTIVE, obs, Pipeline.initial())
        titles = [i.title for i in stage.items]
        assert "欠陥の摘出" in titles
        assert "カバレッジの確保" in titles

    def test_adds_risk_objective_when_required_inputs_exist(self, obs) -> None:
        stage = build_stage(STAGE_TEST_OBJECTIVE, obs, Pipeline.initial())
        assert any("リスク" in i.title for i in stage.items)

    def test_first_run_declares_baseline_only(self, obs) -> None:
        """前回スナップショットが無い初回は「基準の確立」を前提として明示する。"""
        stage = build_stage(STAGE_TEST_OBJECTIVE, obs, Pipeline.initial())
        baseline = next(i for i in stage.items if i.item_id == "obj-baseline")
        assert baseline.assumed is True
        assert "次回以降" in baseline.detail

    def test_rerun_offers_regression_objective(self) -> None:
        obs = observation_from_report(REPORT, url="https://example.com/", has_previous_snapshot=True)
        stage = build_stage(STAGE_TEST_OBJECTIVE, obs, Pipeline.initial())
        assert any(i.item_id == "obj-regression" for i in stage.items)


class TestTestPlan:
    """仕様8: テスト計画の提示。"""

    def test_marks_unobservable_matters_as_assumptions(self, obs) -> None:
        stage = build_stage(STAGE_TEST_PLAN, obs, Pipeline.initial())
        assumed = [i for i in stage.items if i.assumed]
        ids = {i.item_id for i in assumed}
        assert {"plan-assume-browser", "plan-assume-auth", "plan-assume-exit"} <= ids

    def test_declares_claim_scope(self, obs) -> None:
        stage = build_stage(STAGE_TEST_PLAN, obs, Pipeline.initial())
        scope = next(i for i in stage.items if i.item_id == "plan-claim-scope")
        assert "未検証" in scope.detail
        assert "証明しない" in scope.detail

    def test_is_skippable_on_rerun_only(self) -> None:
        assert Pipeline.initial().get(STAGE_TEST_PLAN).definition.skippable_on_rerun is True
        assert Pipeline.initial().get(STAGE_FEATURES).definition.skippable_on_rerun is False


class TestFeatures:
    """仕様9: 全フィーチャーの承認が必要。"""

    def test_groups_screens_into_features(self, obs) -> None:
        stage = build_stage(STAGE_FEATURES, obs, Pipeline.initial())
        assert len(stage.items) >= 2  # top と reserve

    def test_cannot_approve_until_every_item_approved(self, obs) -> None:
        pipeline = Pipeline.initial()
        pipeline = pipeline.replaced(build_stage(STAGE_FEATURES, obs, pipeline))
        stage = pipeline.get(STAGE_FEATURES)
        assert stage.can_approve is False

        pipeline = _approve_all_items(pipeline, STAGE_FEATURES)
        assert pipeline.get(STAGE_FEATURES).can_approve is True

    def test_one_unapproved_item_blocks_the_stage(self, obs) -> None:
        pipeline = Pipeline.initial()
        pipeline = pipeline.replaced(build_stage(STAGE_FEATURES, obs, pipeline))
        pipeline = _approve_all_items(pipeline, STAGE_FEATURES)
        stage = pipeline.get(STAGE_FEATURES)
        stage = stage.with_item(stage.items[0].with_approval(False))
        assert stage.can_approve is False


class TestViewpointsAndDesign:
    def test_viewpoints_skip_input_checks_for_formless_features(self, obs) -> None:
        pipeline = _run_through(obs, STAGE_FEATURES)
        stage = build_stage(STAGE_VIEWPOINTS, obs, pipeline)
        top = [i for i in stage.items if "トップ" in i.title]
        assert top, "トップ画面の観点が生成されていること"
        assert not any("入力検証" in i.title for i in top)

    def test_basic_design_assigns_techniques(self, obs) -> None:
        pipeline = _run_through(obs, STAGE_VIEWPOINTS)
        stage = build_stage(STAGE_BASIC_DESIGN, obs, pipeline)
        techniques = {i.data.get("technique") for i in stage.items}
        assert "同値分割・境界値分析" in techniques
        assert "状態遷移テスト" in techniques

    def test_detail_design_covers_normal_and_abnormal(self, obs) -> None:
        pipeline = _run_through(obs, STAGE_BASIC_DESIGN)
        stage = build_stage(STAGE_DETAIL_DESIGN, obs, pipeline)
        types = {i.data.get("case_type") for i in stage.items}
        assert types == {"正常系", "異常系"}


class TestTestCases:
    """仕様13: QualityForward のカラム構成。"""

    def test_generates_rows_for_every_high_level_case(self, obs) -> None:
        pipeline = _run_through(obs, STAGE_DETAIL_DESIGN)
        stage = build_stage(STAGE_TEST_CASES, obs, pipeline)
        detail = pipeline.get(STAGE_DETAIL_DESIGN)
        assert len(stage.items) == len(detail.items)

    def test_rows_carry_all_qualityforward_columns(self, obs) -> None:
        pipeline = _run_through(obs, STAGE_DETAIL_DESIGN)
        pipeline = pipeline.replaced(build_stage(STAGE_TEST_CASES, obs, pipeline))
        rows = collect_test_case_rows(pipeline)
        assert rows
        for row in rows:
            data = row.to_dict()
            for key in COLUMN_KEYS:
                assert key in data

    def test_precondition_is_concrete_not_tautological(self, obs) -> None:
        """前提条件は「どの画面か」「認証状態」を具体的に書く。

        「対象画面へ到達できる状態」のような同義反復は前提条件として機能しない。
        """
        pipeline = _run_through(obs, STAGE_DETAIL_DESIGN)
        pipeline = pipeline.replaced(build_stage(STAGE_TEST_CASES, obs, pipeline))
        rows = collect_test_case_rows(pipeline)
        assert rows
        for row in rows:
            assert "到達できる状態" not in row.precondition
            # 対象URL か画面名のいずれかが具体的に入っていること
            assert ("対象URL:" in row.precondition) or ("対象画面:" in row.precondition)
            assert "未認証" in row.precondition

    def test_steps_reference_the_observed_url(self, obs) -> None:
        pipeline = _run_through(obs, STAGE_DETAIL_DESIGN)
        pipeline = pipeline.replaced(build_stage(STAGE_TEST_CASES, obs, pipeline))
        rows = collect_test_case_rows(pipeline)
        assert any("https://example.com" in row.steps for row in rows)

    def test_steps_name_actual_input_fields(self, obs) -> None:
        """入力項目がある画面では、手順に実際の項目名を出す。"""
        pipeline = _run_through(obs, STAGE_DETAIL_DESIGN)
        pipeline = pipeline.replaced(build_stage(STAGE_TEST_CASES, obs, pipeline))
        rows = collect_test_case_rows(pipeline)
        assert any("date" in row.steps or "nights" in row.steps for row in rows)

    def test_numbers_are_sequential_from_one(self, obs) -> None:
        pipeline = _run_through(obs, STAGE_DETAIL_DESIGN)
        pipeline = pipeline.replaced(build_stage(STAGE_TEST_CASES, obs, pipeline))
        rows = collect_test_case_rows(pipeline)
        assert [r.no for r in rows] == list(range(1, len(rows) + 1))


class TestQualityForwardSchema:
    def test_column_order_matches_specification(self) -> None:
        assert COLUMN_LABELS == (
            "No",
            "画面",
            "正常系/異常系",
            "観点名",
            "大項目",
            "中項目",
            "小項目",
            "前提条件",
            "手順",
            "期待結果",
            "備考",
        )

    def test_csv_header_uses_japanese_labels(self) -> None:
        rows = renumber(
            [
                TestCaseRow(
                    no=0,
                    screen="予約",
                    case_type="正常系",
                    viewpoint="入力検証",
                    category_large="予約",
                    category_medium="入力検証",
                )
            ]
        )
        csv_text = to_csv(rows)
        assert csv_text.splitlines()[0] == ",".join(COLUMN_LABELS)

    def test_renumber_does_not_mutate_original(self) -> None:
        original = TestCaseRow(
            no=99, screen="s", case_type="正常系", viewpoint="v",
            category_large="l", category_medium="m",
        )
        renumbered = original.renumbered(1)
        assert original.no == 99
        assert renumbered.no == 1
