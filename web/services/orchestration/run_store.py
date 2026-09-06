"""指揮（O2）1 回分の記録と、その永続化。

    out_dir/.orchestration/runs/<run_id>.json

05（web/services/healing/run_store.py）と同じ流儀。画面は実行中にポーリングで
読むため、書き込みは一時ファイル → replace の原子的置換で行う。dataclass を
凍結しないのは、指揮者のスレッドが 1 つの実行を進めながら書き換えるため。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

#: 出力先。05 の .healing と並ぶ位置に置く。
ORCHESTRATION_DIR_NAME = ".orchestration"

#: 1 out_dir あたりに保持する実行の上限。超えた分は古いものから消す。
MAX_RUNS = 200

_RUNS_SUBDIR = "runs"


@dataclass
class StepRecord:
    """1 段の記録。status の語彙は ports.STEP_STATES（＋ queued / cancelled）。"""

    name: str
    label: str = ""
    status: str = "queued"
    summary: str = ""
    artifacts: dict[str, str] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    handle: str = ""
    human_action: str = ""
    error: str = ""
    started_at: str = ""
    finished_at: str = ""


@dataclass
class ConductorRun:
    """指揮 1 回分。step_index は「いま何段目か」。"""

    run_id: str
    domain: str
    goal: str
    project_id: str = ""
    status: str = "queued"
    step_index: int = 0
    steps: list[StepRecord] = field(default_factory=list)
    human_action: str = ""
    error: str = ""
    started_at: str = ""
    finished_at: str = ""
    log: list[str] = field(default_factory=list)
    actor: str = ""
    params: dict[str, Any] = field(default_factory=dict)


_STEP_TEXT = ("label", "status", "summary", "handle", "human_action", "error",
              "started_at", "finished_at")
_RUN_TEXT = ("domain", "goal", "project_id", "status", "human_action", "error",
             "started_at", "finished_at", "actor")


def runs_dir(out_dir: Path) -> Path:
    return Path(out_dir) / ORCHESTRATION_DIR_NAME / _RUNS_SUBDIR


def _run_path(out_dir: Path, run_id: str) -> Path:
    """run_id はファイル名に直結するため必ず検証する（05 と同じ考え方）。"""
    text = str(run_id or "").strip()
    if not text:
        raise ValueError("run_id が空です")
    if ".." in text or "/" in text or "\\" in text or "\x00" in text:
        raise ValueError(f"run_id に不正な文字が含まれています: {run_id!r}")
    return runs_dir(out_dir) / f"{text}.json"


def _known(data: Mapping[str, Any], cls: type) -> dict[str, Any]:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}


def step_from_dict(data: Mapping[str, Any]) -> StepRecord:
    """未知キーを捨てて復元する。型が違う古い記録でも落ちない。"""
    values = _known(data, StepRecord)
    values["name"] = str(values.get("name") or "")
    artifacts = values.get("artifacts")
    values["artifacts"] = (
        {str(k): str(v) for k, v in artifacts.items()} if isinstance(artifacts, Mapping) else {}
    )
    values["evidence"] = [str(x) for x in (values.get("evidence") or [])]
    for key in _STEP_TEXT:
        values[key] = str(values.get(key) or "")
    values["status"] = values["status"] or "queued"
    return StepRecord(**values)


def run_to_dict(run: ConductorRun) -> dict[str, Any]:
    """JSON 化可能な dict にする（中身は文字列・数・リスト・辞書だけ）。"""
    return asdict(run)


def run_from_dict(data: Mapping[str, Any]) -> ConductorRun:
    """dict から復元する。run_to_dict と対で保守する。"""
    values = _known(data, ConductorRun)
    values["run_id"] = str(values.get("run_id") or "")
    for key in _RUN_TEXT:
        values[key] = str(values.get(key) or "")
    values["status"] = values["status"] or "queued"
    try:
        values["step_index"] = int(values.get("step_index") or 0)
    except (TypeError, ValueError):
        values["step_index"] = 0
    steps = values.get("steps") or []
    values["steps"] = [step_from_dict(s) for s in steps if isinstance(s, Mapping)]
    values["log"] = [str(x) for x in (values.get("log") or [])]
    params = values.get("params")
    values["params"] = dict(params) if isinstance(params, Mapping) else {}
    return ConductorRun(**values)


def save_run(out_dir: Path, run: ConductorRun) -> None:
    """原子的に保存する。実行中に画面が読むため置換で書く。"""
    runs_dir(out_dir).mkdir(parents=True, exist_ok=True)
    path = _run_path(out_dir, run.run_id)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(run_to_dict(run), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    _prune_old_runs(out_dir)


def load_run(out_dir: Path, run_id: str) -> ConductorRun | None:
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
    return sorted(directory.glob("*.json")) if directory.is_dir() else []


def list_runs(out_dir: Path, domain: str = "", limit: int = 50) -> list[ConductorRun]:
    """新しい順に返す。壊れた 1 件で一覧全体を落とさない。"""
    entries: list[tuple[ConductorRun, float]] = []
    for path in _iter_run_files(out_dir):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            run = run_from_dict(data) if isinstance(data, Mapping) else None
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if run is None or (domain and run.domain != domain):
            continue
        entries.append((run, path.stat().st_mtime if path.exists() else 0.0))
    entries.sort(key=lambda e: (e[0].started_at or "", e[1]), reverse=True)
    runs = [run for run, _ in entries]
    return runs[:limit] if limit > 0 else runs


def _prune_old_runs(out_dir: Path) -> None:
    """MAX_RUNS を超えた分を古い順に削除する。無限に溜めない。"""
    files = _iter_run_files(out_dir)
    if len(files) <= MAX_RUNS:
        return
    for path in sorted(files, key=lambda p: p.stat().st_mtime)[: len(files) - MAX_RUNS]:
        try:
            path.unlink()
        except OSError:
            pass


def run_summary(run: ConductorRun) -> dict[str, Any]:
    """一覧表示用の軽量 dict。"""
    current = run.steps[run.step_index] if 0 <= run.step_index < len(run.steps) else None
    return {
        "run_id": run.run_id, "domain": run.domain, "goal": run.goal,
        "status": run.status, "step_index": run.step_index, "step_count": len(run.steps),
        "step_label": current.label if current is not None else "",
        "steps": [{"name": s.name, "label": s.label, "status": s.status,
                   "summary": s.summary} for s in run.steps],
        "human_action": run.human_action, "error": run.error,
        "started_at": run.started_at, "finished_at": run.finished_at, "actor": run.actor,
    }
