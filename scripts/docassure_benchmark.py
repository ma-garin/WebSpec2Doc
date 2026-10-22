#!/usr/bin/env python3
"""Document Assurance 決定論検出の測定。gold fixture / ミューテーション / 敵対 fixture を pipeline.analyze に当てる。

測定値は fixture 件数に依存する。件数は result.json と README.md に必ず明記する（一般化した精度の主張はしない）。
採点: 検出 = finding(FAIL) / conflict / testability(NOT_TESTABLE のみ)。severity=info の未対応検出は FP に数えない。
critical recall = 期待 severity が critical または high の期待のうち検出できた割合。
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
EVAL = ROOT / "quality" / "docassure_eval"


def detect(docs: list[dict]) -> list[dict]:
    from web.services.docassure.pipeline import analyze
    r = analyze([{"id": d["id"], "text": d["text"]} for d in docs])
    lines = {u["requirement_id"]: (u["document_id"], u["location"]["line_start"], u["location"]["line_end"] or u["location"]["line_start"])
             for u in r["requirements"]}
    out = []
    for f in r["findings"]:
        if f["result"] == "FAIL":
            loc = f["location"]
            out.append({"kind": "finding", "rule": f["rule_id"], "spans": [(loc["document_id"], loc["line_start"], loc["line_end"] or loc["line_start"])],
                        "severity": f["severity"]})
    for c in r["conflicts"]:
        out.append({"kind": "conflict", "rule": c["kind"], "severity": c["severity"],
                    "spans": [(e["document_id"], e["location"]["line_start"], e["location"]["line_end"] or e["location"]["line_start"]) for e in c["evidence"]]})
    for key, t in r["testability"].items():
        rid = key.split(":", 1)[-1]   # pipeline のキーは「文書ID:要件ID」
        if t["verdict"] == "NOT_TESTABLE" and rid in lines:
            out.append({"kind": "testability", "rule": "NOT_TESTABLE", "spans": [lines[rid]], "severity": "high"})
    return out


def _hit(d: dict, kind: str, rule: str, doc: str, line) -> bool:
    return d["kind"] == kind and d["rule"] == rule and any(
        s[0] == doc and (line is None or s[1] <= line <= s[2]) for s in d["spans"])


def score_case(case: dict) -> dict:
    dets = detect(case["documents"])
    used: set[int] = set()
    tp, fn = [], []
    for e in case["expected"]:
        idx = next((i for i, d in enumerate(dets) if i not in used and _hit(d, e["kind"], e["rule_or_kind"], e["document_id"], e["line"])), None)
        if idx is None:
            fn.append(e)
        else:
            used.add(idx)
            tp.append(e)
    fp = [d for i, d in enumerate(dets) if i not in used and d["severity"] != "info"]
    mn = [m for m in case["must_not"] if any(_hit(d, m["kind"], m["rule_or_kind"], m["document_id"], m["line"]) for d in dets)]
    n_lines = sum(1 for dd in case["documents"] for l in dd["text"].split("\n") if l.strip())
    return {"id": case["id"], "category": case["category"], "tp": tp, "fn": fn, "fp": fp, "must_not_hits": mn,
            "detections": len(dets), "lines": n_lines}


def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    rd = lambda x: None if x is None else round(x, 3)
    return {"precision": rd(p), "recall": rd(r), "f1": rd(f1), "tp": tp, "fp": fp, "fn": fn}


def aggregate(results: list[dict]) -> dict:
    def agg(rs: list[dict]) -> dict:
        tp = sum(len(r["tp"]) for r in rs); fp = sum(len(r["fp"]) for r in rs); fn = sum(len(r["fn"]) for r in rs)
        crit_exp = [e for r in rs for e in r["tp"] + r["fn"] if e["severity"] in ("critical", "high")]
        crit_tp = [e for r in rs for e in r["tp"] if e["severity"] in ("critical", "high")]
        lines = sum(r["lines"] for r in rs)
        fp_cases = sum(1 for r in rs if r["fp"])
        d = _prf(tp, fp, fn)
        d.update({"cases": len(rs), "critical_recall": round(len(crit_tp) / len(crit_exp), 3) if crit_exp else None,
                  "critical_expected": len(crit_exp), "false_positive_case_rate": round(fp_cases / len(rs), 3) if rs else None,
                  "issue_density_per_100_lines": round(100 * (tp + fp) / lines, 2) if lines else None,
                  "must_not_hits": sum(len(r["must_not_hits"]) for r in rs)})
        return d
    cats: dict[str, list] = defaultdict(list)
    for r in results:
        cats[r["category"]].append(r)
    return {"overall": agg(results), "by_category": {c: agg(rs) for c, rs in sorted(cats.items())}}


BASES = [  # (数値, 別単位表記, 変更後数値, 上限語)
    ("30分", "1800秒", "900秒", "セッション"),
    ("5回", "5回", "3回", "ログイン試行"),
    ("100件", "100件", "50件", "一覧表示"),
]


def _base_docs(n: str, n2: str, topic: str) -> tuple[str, str]:
    h = "# 仕様\n\n## 1 機能\n\n"
    a = (h + f"REQ-001 {topic}の上限は{n}とする。超えたとき、システムはエラーを表示する。\n"
         "REQ-002 管理者のみが設定を変更できる。管理者が保存したとき、システムは完了を表示する。失敗した場合はエラーを表示する。\n"
         "REQ-003 認証済みの場合に限り、ユーザーが送信したとき、システムは結果を表示する。失敗した場合はエラーを表示する。\n")
    b = (h + f"REQ-001 {topic}の上限は{n2}とする。超えたとき、システムはエラーを表示する。\n"
         "REQ-002 管理者のみが設定を変更できる。管理者が保存したとき、システムは完了を表示する。失敗した場合はエラーを表示する。\n"
         "REQ-003 認証済みの場合に限り、ユーザーが送信したとき、システムは結果を表示する。失敗した場合はエラーを表示する。\n")
    return a, b


def mutations() -> list[dict]:
    ms = []
    for n, n2, nm, topic in BASES:
        a, b = _base_docs(n, n2, topic)
        base = [{"id": "A", "text": a}, {"id": "B", "text": b}]
        variants = {
            "timeout_value_change": (b.replace(n2, nm), "conflict"),
            "condition_deleted": (b.replace("認証済みの場合に限り、", ""), None),
            "permission_changed": (b.replace("管理者のみが設定を変更できる", "一般ユーザーも設定を変更できる"), "conflict"),
            "error_path_deleted": (b.replace("失敗した場合はエラーを表示する。", ""), None),
        }
        for name, (mb, kind) in variants.items():
            ms.append({"id": f"{name}:{topic}", "type": name, "base": base, "mutated": [{"id": "A", "text": a}, {"id": "B", "text": mb}],
                       "expect_kind": kind})
    return ms


def run_mutations() -> dict:
    rows = []
    for m in mutations():
        sig = lambda ds: {(d["kind"], d["rule"], tuple(d["spans"][0])) for d in ds}
        base_s = sig(detect(m["base"]))
        new = [d for d in detect(m["mutated"]) if (d["kind"], d["rule"], tuple(d["spans"][0])) not in base_s]
        ok = bool(new) if m["expect_kind"] is None else any(d["kind"] == m["expect_kind"] for d in new)
        rows.append({"id": m["id"], "type": m["type"], "baseline_detections": len(base_s), "detected": ok,
                     "new_detections": [f"{d['kind']}:{d['rule']}" for d in new]})
    by: dict[str, list] = defaultdict(list)
    for r in rows:
        by[r["type"]].append(r["detected"])
    return {"total": len(rows), "detected": sum(r["detected"] for r in rows),
            "detection_rate": round(sum(r["detected"] for r in rows) / len(rows), 3),
            "by_type": {t: {"n": len(v), "detected": sum(v), "rate": round(sum(v) / len(v), 3)} for t, v in by.items()},
            "baseline_clean": all(r["baseline_detections"] == 0 for r in rows), "rows": rows}


def load_cases(root: Path = EVAL / "fixtures") -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(root.glob("*/*.json"))]


def run(write: bool = True) -> dict:
    cases = load_cases()
    results = [score_case(c) for c in cases]
    agg = aggregate(results)
    traps = [r for r in results if r["category"] == "false_positive_trap"]
    res = {"fixtures": {"total_cases": len(cases), "per_category": {c: v["cases"] for c, v in agg["by_category"].items()},
                        "expected_items": sum(len(c["expected"]) for c in cases), "trap_cases": len(traps)},
           **agg,
           "adversarial_traps": {"cases": len(traps), "false_positives": sum(len(r["fp"]) for r in traps),
                                 "must_not_hits": sum(len(r["must_not_hits"]) for r in traps),
                                 "fp_detail": [{"case": r["id"], "fp": [f"{d['kind']}:{d['rule']}" for d in r["fp"]]} for r in traps if r["fp"]]},
           "mutation": run_mutations(),
           "targets": {"precision": 0.98, "critical_recall": 0.95},
           "misses": [{"case": r["id"], "missed": [f"{e['rule_or_kind']}@{e['document_id']}:{e['line']}" for e in r["fn"]]} for r in results if r["fn"]],
           "false_positives": [{"case": r["id"], "fp": [f"{d['kind']}:{d['rule']}" for d in r["fp"]]} for r in results if r["fp"] and r["category"] != "false_positive_trap"],
           "caveat": "自作 fixture での測定値。fixture 件数が少なく、実文書への一般化や他製品との優劣を示すものではない。"}
    o = res["overall"]
    res["targets"]["met"] = {"precision": (o["precision"] or 0) >= 0.98, "critical_recall": (o["critical_recall"] or 0) >= 0.95}
    if write:
        (EVAL / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        (EVAL / "README.md").write_text(render_readme(res), encoding="utf-8")
    return res


def render_readme(r: dict) -> str:
    o, f, m, t = r["overall"], r["fixtures"], r["mutation"], r["adversarial_traps"]
    L = ["# Document Assurance 決定論検出ベンチマーク", "",
         f"- fixture: {f['total_cases']} 件（期待 {f['expected_items']} 項目、トラップ {f['trap_cases']} 件）。LLM は使わない",
         f"- 注意: {r['caveat']}", "- 再生成: `python scripts/docassure_benchmark.py`", "",
         "## 全体", "", f"- precision {o['precision']} / recall {o['recall']} / F1 {o['f1']} / critical recall {o['critical_recall']}"
         f"（対象 {o['critical_expected']} 件）",
         f"- TP {o['tp']} / FP {o['fp']} / FN {o['fn']}、FP を含むケース率 {o['false_positive_case_rate']}、検出密度 {o['issue_density_per_100_lines']} 件/100行",
         f"- 目標（参考値）precision >= {r['targets']['precision']}、critical recall >= {r['targets']['critical_recall']}: "
         f"達成 {r['targets']['met']}", "", "## カテゴリ別", "",
         "| カテゴリ | 件数 | P | R | F1 | critR | FP |", "|---|---|---|---|---|---|---|"]
    for c, v in r["by_category"].items():
        L.append(f"| {c} | {v['cases']} | {v['precision']} | {v['recall']} | {v['f1']} | {v['critical_recall']} | {v['fp']} |")
    L += ["", "## 敵対 fixture（検出してはいけない）", "", f"- {t['cases']} 件中 FP {t['false_positives']} 件、must_not 違反 {t['must_not_hits']} 件", "",
          "## ミューテーション（正常仕様に欠陥を注入）", "",
          f"- {m['total']} 件中 {m['detected']} 件検出（{m['detection_rate']}）。基準仕様の検出 0 件: {m['baseline_clean']}"]
    for k, v in m["by_type"].items():
        L.append(f"  - {k}: {v['detected']}/{v['n']}")
    L += ["", "## 未検出（FN）", ""] + [f"- {x['case']}: {', '.join(x['missed'])}" for x in r["misses"]]
    L += ["", "## 誤検出（FP、トラップ以外）", ""] + [f"- {x['case']}: {', '.join(x['fp'])}" for x in r["false_positives"]]
    if t["fp_detail"]:
        L += ["", "## 誤検出（トラップ）", ""] + [f"- {x['case']}: {', '.join(x['fp'])}" for x in t["fp_detail"]]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    res = run()
    o = res["overall"]
    print(json.dumps({k: o[k] for k in ("precision", "recall", "f1", "critical_recall", "tp", "fp", "fn")}, ensure_ascii=False))
