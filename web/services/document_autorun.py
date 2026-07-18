"""AutoRun文書駆動モードの設定検証と成果物生成。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mbt.document_model import build_document_mbt, save_document_mbt
from mbt.manual_procedures import build_manual_procedures, save_manual_procedures
from mbt.test_data import generate_test_data, save_test_data
from mbt.validation_observer import run_validation_observation
from web.routes.qa_process import _load_report
from web.services.auto_run_job import AutoRunJob
from web.validation import _domain_of, _safe_reference_doc_paths


@dataclass(frozen=True)
class DocumentAutoRunConfig:
    mode: str
    reference_docs: list[str]
    selection_criterion: str
    target_page_id: str
    observe_validation: bool


def parse_document_autorun_config(
    form: Any, body: dict[str, Any], url: str
) -> DocumentAutoRunConfig:
    """文書駆動固有の開始設定を検証し、正規化する。"""
    mode = str(form.get("mode") or body.get("mode", "url")).strip()
    if mode not in {"url", "document"}:
        raise ValueError("mode must be url or document")
    raw_reference_docs = form.get("reference_docs") or body.get("reference_docs", "")
    if isinstance(raw_reference_docs, list):
        normalized_docs: str | list[str] = [str(item) for item in raw_reference_docs]
    elif isinstance(raw_reference_docs, str):
        normalized_docs = raw_reference_docs
    else:
        normalized_docs = ""
    reference_docs = _safe_reference_doc_paths(normalized_docs, _domain_of(url))
    selection_criterion = str(
        form.get("selection_criterion") or body.get("selection_criterion", "vertex_coverage")
    ).strip()
    if selection_criterion not in {"vertex_coverage", "edge_coverage", "reached_target"}:
        raise ValueError("invalid selection_criterion")
    target_page_id = str(form.get("target_page_id") or body.get("target_page_id", "")).strip()
    if mode == "document" and not reference_docs:
        raise ValueError("文書駆動には有効な参考文書が1件以上必要です")
    if mode == "document" and selection_criterion == "reached_target" and not target_page_id:
        raise ValueError("到達目標には target_page_id が必要です")
    raw_observe = form.get("observe_validation") or body.get("observe_validation", False)
    observe_validation = str(raw_observe).strip().lower() in {"1", "true", "yes", "on"}
    return DocumentAutoRunConfig(
        mode=mode,
        reference_docs=reference_docs,
        selection_criterion=selection_criterion,
        target_page_id=target_page_id,
        observe_validation=observe_validation,
    )


def candidate_filename(mode: str) -> str:
    """モードに対応する、実行対象として選定済みの候補ファイル名。"""
    return (
        "document_playwright_candidates.json"
        if mode == "document"
        else "playwright_candidates.json"
    )


def generate_document_autorun_artifacts(
    job: AutoRunJob, output_dir: Path
) -> tuple[dict[str, Path], dict[str, int | float]]:
    """文書要件と実測画面から第3弾成果物一式と集計を返す。"""
    domain_dir = output_dir / job.domain
    qa_dir = domain_dir / "qa_process"
    report = _load_report(domain_dir / "report.json")
    requirement_trace = _load_report(domain_dir / "requirement_trace.json")
    transition_graph = _load_report(qa_dir / "screen_transition_graph.json")
    candidates = _load_report(qa_dir / "playwright_candidates.json")
    if report is None or transition_graph is None or candidates is None:
        raise ValueError("文書駆動MBTに必要な実測成果物が見つかりません")
    if requirement_trace is None:
        raise ValueError("参考文書から追跡可能な要件を抽出できませんでした")

    model = build_document_mbt(
        transition_graph,
        requirement_trace,
        criterion=job.selection_criterion,
        target_page_id=job.target_page_id,
        candidates_data=candidates,
    )
    outputs = save_document_mbt(model, candidates, qa_dir)
    procedures = build_manual_procedures(model, _attach_measured_screenshots(report, domain_dir))
    outputs |= save_manual_procedures(procedures, qa_dir)
    requirement_ids_by_page = {
        str(node.get("id", "")): [
            str(requirement_id)
            for requirement_id in node.get("requirement_ids", [])
            if str(requirement_id)
        ]
        for node in model.get("nodes", [])
        if isinstance(node, dict) and str(node.get("id", ""))
    }
    test_data = generate_test_data(report, requirement_ids_by_page)
    outputs |= save_test_data(test_data, qa_dir)

    observation_count = 0
    if job.observe_validation:
        observable_cases = [
            case
            for case in test_data
            if case.get("locator")
            and case.get("field_type") not in {"select", "checkbox", "radio", "file", "hidden"}
        ]
        observation_path = run_validation_observation(
            observable_cases,
            qa_dir,
            Path(job.auth_path) if job.auth_path else None,
        )
        outputs["validation_observations_json"] = observation_path
        observation_payload = _load_report(observation_path) or {}
        observation_count = int(observation_payload.get("meta", {}).get("observation_count", 0))

    requirements = [
        item for item in requirement_trace.get("requirements", []) if isinstance(item, dict)
    ]
    summary: dict[str, int | float] = {
        "requirements": len(requirements),
        "matched_requirements": max(
            0, len(requirements) - len(model.get("unmatched_requirements", []))
        ),
        "matched_screens": sum(
            1
            for node in model.get("nodes", [])
            if isinstance(node, dict) and node.get("requirement_ids")
        ),
        "paths": len(model.get("paths", [])),
        "coverage_rate": float(model.get("coverage", {}).get("rate", 0.0)),
        "test_data_cases": len(test_data),
        "validation_observations": observation_count,
    }
    return outputs, summary


def _attach_measured_screenshots(report: dict[str, Any], domain_dir: Path) -> dict[str, Any]:
    """実在するクロール画像だけを手順書向けの相対パスとして結び付ける。"""
    screens: list[dict[str, Any]] = []
    for screen in report.get("screens", []):
        if not isinstance(screen, dict):
            continue
        page_id = str(screen.get("page_id", ""))
        screenshot = domain_dir / "screenshots" / f"{page_id}.png"
        enriched = dict(screen)
        if page_id and screenshot.is_file():
            enriched["screenshot_path"] = f"../screenshots/{page_id}.png"
        screens.append(enriched)
    return {**report, "screens": screens}


def run_document_autorun_phase(
    job: AutoRunJob,
    output_dir: Path,
    mark_failed: Callable[[AutoRunJob, str], None],
) -> None:
    """文書駆動フェーズの状態遷移・成果物登録・失敗処理を一括する。"""
    if job._cancelled:
        return
    job.status = "generating_document_mbt"
    job.step_label = "文書駆動テストを設計中"
    job.add_log("文書要件からMBTモデルとテスト成果物を生成しています…")
    try:
        outputs, summary = generate_document_autorun_artifacts(job, output_dir)
    except (OSError, ValueError, TypeError) as exc:
        mark_failed(job, f"文書駆動MBT成果物の生成に失敗しました: {exc}")
        return
    for key, path in outputs.items():
        if path.is_file():
            job.outputs[key] = str(path.resolve())
    job.step_data["document_mbt"] = summary
    job.add_log(
        f"文書駆動MBT完了: 要件 {summary['requirements']}件 / "
        f"パス {summary['paths']}件 / テストデータ {summary['test_data_cases']}件"
    )
