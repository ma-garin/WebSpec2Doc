"""System 08 の結果の組み立て: bt_runtime の証跡（results.jsonl・before/after.json）を
oracle.evaluate の observed のキーに合わせて判定し、BD-008 3.2 results の形にする。"""
from __future__ import annotations

import json
from pathlib import Path

from web.services.backendtest import evidence, oracle, runner, store

_REQUIRED = {"db_diff": ("before", "after"), "alt_sql": ("expected", "actual"),
             "golden": ("golden", "actual"), "schema": ("violations",)}
_UNRUN = ("not_run", "error", "cancelled")


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _rows_of(snap, oracle_cfg: dict):
    """before.json / after.json（{table: {"rows", "truncated"}}）から判定対象の行。打ち切りは None。"""
    if not isinstance(snap, dict) or not snap:
        return None
    tables = [t for t in oracle_cfg.get("tables") or [] if t in snap] or list(snap)
    entry = snap.get(tables[0]) or {}
    if not isinstance(entry, dict) or entry.get("truncated"):
        return None
    return list(entry.get("rows") or [])


def _order_tables(cfg: dict, before, after) -> list:
    """判定に使うテーブルの順。指定（table）→ 前後で変わったテーブル → 残り。"""
    tables = list(cfg.get("tables") or [])
    b, a = (before if isinstance(before, dict) else {}), (after if isinstance(after, dict) else {})
    changed = [t for t in tables if b.get(t) != a.get(t)]
    return list(dict.fromkeys(([cfg["table"]] if cfg.get("table") else []) + changed + tables))


def _observed(jid: str, case: dict, row: dict) -> dict:
    """bt_runtime の証跡を oracle.evaluate の observed のキーに合わせる。"""
    cfg = case.get("oracle") or {}
    raw = str((row.get("facts") or {}).get("evidence") or "")
    root = store.job_dir(jid).resolve()
    try:
        directory = Path(raw).resolve()
        directory.relative_to(root)
    except (ValueError, OSError):
        return {}
    if not raw or not directory.is_dir():
        return {}
    b_snap, a_snap = _read_json(directory / "before.json"), _read_json(directory / "after.json")
    order = _order_tables(cfg, b_snap, a_snap)
    before, after = _rows_of(b_snap, {**cfg, "tables": order}), _rows_of(a_snap, {**cfg, "tables": order})
    observed: dict = {}
    if before is not None and after is not None:
        observed.update(before=before, after=after)
    if after is not None:
        observed["actual"] = after
    golden_file = Path(str((cfg.get("golden") or {}).get("file") or "")).name
    if golden_file:
        rows = _read_json(root / "code" / "golden" / golden_file)
        if isinstance(rows, list):
            observed["golden"] = rows
    return observed


def _record(jid: str, rid: str, row: dict, case: dict) -> dict:
    facts = row.get("facts") or {}
    observed = _observed(jid, case, row)
    auto = oracle.evaluate(case, observed)
    method = (case.get("oracle") or {}).get("method")
    missing = any(k not in observed for k in _REQUIRED.get(method, ()))
    confirmed = (case.get("oracle") or {}).get("state") in ("auto", "human")
    state = row.get("state")
    if state in _UNRUN:
        pass
    elif auto["verdict"] in ("pass", "fail"):
        state = auto["verdict"]
    elif missing and confirmed and state in ("pass", "fail"):
        auto = {**auto, "rule": "runtime", "reason": "テストコード内の判定を採用しました（証跡から再判定できる値がありません）。"}
    else:
        state = "undetermined"
    counts = (auto.get("detail") or {}).get("counts") or {}
    return {"run": rid, "case": row.get("case"), "state": state,
            "fact": {"rc": facts.get("outcome"), "diff": facts.get("evidence") or "", "observed": counts,
                     "duration": facts.get("duration"), "message": facts.get("message") or ""},
            "auto": {"verdict": auto["verdict"], "rule": auto.get("rule"), "reason": auto.get("reason")},
            "cause": facts.get("reason") or ""}


def records(job: dict, run: dict) -> list[dict]:
    jid, rid = job["id"], run["id"]
    by_id = {str(c.get("id")): c for c in job.get("cases") or []}
    rows = evidence.read_results(evidence.run_dir(jid, rid))
    out = [_record(jid, rid, r, by_id.get(str(r.get("case"))) or {}) for r in rows]
    if run.get("status") not in runner.ACTIVE:
        seen = {str(r["case"]) for r in out}
        state = "cancelled" if run.get("status") == "cancelled" else "not_run"
        out += [{"run": rid, "case": c, "state": state, "fact": {}, "auto": {}, "cause": run.get("reason") or ""}
                for c in run.get("case_ids") or [] if c not in seen]
    return out


def merged(job: dict) -> list[dict]:
    """run を跨いでケースごとに最新の結果。人の判定は同じ run・ケースなら引き継ぐ。"""
    human = {(r.get("run"), r.get("case")): r.get("human") for r in job.get("results") or [] if r.get("human")}
    latest: dict[str, dict] = {}
    for run in job.get("runs") or []:
        for rec in records(job, run):
            h = human.get((rec["run"], rec["case"]))
            latest[str(rec["case"])] = {**rec, "human": h} if h else rec
    return list(latest.values())
