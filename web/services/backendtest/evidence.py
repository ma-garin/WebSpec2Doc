"""System 08 段階 7 の証跡。フォルダ規約・結果の逐次読み取り・junit 解析・スナップショット・ハッシュ。

証跡は <jid>/evidence/<run_id>/ に置く（BD-008 3.1）。
results.jsonl は生成コードの bt_runtime がケース終了ごとに 1 行追記する。途中で止まった実行でも
読めた行までを部分結果として返す（書きかけの最終行は捨てる）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from . import store

RESULTS_FILE = "results.jsonl"
JUNIT_FILE = "junit.xml"
RUN_FILE = "run.json"
MANIFEST_FILE = "manifest.json"
OUTPUT_LIMIT_FILE = "output_limit.json"
OUTPUT_LIMIT_BYTES = 1024 * 1024          # 標準出力＋標準エラーの合計。超えたら実行を止める
MAX_JUNIT_BYTES = 20 * 1024 * 1024
SNAPSHOT_PHASES = ("before", "after", "diff")
_RUN_ID = re.compile(r"^r\d{8}-\d{2,4}$")
_CASE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_log = logging.getLogger(__name__)


def evidence_root(jid: str) -> Path:
    return store.job_dir(jid) / "evidence"


def check_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not _RUN_ID.match(run_id):
        raise KeyError(run_id)
    return run_id


def run_dir(jid: str, run_id: str) -> Path:
    return evidence_root(jid) / check_run_id(run_id)


def new_run_id(root: Path, today: datetime | None = None) -> str:
    """r<YYYYMMDD>-<連番> を返す。連番は同じ日の既存フォルダの次。"""
    day = (today or datetime.now(timezone.utc)).strftime("%Y%m%d")
    prefix = f"r{day}-"
    used = [int(p.name[len(prefix):]) for p in root.glob(prefix + "*")
            if p.is_dir() and p.name[len(prefix):].isdigit()] if root.is_dir() else []
    return f"{prefix}{(max(used) + 1 if used else 1):02d}"


def _atomic_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1, default=str)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        _log.warning("証跡の JSON を読めません: %s (%s)", path.name, exc)
        return None


def read_results(directory: Path) -> list[dict]:
    """results.jsonl を読む。壊れた行・dict でない行は飛ばす（部分結果を優先）。"""
    path = Path(directory) / RESULTS_FILE
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []
    rows: list[dict] = []
    for no, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            _log.info("results.jsonl の %d 行目を読めないため飛ばしました", no)
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _junit_state(case: ET.Element) -> tuple[str, str]:
    for tag, state in (("failure", "fail"), ("error", "error"), ("skipped", "skip")):
        node = case.find(tag)
        if node is not None:
            return state, (node.get("message") or "")[:2000]
    return "pass", ""


def parse_junit(path: Path) -> list[dict]:
    """pytest の junit xml をケースごとの dict にする。無い・大きすぎる・壊れているときは空。"""
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_JUNIT_BYTES:
        return []
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as exc:
        _log.warning("junit xml を読めません: %s", exc)
        return []
    rows = []
    for case in tree.getroot().iter("testcase"):
        state, message = _junit_state(case)
        try:
            seconds = float(case.get("time") or 0)
        except ValueError:
            seconds = 0.0
        rows.append({"classname": case.get("classname") or "", "name": case.get("name") or "",
                     "time": seconds, "state": state, "message": message})
    return rows


def write_snapshot(directory: Path, case: str, phase: str, data) -> Path:
    """<case>/<phase>.json に書く。phase は before / after / diff。"""
    if not isinstance(case, str) or not _CASE.match(case):
        raise store.StoreError("ケース番号の形式が正しくありません。英数字・ハイフン・下線で指定してください。")
    if phase not in SNAPSHOT_PHASES:
        raise store.StoreError("スナップショットの種類が正しくありません。before・after・diff のいずれかを指定してください。")
    path = Path(directory) / case / f"{phase}.json"
    _atomic_json(path, data)
    return path


def write_run(directory: Path, summary: dict) -> None:
    _atomic_json(Path(directory) / RUN_FILE, summary)


def read_run(directory: Path) -> dict | None:
    data = _read_json(Path(directory) / RUN_FILE)
    return data if isinstance(data, dict) else None


def list_runs(root: Path) -> list[dict]:
    """<jid>/evidence 配下の実行の要約（run.json）を run_id 順に返す。"""
    root = Path(root)
    if not root.is_dir():
        return []
    runs = []
    for path in sorted(root.iterdir()):
        if not (path.is_dir() and _RUN_ID.match(path.name)):
            continue
        data = read_run(path) or {"id": path.name, "status": "unknown"}
        runs.append({**data, "results_count": len(read_results(path))})
    return runs


def record_output_limit(directory: Path, stream: str, written: int,
                        limit: int = OUTPUT_LIMIT_BYTES) -> dict:
    """出力量の上限超過で止めたことを記録する。最初の 1 回だけ書く。"""
    path = Path(directory) / OUTPUT_LIMIT_FILE
    existing = _read_json(path)
    if isinstance(existing, dict):
        return existing
    record = {"stream": stream, "written_bytes": int(written), "limit_bytes": int(limit),
              "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "message": f"出力が上限 {limit // 1024} KB を超えたため、以降の出力を保存せず実行を止めました。"}
    _atomic_json(path, record)
    return record


def read_output_limit(directory: Path) -> dict | None:
    data = _read_json(Path(directory) / OUTPUT_LIMIT_FILE)
    return data if isinstance(data, dict) else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest(directory: Path, meta: dict | None = None) -> dict:
    """証跡フォルダ内の全ファイルの sha256 を manifest.json に書き、その内容を返す。"""
    directory = Path(directory)
    files = [{"path": p.relative_to(directory).as_posix(), "sha256": _sha256(p)}
             for p in sorted(directory.rglob("*"))
             if p.is_file() and p.name != MANIFEST_FILE and not p.name.startswith(".tmp-")]
    data = {**(meta or {}), "files": files,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _atomic_json(directory / MANIFEST_FILE, data)
    return data
