"""AutoRun / QA 工程の CLI 化（web.services.autorun_runner / cli_steps）のテスト。

パイプライン本体（`_run_job`）は monkeypatch で差し替え、ランナー側の
「段階承認の自動解除」「ログイン投入」「終了コード判定」のロジックを検証する。
実際のクロール・Playwright 実行は行わない。
"""

from __future__ import annotations

import pytest

pytest.importorskip("flask")


def test_autorun_exit_code() -> None:
    from web.services.autorun_runner import autorun_exit_code

    class _Job:
        status = "complete"
        test_results: dict = {}

    job = _Job()
    job.test_results = {"failed": 0, "total": 3}
    assert autorun_exit_code(job) == 0

    job.test_results = {"failed": 2}
    assert autorun_exit_code(job) == 1

    job.status = "failed"
    job.test_results = {}
    assert autorun_exit_code(job) == 2

    job.status = "cancelled"
    assert autorun_exit_code(job) == 130


def test_run_autorun_job_auto_approves_stages(monkeypatch) -> None:
    import web.routes.auto_run as auto_run
    from web.services import autorun_runner
    from web.services.auto_run_job import AutoRunJob

    approvals: list[str] = []

    def fake_run_job(job: AutoRunJob, depth: int, max_pages: int) -> None:
        for gate in ("test_objective", "playwright"):
            job.status = "awaiting_stages"
            job.awaiting_stage_id = gate
            assert job._stages_event.wait(3), f"{gate} が承認されなかった"
            job._stages_event.clear()
            job.awaiting_stage_id = ""
            approvals.append(gate)
        job.status = "complete"
        job.test_results = {"passed": 1, "failed": 0, "total": 1}

    monkeypatch.setattr(auto_run, "_run_job", fake_run_job)

    job = AutoRunJob(job_id="t1", url="https://example.com")
    logs: list[str] = []
    autorun_runner.run_autorun_job(job, 1, 1, on_log=logs.append, poll_interval=0.01)

    assert approvals == ["test_objective", "playwright"]
    assert job.status == "complete"
    assert autorun_runner.autorun_exit_code(job) == 0


def test_run_autorun_job_injects_login(monkeypatch) -> None:
    import web.routes.auto_run as auto_run
    from web.services import autorun_runner
    from web.services.auto_run_job import AutoRunJob

    received: dict = {}

    def fake_run_job(job: AutoRunJob, depth: int, max_pages: int) -> None:
        job.status = "awaiting_input"
        assert job._input_event.wait(3), "ログイン入力が投入されなかった"
        received.update(job._input_data)
        job.status = "complete"

    monkeypatch.setattr(auto_run, "_run_job", fake_run_job)

    job = AutoRunJob(job_id="t2", url="https://example.com")
    autorun_runner.run_autorun_job(
        job,
        1,
        1,
        login={"username": "alice", "password": "secret"},
        poll_interval=0.01,
    )
    assert received.get("username") == "alice"
    assert received.get("password") == "secret"


def test_run_autorun_job_skips_login_without_credentials(monkeypatch) -> None:
    import web.routes.auto_run as auto_run
    from web.services import autorun_runner
    from web.services.auto_run_job import AutoRunJob

    received: dict = {}

    def fake_run_job(job: AutoRunJob, depth: int, max_pages: int) -> None:
        job.status = "awaiting_input"
        assert job._input_event.wait(3)
        received.update(job._input_data)
        job.status = "complete"

    monkeypatch.setattr(auto_run, "_run_job", fake_run_job)

    job = AutoRunJob(job_id="t3", url="https://example.com")
    autorun_runner.run_autorun_job(job, 1, 1, poll_interval=0.01)
    assert received.get("skip") is True


def test_run_qa_process_missing_report_raises(tmp_path) -> None:
    from web.services.cli_steps import CliStepError, run_qa_process

    with pytest.raises(CliStepError):
        run_qa_process("example.com", tmp_path)


def test_run_gen_spec_missing_candidates_raises(tmp_path) -> None:
    from web.services.cli_steps import CliStepError, run_gen_spec

    with pytest.raises(CliStepError):
        run_gen_spec("example.com", tmp_path)


def test_run_tests_missing_spec_raises(tmp_path) -> None:
    from web.services.cli_steps import CliStepError, run_tests

    with pytest.raises(CliStepError):
        run_tests("example.com", tmp_path)
