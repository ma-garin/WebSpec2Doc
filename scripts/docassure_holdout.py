#!/usr/bin/env python3
"""holdout 評価セット（quality/docassure_eval/holdout）の測定。benchmark の採点関数を流用し、エンジンは変更しない。

holdout は検出器の実装を見ずに作った自作セット。件数が少なく、過学習の可能性・ラベル誤りの可能性を含む。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docassure_benchmark as b  # noqa: E402

HOLDOUT = b.EVAL / "holdout"


def run(write: bool = True, root: Path = HOLDOUT) -> dict:
    cases = b.load_cases(root)
    results = [b.score_case(c) for c in cases]
    agg = b.aggregate(results)
    res = {"holdout": {"total_cases": len(cases), "expected_items": sum(len(c["expected"]) for c in cases),
                       "per_category": {c: v["cases"] for c, v in agg["by_category"].items()}},
           **agg,
           "misses": [{"case": r["id"], "missed": [f"{e['rule_or_kind']}@{e['document_id']}:{e['line']}" for e in r["fn"]]} for r in results if r["fn"]],
           "false_positives": [{"case": r["id"], "fp": [f"{d['kind']}:{d['rule']}" for d in r["fp"]]} for r in results if r["fp"]],
           "caveat": "自作 holdout（検出器の実装を見ずに作成）。件数が少なく、実文書への一般化や他製品との優劣を示さない。過学習の可能性の確認用で、ルール名のラベル付けに誤りを含みうる。"}
    if write:
        (root / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        (root / "README.md").write_text(render_readme(res), encoding="utf-8")
    return res


def render_readme(r: dict) -> str:
    o, h = r["overall"], r["holdout"]
    L = ["# Document Assurance holdout 測定", "",
         f"- 件数: {h['total_cases']} ケース（期待 {h['expected_items']} 項目）。LLM は使わない",
         "- 注意: 検出器の実装を見ずに作った自作セット。件数が少なく、過学習の可能性・ラベル（rule 名）の付け誤りを含みうる。実文書への一般化や他製品との優劣を示すものではない。",
         "- 再生成: `python scripts/docassure_holdout.py`", "", "## 全体", "",
         f"- precision {o['precision']} / recall {o['recall']} / F1 {o['f1']} / critical recall {o['critical_recall']}（対象 {o['critical_expected']} 件）",
         f"- TP {o['tp']} / FP {o['fp']} / FN {o['fn']}、FP を含むケース率 {o['false_positive_case_rate']}", "",
         "## カテゴリ別", "", "| カテゴリ | 件数 | P | R | F1 | FP |", "|---|---|---|---|---|---|"]
    for c, v in r["by_category"].items():
        L.append(f"| {c} | {v['cases']} | {v['precision']} | {v['recall']} | {v['f1']} | {v['fp']} |")
    L += ["", "## 未検出（FN）", ""] + [f"- {m['case']}: {', '.join(m['missed'])}" for m in r["misses"]]
    L += ["", "## 誤検出（FP）", ""] + [f"- {m['case']}: {', '.join(m['fp'])}" for m in r["false_positives"]]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    res = run()
    print(json.dumps(res["overall"], ensure_ascii=False))
