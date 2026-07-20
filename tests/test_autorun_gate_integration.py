"""段階承認がジョブ実行の関門になっていることの結合テスト。

以前、段階UIを作ったのに実行フローへ繋がっておらず、承認を待たずに
最後まで進んでしまっていた。「部品はある」を「動く」と誤認しないよう、
実行の流れそのものを検証する。
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import web.routes.auto_run as auto_run
from web.services.auto_run_job import AutoRunJob


@pytest.fixture()
def job() -> AutoRunJob:
    j = AutoRunJob(job_id="job-test", url="https://example.com/", domain="example.com")
    with auto_run._JOBS_LOCK:
        auto_run._JOBS[j.job_id] = j
    yield j
    with auto_run._JOBS_LOCK:
        auto_run._JOBS.pop(j.job_id, None)


class TestStageGateBlocks:
    def test_gate_waits_until_released(self, job: AutoRunJob, monkeypatch) -> None:
        """承認されるまで先へ進まないこと。"""
        monkeypatch.setattr(auto_run, "STAGE_APPROVAL_TIMEOUT_SEC", 5)
        finished = threading.Event()

        def run() -> None:
            auto_run._await_stage_approval(job, "design")
            finished.set()

        worker = threading.Thread(target=run, daemon=True)
        worker.start()

        # 承認しない間は待ち続ける
        assert not finished.wait(timeout=0.5)
        assert job.status == "awaiting_stages"

        assert auto_run.release_stage_gate(job.job_id, job.domain) is True
        assert finished.wait(timeout=3), "承認後は先へ進むこと"
        worker.join(timeout=3)

    def test_gate_can_be_released_by_domain_without_job_id(self, job: AutoRunJob, monkeypatch) -> None:
        """画面をリロードして job_id を失っても、ドメインで解除できる。"""
        monkeypatch.setattr(auto_run, "STAGE_APPROVAL_TIMEOUT_SEC", 5)
        worker = threading.Thread(target=lambda: auto_run._await_stage_approval(job, "design"), daemon=True)
        worker.start()
        time.sleep(0.2)

        assert auto_run.release_stage_gate("", "example.com") is True
        worker.join(timeout=3)
        assert not worker.is_alive()

    def test_release_is_rejected_when_not_waiting(self, job: AutoRunJob) -> None:
        job.status = "running_tests"
        assert auto_run.release_stage_gate(job.job_id, job.domain) is False

    def test_cancel_releases_the_gate(self, job: AutoRunJob, monkeypatch) -> None:
        """停止したのに承認待ちで固まらないこと。"""
        monkeypatch.setattr(auto_run, "STAGE_APPROVAL_TIMEOUT_SEC", 30)
        worker = threading.Thread(target=lambda: auto_run._await_stage_approval(job, "design"), daemon=True)
        worker.start()
        time.sleep(0.2)

        job.cancel()
        worker.join(timeout=3)
        assert not worker.is_alive(), "cancel() で待機が解除されること"

    def test_timeout_is_logged_as_unapproved(self, job: AutoRunJob, monkeypatch) -> None:
        """タイムアウトで進む場合、未承認であることを記録に残す。"""
        monkeypatch.setattr(auto_run, "STAGE_APPROVAL_TIMEOUT_SEC", 0.2)
        auto_run._await_stage_approval(job, "design")
        joined = "\n".join(job.log)
        assert "タイムアウト" in joined
        assert "未承認" in joined


class TestAutomationBypass:
    """人が承認できない文脈では関門を外せるが、飛ばした事実を必ず残す。"""

    def test_bypass_does_not_block(self, job: AutoRunJob) -> None:
        job.require_stage_approval = False
        auto_run._await_stage_approval(job, "design")  # ブロックしないこと
        assert job.status != "awaiting_stages"

    def test_bypass_is_recorded_in_the_log(self, job: AutoRunJob) -> None:
        job.require_stage_approval = False
        auto_run._await_stage_approval(job, "design")
        joined = "\n".join(job.log)
        assert "スキップ" in joined
        assert "人の確認を経ていません" in joined

    def test_ui_started_jobs_require_approval_by_default(self) -> None:
        """既定は承認必須。黙って飛ばさない。"""
        assert AutoRunJob(job_id="j", url="u").require_stage_approval is True


class TestRunJobOrder:
    def test_gate_runs_before_script_generation(self, monkeypatch) -> None:
        """関門がスクリプト生成より前に入っていること（順序の回帰防止）。"""
        import inspect

        source = inspect.getsource(auto_run._run_job)
        gate_at = source.index('_await_stage_approval(job, "design")')
        scripts_at = source.index("_phase_generate_scripts")
        qa_at = source.index("_phase_generate_qa")
        assert qa_at < gate_at < scripts_at
