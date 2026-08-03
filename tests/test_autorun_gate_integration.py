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
import web.services.auto_run_pipeline as auto_run_pipeline
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
        monkeypatch.setattr(auto_run_pipeline, "STAGE_APPROVAL_TIMEOUT_SEC", 5)
        finished = threading.Event()

        def run() -> None:
            auto_run._await_stage_approval(job, "test_objective")
            finished.set()

        worker = threading.Thread(target=run, daemon=True)
        worker.start()

        # 承認しない間は待ち続ける
        assert not finished.wait(timeout=0.5)
        assert job.status == "awaiting_stages"

        assert auto_run.release_stage_gate(job.job_id, job.domain) is True
        assert finished.wait(timeout=3), "承認後は先へ進むこと"
        worker.join(timeout=3)

    def test_gate_can_be_released_by_domain_without_job_id(
        self, job: AutoRunJob, monkeypatch
    ) -> None:
        """画面をリロードして job_id を失っても、ドメインで解除できる。"""
        monkeypatch.setattr(auto_run_pipeline, "STAGE_APPROVAL_TIMEOUT_SEC", 5)
        worker = threading.Thread(
            target=lambda: auto_run._await_stage_approval(job, "test_objective"), daemon=True
        )
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
        monkeypatch.setattr(auto_run_pipeline, "STAGE_APPROVAL_TIMEOUT_SEC", 30)
        worker = threading.Thread(
            target=lambda: auto_run._await_stage_approval(job, "test_objective"), daemon=True
        )
        worker.start()
        time.sleep(0.2)

        job.cancel()
        worker.join(timeout=3)
        assert not worker.is_alive(), "cancel() で待機が解除されること"

    def test_timeout_is_recorded_as_unverified(self, job: AutoRunJob, monkeypatch) -> None:
        """タイムアウトで進む場合、未確認として状態に残す。

        ログ1行だけでは成果物を見た人に届かないため、job.unverified に載せる。
        """
        monkeypatch.setattr(auto_run_pipeline, "STAGE_APPROVAL_TIMEOUT_SEC", 0.2)
        auto_run._await_stage_approval(job, "test_objective")
        joined = "\n".join(job.log)
        assert "タイムアウト" in joined
        assert any("人の確認を経ないまま" in note for note in job.unverified)


class TestAutomationBypass:
    """人が承認できない文脈では関門を外せるが、飛ばした事実を必ず残す。"""

    def test_bypass_does_not_block(self, job: AutoRunJob) -> None:
        job.require_stage_approval = False
        auto_run._await_stage_approval(job, "test_objective")  # ブロックしないこと
        assert job.status != "awaiting_stages"

    def test_bypass_is_recorded_as_unverified(self, job: AutoRunJob) -> None:
        job.require_stage_approval = False
        auto_run._await_stage_approval(job, "test_objective")
        joined = "\n".join(job.log)
        assert "人の確認を経ていません" in joined
        assert any("人の確認を経ていません" in note for note in job.unverified)

    def test_ui_started_jobs_require_approval_by_default(self) -> None:
        """既定は承認必須。黙って飛ばさない。"""
        assert AutoRunJob(job_id="j", url="u").require_stage_approval is True


class TestRunJobOrder:
    def test_gate_runs_before_script_generation(self, monkeypatch) -> None:
        """関門がスクリプト生成より前に入っていること（順序の回帰防止）。"""
        import inspect

        source = inspect.getsource(auto_run._run_job)
        gate_at = source.index("for stage_gate in DESIGN_STAGE_IDS")
        scripts_at = source.index("_phase_generate_scripts")
        qa_at = source.index("_phase_generate_qa")
        assert qa_at < gate_at < scripts_at

    def test_each_design_stage_has_its_own_gate(self) -> None:
        """仕様7〜13: 設計段階は1段階ずつ提示・承認する。

        以前は1〜7を1つの関門でまとめて承認させており、開始した途端に
        全段階の内容が一度に出てしまっていた（利用者の操作で発覚）。
        """
        from autorun.stages import DESIGN_STAGE_IDS

        for stage_id in DESIGN_STAGE_IDS:
            assert stage_id in auto_run._GATE_MESSAGES, f"{stage_id} の関門メッセージが無い"
        # 旧来の一括関門は廃止されていること
        assert "design" not in auto_run._GATE_MESSAGES


class TestUnverifiedIsCarriedToOutputs:
    """「確認していない」は状態として残し、成果物まで運ぶ。

    ログに1行流すだけでは、レポートを見た人には届かない。届かない記録は
    「全部確認済み」と誤読される。
    """

    def test_add_unverified_is_deduplicated(self, job: AutoRunJob) -> None:
        job.add_unverified("同じ事項")
        job.add_unverified("同じ事項")
        assert job.unverified == ["同じ事項"]

    def test_add_unverified_ignores_blank(self, job: AutoRunJob) -> None:
        job.add_unverified("   ")
        assert job.unverified == []

    def test_status_payload_exposes_unverified(self, job: AutoRunJob) -> None:
        job.add_unverified("未観測の領域: ログイン後")
        payload = job.to_dict()
        assert payload["unverified"] == ["未観測の領域: ログイン後"]
        assert "awaiting_remaining_sec" in payload

    def test_awaiting_deadline_is_exposed_while_waiting(self, job: AutoRunJob) -> None:
        """期限を出せないと、時間切れは黙って承認されたのと区別がつかない。"""
        import time as _time

        job.awaiting_deadline_epoch = _time.time() + 120
        assert 0 < job.awaiting_remaining_sec() <= 120
        job.awaiting_deadline_epoch = 0.0
        assert job.awaiting_remaining_sec() == 0
