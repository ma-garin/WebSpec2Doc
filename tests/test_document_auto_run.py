from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from web.routes.auto_run import (
    AutoRunJob,
    _execute_tests,
    _now_iso,
    _phase_crawl,
    _phase_generate_document_mbt,
    _phase_generate_scripts,
    _run_job,
)


def _make_job(**kwargs: Any) -> AutoRunJob:
    defaults: dict[str, Any] = {
        "job_id": "document-job-001",
        "url": "https://example.com",
        "domain": "example.com",
        "started_at": _now_iso(),
    }
    return AutoRunJob(**{**defaults, **kwargs})


def _viewpoint_store() -> MagicMock:
    store = MagicMock()
    store.select_snapshot.return_value = {
        "set_id": "default",
        "set_name": "標準",
        "version": 1,
        "checksum": "abc",
        "selection_reason": "default",
        "viewpoint_count": 0,
        "items": [],
    }
    return store


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _client():
    import app as appmod

    return appmod.app.test_client()


class TestStartDocumentDrivenRoute:
    def test_stores_validated_mbt_configuration(self, tmp_path: Path) -> None:
        doc = tmp_path / "example.com" / "reference_docs" / "requirements.md"
        doc.parent.mkdir(parents=True)
        doc.write_text("# 要件", encoding="utf-8")
        jobs: dict[str, AutoRunJob] = {}

        with (
            patch("web.routes.auto_run._JOBS", jobs),
            patch("web.routes.auto_run.OUTPUT_DIR", tmp_path),
            patch("web.validation.OUTPUT_DIR", tmp_path),
            patch("web.routes.auto_run.get_viewpoint_store", return_value=_viewpoint_store()),
            patch("web.routes.auto_run.threading.Thread"),
        ):
            response = _client().post(
                "/api/autorun/start",
                json={
                    "url": "https://example.com",
                    "mode": "document",
                    "reference_docs": [str(doc)],
                    "selection_criterion": "reached_target",
                    "target_page_id": "P004",
                    "observe_validation": True,
                },
            )

        assert response.status_code == 200
        job = jobs[response.get_json()["job_id"]]
        assert (job.mode, job.selection_criterion, job.target_page_id) == (
            "document",
            "reached_target",
            "P004",
        )
        assert job.observe_validation is True
        assert job._reference_docs == [str(doc.resolve())]
        assert job.to_dict()["reference_doc_count"] == 1

    def test_rejects_reference_path_outside_site_scope(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside.md"
        outside.write_text("# 秘密", encoding="utf-8")
        jobs: dict[str, AutoRunJob] = {}

        with (
            patch("web.routes.auto_run._JOBS", jobs),
            patch("web.routes.auto_run.OUTPUT_DIR", tmp_path),
            patch("web.validation.OUTPUT_DIR", tmp_path),
            patch("web.routes.auto_run.get_viewpoint_store", return_value=_viewpoint_store()),
            patch("web.routes.auto_run.threading.Thread") as thread,
        ):
            response = _client().post(
                "/api/autorun/start",
                json={
                    "url": "https://example.com",
                    "mode": "document",
                    "reference_docs": [str(outside)],
                },
            )

        assert response.status_code == 400
        assert jobs == {}
        thread.assert_not_called()

    def test_port_url_accepts_document_uploaded_under_same_host_key(self, tmp_path: Path) -> None:
        jobs: dict[str, AutoRunJob] = {}

        with (
            patch("web.routes.auto_run._JOBS", jobs),
            patch("web.routes.auto_run.OUTPUT_DIR", tmp_path),
            patch("web.routes.crawl.OUTPUT_DIR", tmp_path),
            patch("web.validation.OUTPUT_DIR", tmp_path),
            patch("web.routes.auto_run.get_viewpoint_store", return_value=_viewpoint_store()),
            patch("web.routes.auto_run.threading.Thread"),
        ):
            upload = _client().post(
                "/api/reference-docs",
                data={
                    "domain": "example.com:8443",
                    "files": (BytesIO(b"# requirement"), "requirements.md"),
                },
                content_type="multipart/form-data",
            )
            assert upload.status_code == 200
            doc = upload.get_json()["saved"][0]["path"]
            response = _client().post(
                "/api/autorun/start",
                json={
                    "url": "https://EXAMPLE.COM:8443",
                    "mode": "document",
                    "reference_docs": [doc],
                },
            )

        assert response.status_code == 200
        job = jobs[response.get_json()["job_id"]]
        assert job._reference_docs == [str(Path(doc).resolve())]


def test_preview_uses_document_candidates(tmp_path: Path) -> None:
    qa_dir = tmp_path / "example.com" / "qa_process"
    _write_json(qa_dir / "playwright_candidates.json", {"candidates": [{"id": "URL"}]})
    _write_json(
        qa_dir / "document_playwright_candidates.json",
        {"candidates": [{"id": "DOC", "automation_status": "auto"}]},
    )
    job = _make_job(mode="document")
    job._output_dir = tmp_path

    with patch("web.routes.auto_run._JOBS", {job.job_id: job}):
        response = _client().get(f"/api/autorun/preview?job_id={job.job_id}")

    assert response.status_code == 200
    assert [item["id"] for item in response.get_json()["candidates"]] == ["DOC"]


def test_document_phase_runs_before_script_generation() -> None:
    job = _make_job(mode="document")
    order: list[str] = []

    def phase(name: str):
        return lambda *_args: order.append(name)

    with (
        patch("web.routes.auto_run._phase_discover", side_effect=phase("discover")),
        patch("web.routes.auto_run._phase_crawl", side_effect=phase("crawl")),
        patch("web.routes.auto_run._phase_generate_qa", side_effect=phase("qa")),
        patch("web.routes.auto_run._phase_generate_document_mbt", side_effect=phase("mbt")),
        patch("web.routes.auto_run._phase_generate_scripts", side_effect=phase("scripts")),
    ):
        _run_job(job, depth=5, max_pages=300)

    assert order == ["discover", "crawl", "qa", "mbt", "scripts"]
    assert job.status == "awaiting_approval"


def test_filter_keeps_document_candidates(tmp_path: Path) -> None:
    qa_dir = tmp_path / "example.com" / "qa_process"
    spec_path = qa_dir / "autorun.spec.ts"
    document_candidates = qa_dir / "document_playwright_candidates.json"
    _write_json(document_candidates, {"candidates": []})
    _write_json(qa_dir / "playwright_candidates.json", {"candidates": [{"id": "URL"}]})
    spec_path.write_text("", encoding="utf-8")
    job = _make_job(mode="document")
    job.outputs = {"spec_ts": str(spec_path)}
    job.run_policy = {"filter_mode": "smoke", "per_test_timeout_sec": 30}
    generated_from: list[Path] = []

    with (
        patch("web.routes.auto_run.OUTPUT_DIR", tmp_path),
        patch("web.routes.auto_run.generate_spec_ts") as generate,
        patch(
            "web.routes.auto_run.run_playwright",
            return_value={"ok": True, "passed": 0, "failed": 0, "total": 0, "tests": []},
        ),
    ):
        generate.side_effect = lambda _domain, source, _output, **_kwargs: generated_from.append(
            source
        )
        _execute_tests(job)

    assert generated_from == [document_candidates]


def test_script_generation_uses_document_candidates(tmp_path: Path) -> None:
    qa_dir = tmp_path / "example.com" / "qa_process"
    _write_json(
        qa_dir / "playwright_candidates.json",
        {"candidates": [{"id": "PW-9999", "title": "URL駆動候補", "steps": []}]},
    )
    _write_json(
        qa_dir / "document_playwright_candidates.json",
        {"candidates": [{"id": "PW-0001", "title": "文書駆動候補", "steps": []}]},
    )
    job = _make_job(mode="document")

    with patch("web.routes.auto_run.OUTPUT_DIR", tmp_path):
        _phase_generate_scripts(job)

    content = Path(job.outputs["spec_ts"]).read_text(encoding="utf-8")
    assert "文書駆動候補" in content
    assert "URL駆動候補" not in content


def test_document_phase_generates_artifacts_and_summary(tmp_path: Path) -> None:
    domain_dir = tmp_path / "example.com"
    qa_dir = domain_dir / "qa_process"
    _write_json(
        domain_dir / "report.json",
        {
            "screens": [
                {"page_id": "P001", "title": "入口", "url": "https://example.com/", "forms": []},
                {
                    "page_id": "P002",
                    "title": "検索",
                    "url": "https://example.com/search",
                    "forms": [],
                },
            ]
        },
    )
    _write_json(
        domain_dir / "requirement_trace.json",
        {
            "meta": {"source_files": ["requirements.md"]},
            "requirements": [{"req_id": "REQ-01", "page_id": "P002", "status": "covered"}],
        },
    )
    screenshots = domain_dir / "screenshots"
    screenshots.mkdir()
    (screenshots / "P001.png").write_bytes(b"measured")
    (screenshots / "P002.png").write_bytes(b"measured")
    _write_json(
        qa_dir / "screen_transition_graph.json",
        {
            "nodes": [
                {"id": "P001", "title": "入口", "url": "https://example.com/"},
                {"id": "P002", "title": "検索", "url": "https://example.com/search"},
            ],
            "edges": [{"from": "P001", "to": "P002", "trace_id": "P001->P002"}],
            "entry_nodes": ["P001"],
        },
    )
    _write_json(
        qa_dir / "playwright_candidates.json",
        {
            "domain": "example.com",
            "candidates": [
                {"id": "PW-0001", "trace_id": "P001", "steps": []},
                {"id": "PW-0002", "trace_id": "P001->P002", "steps": []},
            ],
        },
    )
    job = _make_job(mode="document", selection_criterion="reached_target", target_page_id="P002")

    with patch("web.routes.auto_run.OUTPUT_DIR", tmp_path):
        _phase_generate_document_mbt(job)

    assert job.status != "failed"
    assert job.step_data["document_mbt"] == {
        "requirements": 1,
        "matched_requirements": 1,
        "matched_screens": 1,
        "paths": 1,
        "coverage_rate": 1.0,
        "test_data_cases": 0,
        "validation_observations": 0,
    }
    assert {
        "document_mbt_json",
        "document_candidates_json",
        "manual_procedures_md",
        "manual_procedures_xlsx",
        "test_data_json",
        "test_data_csv",
    } <= job.outputs.keys()
    markdown = Path(job.outputs["manual_procedures_md"]).read_text(encoding="utf-8")
    assert "![P001](../screenshots/P001.png)" in markdown
    assert "![P002](../screenshots/P002.png)" in markdown


def test_crawl_receives_each_reference_document(tmp_path: Path) -> None:
    job = _make_job(mode="document")
    docs = [tmp_path / "requirements.md", tmp_path / "fields.xlsx"]
    for doc in docs:
        doc.write_text("test", encoding="utf-8")
    job._reference_docs = [str(doc.resolve()) for doc in docs]
    commands: list[list[str]] = []

    def fake_popen(command, *args, **kwargs):
        commands.append(command)
        proc = MagicMock()
        proc.stdout = iter([])
        proc.wait.return_value = 0
        return proc

    _write_json(tmp_path / "example.com" / "report.json", {"screens": []})
    with (
        patch("web.routes.auto_run.OUTPUT_DIR", tmp_path),
        patch("web.routes.auto_run.subprocess.Popen", side_effect=fake_popen),
    ):
        _phase_crawl(job, depth=2, max_pages=30)

    command = commands[0]
    assert command.count("--reference-doc") == 2
    assert all(str(doc.resolve()) in command for doc in docs)
