"""AutoRun 実行フローへの自己検証（ミューテーションテスト）組み込みの結合テスト。

_run_mutation_self_check が結果を記録すること、_publish_playwright_stage が
その結果を段階8（Playwright自動化）の項目として承認前に提示することを確認する。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import web.routes.auto_run as auto_run
from autorun.stages import STAGE_PLAYWRIGHT, Pipeline
from web.services.auto_run_job import AutoRunJob


@pytest.fixture()
def job() -> AutoRunJob:
    j = AutoRunJob(job_id="job-mut", url="https://example.com/", domain="example.com")
    with auto_run._JOBS_LOCK:
        auto_run._JOBS[j.job_id] = j
    yield j
    with auto_run._JOBS_LOCK:
        auto_run._JOBS.pop(j.job_id, None)


class TestMutationSelfCheckPhase:
    def test_writes_result_file_and_logs_score(self, job: AutoRunJob, tmp_path: Path) -> None:
        spec_path = tmp_path / "autorun.spec.ts"
        spec_path.write_text("import { test } from '@playwright/test';\n", encoding="utf-8")

        fake = {
            "ok": True,
            "applicable": True,
            "total": 10,
            "detected": 9,
            "survivors": ["PW-0005 フォーム入力 [P001-F01-I01]"],
            "survivor_count": 1,
            "score": 90.0,
            "duration_ms": 1000,
        }
        with patch("web.services.mutation_verifier.run_self_check", return_value=fake):
            auto_run._run_mutation_self_check(job, spec_path, tmp_path)

        result_path = tmp_path / "mutation_verification.json"
        assert result_path.is_file()
        saved = json.loads(result_path.read_text(encoding="utf-8"))
        assert saved["score"] == 90.0
        assert any("90.0" in line for line in job.log)
        assert any("弱いテスト" in line for line in job.log)

    def test_not_applicable_is_logged_without_error(self, job: AutoRunJob, tmp_path: Path) -> None:
        spec_path = tmp_path / "autorun.spec.ts"
        spec_path.write_text("import { test } from '@playwright/test';\n", encoding="utf-8")

        fake = {"ok": True, "applicable": False, "note": "対象がありません。"}
        with patch("web.services.mutation_verifier.run_self_check", return_value=fake):
            auto_run._run_mutation_self_check(job, spec_path, tmp_path)

        assert any("対象がありません" in line for line in job.log)

    def test_exception_is_logged_not_raised(self, job: AutoRunJob, tmp_path: Path) -> None:
        spec_path = tmp_path / "autorun.spec.ts"
        spec_path.write_text("import { test } from '@playwright/test';\n", encoding="utf-8")

        with patch(
            "web.services.mutation_verifier.run_self_check", side_effect=RuntimeError("boom")
        ):
            auto_run._run_mutation_self_check(job, spec_path, tmp_path)

        assert any("自己検証を実行できませんでした" in line for line in job.log)


class TestPublishPlaywrightStageSurfacesSelfCheck:
    def test_appends_self_check_item_with_survivors(
        self, job: AutoRunJob, tmp_path: Path
    ) -> None:
        (tmp_path / "stages.json").write_text(
            json.dumps(Pipeline.initial().to_dict(), ensure_ascii=False), encoding="utf-8"
        )
        (tmp_path / "mutation_verification.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "applicable": True,
                    "total": 5,
                    "detected": 4,
                    "survivors": ["PW-0002 必須入力 [P001-F01-I01]"],
                    "survivor_count": 1,
                    "score": 80.0,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        auto_run._publish_playwright_stage(job, tmp_path)

        saved = Pipeline.from_dict(json.loads((tmp_path / "stages.json").read_text()))
        stage = saved.get(STAGE_PLAYWRIGHT)
        self_check_items = [i for i in stage.items if i.item_id == "pw-self-check"]
        assert len(self_check_items) == 1
        item = self_check_items[0]
        assert "80.0%" in item.title
        assert "PW-0002 必須入力 [P001-F01-I01]" in item.detail
        assert item.assumed is True  # 弱いテストがある場合は前提扱いで注意喚起する

    def test_no_self_check_item_when_result_file_missing(
        self, job: AutoRunJob, tmp_path: Path
    ) -> None:
        (tmp_path / "stages.json").write_text(
            json.dumps(Pipeline.initial().to_dict(), ensure_ascii=False), encoding="utf-8"
        )

        auto_run._publish_playwright_stage(job, tmp_path)

        saved = Pipeline.from_dict(json.loads((tmp_path / "stages.json").read_text()))
        stage = saved.get(STAGE_PLAYWRIGHT)
        assert all(i.item_id != "pw-self-check" for i in stage.items)

    def test_no_survivors_marks_item_not_assumed(self, job: AutoRunJob, tmp_path: Path) -> None:
        (tmp_path / "stages.json").write_text(
            json.dumps(Pipeline.initial().to_dict(), ensure_ascii=False), encoding="utf-8"
        )
        (tmp_path / "mutation_verification.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "applicable": True,
                    "total": 5,
                    "detected": 5,
                    "survivors": [],
                    "survivor_count": 0,
                    "score": 100.0,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        auto_run._publish_playwright_stage(job, tmp_path)

        saved = Pipeline.from_dict(json.loads((tmp_path / "stages.json").read_text()))
        stage = saved.get(STAGE_PLAYWRIGHT)
        item = next(i for i in stage.items if i.item_id == "pw-self-check")
        assert item.assumed is False
        assert "100.0%" in item.title
