"""オートヒーリング（System 05）実行結果の永続化。

1 回の実行（HealingRun）を 1 ファイルに保存する。実行中に画面がポーリングして
読むため、書き込みは必ず一時ファイル → os.replace の原子的置換で行う。

    out_dir/.healing/runs/<run_id>.json
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from web.services.healing.project_store import HEALING_DIR_NAME
from web.services.healing.types import (
    RUN_STATUS_LABELS,
    Defect,
    FixProposal,
    HealingIteration,
    HealingRun,
    PullRequestRef,
    VerifyFailure,
    VerifyResult,
)

#: 1 out_dir あたりに保持する run の上限。超えた分は古いものから削除する。
MAX_RUNS = 200

_RUNS_SUBDIR = "runs"


def runs_dir(out_dir: Path) -> Path:
    return Path(out_dir) / HEALING_DIR_NAME / _RUNS_SUBDIR


def _validate_run_id(run_id: str) -> str:
    """run_id はファイル名に直結するため必ず検証する（defect_store の _safe_domain と同じ考え方）。"""
    text = str(run_id or "").strip()
    if not text:
        raise ValueError("run_id が空です")
    if ".." in text or "/" in text or "\\" in text or "\x00" in text:
        raise ValueError(f"run_id に不正な文字が含まれています: {run_id!r}")
    return text


def _run_path(out_dir: Path, run_id: str) -> Path:
    return runs_dir(out_dir) / f"{_validate_run_id(run_id)}.json"


# ─────────────────────────── dict 変換（往復可能） ───────────────────────────


def _verify_result_to_dict(v: VerifyResult | None) -> dict[str, Any] | None:
    if v is None:
        return None
    data = asdict(v)
    data["failures"] = [asdict(f) for f in v.failures]
    return data


def _verify_result_from_dict(data: Any) -> VerifyResult | None:
    if not isinstance(data, Mapping):
        return None
    failures_raw = data.get("failures") or []
    failures = tuple(
        VerifyFailure(
            test_id=str(f.get("test_id") or ""),
            message=str(f.get("message") or ""),
            file=str(f.get("file") or ""),
            line=int(f.get("line") or 0),
            traceback_tail=str(f.get("traceback_tail") or ""),
        )
        for f in failures_raw
        if isinstance(f, Mapping)
    )
    return VerifyResult(
        ok=bool(data.get("ok")),
        command=str(data.get("command") or ""),
        exit_code=int(data.get("exit_code") or 0),
        duration_sec=float(data.get("duration_sec") or 0.0),
        total=int(data.get("total") or 0),
        passed=int(data.get("passed") or 0),
        failed=int(data.get("failed") or 0),
        failures=failures,
        log_tail=str(data.get("log_tail") or ""),
        started_at=str(data.get("started_at") or ""),
        finished_at=str(data.get("finished_at") or ""),
        error=str(data.get("error") or ""),
    )


def _defect_to_dict(d: Defect) -> dict[str, Any]:
    data = asdict(d)
    data["suspect_files"] = list(d.suspect_files)
    return data


def _defect_from_dict(data: Mapping[str, Any]) -> Defect:
    suspect = data.get("suspect_files") or []
    return Defect(
        defect_id=str(data.get("defect_id") or ""),
        title=str(data.get("title") or ""),
        severity=str(data.get("severity") or "medium"),
        source=str(data.get("source") or "verify"),
        test_id=str(data.get("test_id") or ""),
        message=str(data.get("message") or ""),
        evidence=str(data.get("evidence") or ""),
        suspect_files=tuple(str(s) for s in suspect),
        detected_at=str(data.get("detected_at") or ""),
    )


def _fix_proposal_to_dict(p: FixProposal) -> dict[str, Any]:
    data = asdict(p)
    data["files_changed"] = list(p.files_changed)
    return data


def _fix_proposal_from_dict(data: Mapping[str, Any]) -> FixProposal:
    files_changed = data.get("files_changed") or []
    return FixProposal(
        defect_id=str(data.get("defect_id") or ""),
        agent=str(data.get("agent") or ""),
        status=str(data.get("status") or "proposed"),
        summary=str(data.get("summary") or ""),
        rationale=str(data.get("rationale") or ""),
        diff=str(data.get("diff") or ""),
        files_changed=tuple(str(s) for s in files_changed),
        log_tail=str(data.get("log_tail") or ""),
        duration_sec=float(data.get("duration_sec") or 0.0),
        error=str(data.get("error") or ""),
    )


def _pull_request_from_dict(data: Any) -> PullRequestRef | None:
    if not isinstance(data, Mapping):
        return None
    return PullRequestRef(
        number=int(data.get("number") or 0),
        url=str(data.get("url") or ""),
        state=str(data.get("state") or "open"),
        title=str(data.get("title") or ""),
        branch=str(data.get("branch") or ""),
        checks=str(data.get("checks") or ""),
        created_at=str(data.get("created_at") or ""),
    )


def _iteration_to_dict(it: HealingIteration) -> dict[str, Any]:
    return {
        "index": it.index,
        "verify_before": _verify_result_to_dict(it.verify_before),
        "defects": [_defect_to_dict(d) for d in it.defects],
        "proposals": [_fix_proposal_to_dict(p) for p in it.proposals],
        "verify_after": _verify_result_to_dict(it.verify_after),
        "started_at": it.started_at,
        "finished_at": it.finished_at,
    }


def _iteration_from_dict(data: Mapping[str, Any]) -> HealingIteration:
    defects_raw = data.get("defects") or []
    proposals_raw = data.get("proposals") or []
    return HealingIteration(
        index=int(data.get("index") or 0),
        verify_before=_verify_result_from_dict(data.get("verify_before")),
        defects=[_defect_from_dict(d) for d in defects_raw if isinstance(d, Mapping)],
        proposals=[_fix_proposal_from_dict(p) for p in proposals_raw if isinstance(p, Mapping)],
        verify_after=_verify_result_from_dict(data.get("verify_after")),
        started_at=str(data.get("started_at") or ""),
        finished_at=str(data.get("finished_at") or ""),
    )


def run_to_dict(run: HealingRun) -> dict[str, Any]:
    """HealingRun を JSON 化可能な dict にする。run_from_dict と対で保守する。"""
    return {
        "run_id": run.run_id,
        "project_id": run.project_id,
        "project_name": run.project_name,
        "status": run.status,
        "step_label": run.step_label,
        "branch": run.branch,
        "base_branch": run.base_branch,
        "iterations": [_iteration_to_dict(it) for it in run.iterations],
        "pull_request": asdict(run.pull_request) if run.pull_request is not None else None,
        "log": list(run.log),
        "error": run.error,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "unverified": list(run.unverified),
        "decisions": [dict(d) for d in run.decisions],
    }


def run_from_dict(data: Mapping[str, Any]) -> HealingRun:
    """dict から HealingRun を復元する。未知キーは無視し、古い/新しい run の両方を壊さない。"""
    iterations_raw = data.get("iterations") or []
    decisions_raw = data.get("decisions") or []
    return HealingRun(
        run_id=str(data.get("run_id") or ""),
        project_id=str(data.get("project_id") or ""),
        project_name=str(data.get("project_name") or ""),
        status=str(data.get("status") or "queued"),
        step_label=str(data.get("step_label") or ""),
        branch=str(data.get("branch") or ""),
        base_branch=str(data.get("base_branch") or "main"),
        iterations=[_iteration_from_dict(it) for it in iterations_raw if isinstance(it, Mapping)],
        pull_request=_pull_request_from_dict(data.get("pull_request")),
        log=[str(x) for x in (data.get("log") or [])],
        error=str(data.get("error") or ""),
        started_at=str(data.get("started_at") or ""),
        finished_at=str(data.get("finished_at") or ""),
        unverified=[str(x) for x in (data.get("unverified") or [])],
        decisions=[dict(d) for d in decisions_raw if isinstance(d, Mapping)],
    )


# ─────────────────────────── 入出力 ───────────────────────────


def save_run(out_dir: Path, run: HealingRun) -> None:
    """原子的に保存する。保存後、件数が MAX_RUNS を超えていたら古いものから削除する。"""
    directory = runs_dir(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = _run_path(out_dir, run.run_id)
    payload = run_to_dict(run)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)  # 実行中に読まれるため原子的に置換する
    _prune_old_runs(out_dir)


def load_run(out_dir: Path, run_id: str) -> HealingRun | None:
    path = _run_path(out_dir, run_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, Mapping):
        return None
    try:
        return run_from_dict(data)
    except (TypeError, ValueError):
        return None


def _iter_run_files(out_dir: Path) -> list[Path]:
    directory = runs_dir(out_dir)
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


def list_runs(out_dir: Path, project_id: str = "", limit: int = 50) -> list[HealingRun]:
    """新しい順（started_at 降順、無ければファイル mtime）に返す。壊れた 1 件で全体を落とさない。"""
    entries: list[tuple[HealingRun, float]] = []
    for path in _iter_run_files(out_dir):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, Mapping):
                continue
            run = run_from_dict(data)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue  # 壊れた 1 件で一覧全体を落とさない
        if project_id and run.project_id != project_id:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        entries.append((run, mtime))

    entries.sort(key=lambda entry: (entry[0].started_at or "", entry[1]), reverse=True)
    runs = [run for run, _ in entries]
    return runs[:limit] if limit > 0 else runs


def delete_run(out_dir: Path, run_id: str) -> bool:
    path = _run_path(out_dir, run_id)
    if not path.is_file():
        return False
    path.unlink()
    return True


def _prune_old_runs(out_dir: Path) -> None:
    """MAX_RUNS を超えた分を mtime の古い順に削除する。無限に溜めない。"""
    files = _iter_run_files(out_dir)
    if len(files) <= MAX_RUNS:
        return
    files_by_age = sorted(files, key=lambda p: p.stat().st_mtime)
    excess = len(files_by_age) - MAX_RUNS
    for path in files_by_age[:excess]:
        try:
            path.unlink()
        except OSError:
            pass


def run_summary(run: HealingRun) -> dict[str, Any]:
    """一覧表示用の軽量 dict。"""
    fixed_count = sum(
        1 for it in run.iterations for p in it.proposals if p.status == "applied"
    )
    defect_count = sum(len(it.defects) for it in run.iterations)
    pr = run.pull_request
    return {
        "run_id": run.run_id,
        "project_id": run.project_id,
        "project_name": run.project_name,
        "status": run.status,
        "status_label": RUN_STATUS_LABELS.get(run.status, run.status),
        "step_label": run.step_label,
        "branch": run.branch,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "iterations": len(run.iterations),
        "defect_count": defect_count,
        "fixed_count": fixed_count,
        "pr_number": pr.number if pr else 0,
        "pr_url": pr.url if pr else "",
        "pr_state": pr.state if pr else "",
        "error": run.error,
    }
