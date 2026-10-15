"""System 08 の結果の組み立て: bt_runtime の証跡（results.jsonl・before/after.json）を
oracle.evaluate の observed のキーに合わせて判定し、BD-008 3.2 results の形にする。"""
from __future__ import annotations

import json
from pathlib import Path

from web.services.backendtest import codegen, evidence, oracle, runner, store

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


def _evidence_dir(jid: str, row: dict):
    """ケースの証跡ディレクトリ（案件フォルダの外・無ければ None）。"""
    raw = str((row.get("facts") or {}).get("evidence") or "")
    root = store.job_dir(jid).resolve()
    try:
        directory = Path(raw).resolve()
        directory.relative_to(root)
    except (ValueError, OSError):
        return None
    return directory if raw and directory.is_dir() else None


def _exit_codes(directory, facts: dict) -> list[int]:
    """対象の終了コード（全回）。facts.rc → rcs.txt → rc.txt（旧版の生成コードは最後の 1 回だけ）。"""
    if isinstance(facts.get("rc"), list):
        return [int(x) for x in facts["rc"]]
    for name in ("rcs.txt", "rc.txt"):
        text = (directory / name).read_text(encoding="utf-8") if directory and (directory / name).is_file() else ""
        if text.strip():
            return [int(x) for x in text.split() if x.lstrip("-").isdigit()]
    return []


def _diff_summary(directory) -> dict:
    """diff.json（{table: {added, removed, updated}}）を種類ごとに合計した実際の差分件数。"""
    data = _read_json(directory / "diff.json") if directory else None
    tables = [d for d in (data or {}).values() if isinstance(d, dict)]
    return {k: sum(len(d.get(k) or []) for d in tables) for k in ("added", "removed", "updated")}


def _diff_tables(directory) -> dict:
    """表ごとの差分件数。判定に使った表以外（出力表など）の変化も事実として見せる（N10）。"""
    data = _read_json(directory / "diff.json") if directory else None
    return {str(t): {k: len(d.get(k) or []) for k in ("added", "removed", "updated")}
            for t, d in (data or {}).items() if isinstance(d, dict)}


def _stderr_tail(directory, limit: int = 300) -> str:
    path = directory / "stderr.txt" if directory else None
    return path.read_text(encoding="utf-8", errors="replace")[-limit:].strip() if path and path.is_file() else ""


def _observed(jid: str, case: dict, row: dict) -> dict:
    """bt_runtime の証跡を oracle.evaluate の observed のキーに合わせる。"""
    cfg = case.get("oracle") or {}
    root = store.job_dir(jid).resolve()
    directory = _evidence_dir(jid, row)
    if directory is None:
        return {}
    b_snap, a_snap = _read_json(directory / "before.json"), _read_json(directory / "after.json")
    order = _order_tables(cfg, b_snap, a_snap)
    before, after = _rows_of(b_snap, {**cfg, "tables": order}), _rows_of(a_snap, {**cfg, "tables": order})
    observed: dict = {}
    if before is not None and after is not None:
        observed.update(before=before, after=after)
    if after is not None:
        observed["actual"] = after
    alt = _read_json(directory / "alt_sql.json") if cfg.get("method") == "alt_sql" else None
    if isinstance(alt, dict):  # 別経路: この起動で変わった行だけを出力側にする（削除は件数だけ）
        observed.update(expected=list(alt.get("expected") or []), actual=list(alt.get("changed") or []),
                        alt_sql={**(alt.get("counts") or {}), "removed": alt.get("removed_count", 0)})
    golden_file = Path(str((cfg.get("golden") or {}).get("file") or "")).name
    if golden_file:
        rows = _read_json(root / "code" / "golden" / golden_file)
        if isinstance(rows, list):
            observed["golden"] = rows
    return observed


