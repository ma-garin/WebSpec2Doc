"""仕様7〜13「提示・承認」— 内容が自動で提示されることのテスト。

利用者の仕様は「テスト目的の**提示**・承認」であり、
利用者に「内容を生成」を押させることではない。

また、同一ドメインの過去実行で保存された stages.json が残っていると、
古い内容（例: テスト技法が適用されていない基本設計）がそのまま提示される
問題があった。関門到達時に生成し直すことで両方を解消する。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import web.routes.auto_run as auto_run
from web.services.auto_run_job import AutoRunJob

from autorun.stages import STAGE_BASIC_DESIGN, STAGE_TEST_OBJECTIVE, Pipeline

DOMAIN = "example.com"

_REPORT = {
    "meta": {"page_count": 1, "screen_count": 1},
    "screens": [
        {
            "page_id": "P001",
            "title": "予約",
            "url": "https://example.com/reserve",
            "forms": [
                {
                    "action": "./confirm",
                    "method": "get",
                    "fields": [
                        {
                            "name": "term",
                            "field_type": "number",
                            "required": True,
                            "min_value": "1",
                            "max_value": "9",
                        },
                        {"name": "username", "field_type": "text", "required": True},
                    ],
                }
            ],
            "transitions": {"to": [], "from": []},
        }
    ],
}


@pytest.fixture()
def job(tmp_path) -> AutoRunJob:
    (tmp_path / DOMAIN).mkdir(parents=True)
    (tmp_path / DOMAIN / "report.json").write_text(
        json.dumps(_REPORT, ensure_ascii=False), encoding="utf-8"
    )
    j = AutoRunJob(job_id="j-auto", url="https://example.com/", domain=DOMAIN)
    j._output_dir = tmp_path
    return j


def _pipeline(job: AutoRunJob) -> Pipeline:
    path = job._output_dir / DOMAIN / "qa_process" / "stages.json"
    return Pipeline.from_dict(json.loads(path.read_text(encoding="utf-8")))


class TestAutoPresentation:
    def test_content_is_presented_without_manual_generation(self, job: AutoRunJob) -> None:
        """初回（stages.json が無い）でも、押さずに内容が用意される。"""
        auto_run._ensure_stage_content(job, STAGE_TEST_OBJECTIVE)
        stage = _pipeline(job).get(STAGE_TEST_OBJECTIVE)
        assert len(stage.items) > 0

    def test_basic_design_includes_applied_techniques(self, job: AutoRunJob) -> None:
        """技法は名前だけでなく、実測項目へ適用された具体値として提示される。"""
        auto_run._ensure_stage_content(job, STAGE_BASIC_DESIGN)
        items = _pipeline(job).get(STAGE_BASIC_DESIGN).items
        technique_items = [i for i in items if i.item_id.startswith("tech-")]
        assert technique_items, "技法を適用した項目が無い"
        details = "\n".join(i.detail for i in technique_items)
        assert "下限" in details or "上限" in details  # 境界値
        assert "規則 |" in details  # デシジョンテーブル

    def test_stale_content_is_regenerated(self, job: AutoRunJob) -> None:
        """過去実行の古い内容が残っていても、実行のたびに作り直される。"""
        qa = job._output_dir / DOMAIN / "qa_process"
        qa.mkdir(parents=True, exist_ok=True)
        stale = Pipeline.initial()
        stale_stage = stale.get(STAGE_BASIC_DESIGN)
        # 技法適用が無い「古い」状態を作る
        assert not [i for i in stale_stage.items if i.item_id.startswith("tech-")]
        (qa / "stages.json").write_text(
            json.dumps(stale.to_dict(), ensure_ascii=False), encoding="utf-8"
        )

        auto_run._ensure_stage_content(job, STAGE_BASIC_DESIGN)

        items = _pipeline(job).get(STAGE_BASIC_DESIGN).items
        assert [i for i in items if i.item_id.startswith("tech-")]

    def test_generation_is_recorded_in_audit(self, job: AutoRunJob) -> None:
        """提示した事実を監査に残す。"""
        auto_run._ensure_stage_content(job, STAGE_TEST_OBJECTIVE)
        assert any(e.action == "generate" for e in _pipeline(job).audit)

    def test_failure_does_not_break_the_run(self, job: AutoRunJob) -> None:
        """内容を用意できなくても実行は止めない（手動生成の余地を残す）。"""
        auto_run._ensure_stage_content(job, "unknown_stage")
        assert job.status != "failed"

    def test_missing_report_still_produces_content(self, job: AutoRunJob) -> None:
        """実測が無くても、目的・計画のような段階は提示できる。"""
        (job._output_dir / DOMAIN / "report.json").unlink()
        auto_run._ensure_stage_content(job, STAGE_TEST_OBJECTIVE)
        assert len(_pipeline(job).get(STAGE_TEST_OBJECTIVE).items) > 0