def _record(jid: str, rid: str, row: dict, case: dict, ok: list[int] = (0,)) -> dict:
    facts = row.get("facts") or {}
    observed = _observed(jid, case, row)
    directory = _evidence_dir(jid, row)
    rcs, tail = _exit_codes(directory, facts), _stderr_tail(directory)
    bad = [rc for rc in rcs if rc not in ok]
    auto = oracle.evaluate(case, observed)
    method = (case.get("oracle") or {}).get("method")
    missing = any(k not in observed for k in _REQUIRED.get(method, ()))
    confirmed = (case.get("oracle") or {}).get("state") in ("auto", "human")
    state = row.get("state")
    if state in _UNRUN:
        pass
    elif bad:  # 対象が異常終了したケースは、差分の有無に関係なく不合格（冪等性の 2 回目も同じ）
        state, auto = "fail", {"verdict": "fail", "rule": "exit_code",
                               "reason": f"対象の終了コード {bad[0]} は正常（{'・'.join(map(str, ok))}）ではありません。標準エラー: {tail or 'なし'}"}
    elif state == "fail" and auto["verdict"] == "pass":  # テストコード内の不合格を証跡の再判定で覆さない
        auto = {**auto, "verdict": "fail", "rule": "runtime", "reason": "テストコード内の判定が不合格です。"}
    elif auto["verdict"] in ("pass", "fail"):
        state = auto["verdict"]
    elif missing and confirmed and state in ("pass", "fail"):
        auto = {**auto, "rule": "runtime", "reason": "テストコード内の判定を採用しました（証跡から再判定できる値がありません）。"}
    else:
        state = "undetermined"
    counts = (auto.get("detail") or {}).get("counts") or {}
    return {"run": rid, "case": row.get("case"), "state": state,
            "fact": {"rc": (bad or rcs or [None])[-1 if not bad else 0], "rcs": rcs, "outcome": facts.get("outcome"),
                     "stderr_tail": tail, "diff_summary": _diff_summary(directory), "diff_tables": _diff_tables(directory),
                     "business_date": facts.get("business_date"),
                     "diff": facts.get("evidence") or "", "observed": counts, "alt_sql": observed.get("alt_sql"),
                     "duration": facts.get("duration"), "message": facts.get("message") or ""},
            "auto": {"verdict": auto["verdict"], "rule": auto.get("rule"), "reason": auto.get("reason")},
            "cause": f"対象が異常終了しました（終了コード {bad[0]}）" if bad and state == "fail" else facts.get("reason") or ""}


def records(job: dict, run: dict) -> list[dict]:
    jid, rid = job["id"], run["id"]
    by_id = {str(c.get("id")): c for c in job.get("cases") or []}
    rows = evidence.read_results(evidence.run_dir(jid, rid))
    ok = codegen.ok_codes(job)
    out = _with_isolation([_record(jid, rid, r, by_id.get(str(r.get("case"))) or {}, ok) for r in rows])
    if run.get("status") not in runner.ACTIVE:
        seen = {str(r["case"]) for r in out}
        state = "cancelled" if run.get("status") == "cancelled" else "not_run"
        out += [_unrun(rid, c, by_id.get(str(c)) or {}, state, run.get("reason") or "")
                for c in run.get("case_ids") or [] if c not in seen]
    return out


def _unrun(rid: str, cid, case: dict, state: str, reason: str) -> dict:
    """止めた・途中で終わった実行で結果の無いケース。期待値が未確定のケースは元から判定しないので未判定のまま（N11）。"""
    if (case.get("oracle") or {}).get("state") not in ("auto", "human"):
        return {"run": rid, "case": cid, "state": "undetermined", "fact": {}, "auto": {},
                "cause": "期待値が未確定のため判定していません。期待値を確定してから実行してください。"}
    return {"run": rid, "case": cid, "state": state, "fact": {}, "auto": {}, "cause": reason}


def _with_isolation(recs: list[dict]) -> list[dict]:
    """ケースごとに DB を戻さないため、同じ実行で先に動いたケースを事実に残す（差分は各ケースの開始時点が基準。N7）。"""
    prior: list[str] = []
    out = []
    for rec in recs:
        if prior and rec["state"] not in _UNRUN:
            note = (f"同じ実行で先に動いたケース（{'・'.join(prior[-5:])}）の後の DB から始めています。"
                    "前のケースの影響を受ける可能性があります（差分はこのケースの開始時点との比較）。")
            rec = {**rec, "fact": {**rec["fact"], "prior_cases": list(prior), "isolation": note}}
        if rec["state"] not in _UNRUN:
            prior.append(str(rec["case"]))
        out.append(rec)
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
