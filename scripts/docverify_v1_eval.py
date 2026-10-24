"""V1（既知欠陥 A/B/C）で対検査エンジンの検出率を実測する。LLM は使わない（semantic は off）。

使い方:
    venv/bin/python scripts/docverify_v1_eval.py --v1 <evidence/A1/v1> [--out result.json]

照合の規則:
- 指摘の位置 = req_lines → spec_requirements.md、design_lines → spec_design.md の
  その行が属する「## N.」の章番号。既知欠陥の位置 = location と counterpart の各節の章番号
  （「5. テーブル / 9. 再試行」のように複数あれば全部）。
- 文書と章番号が 1 つでも重なり、型が対応すれば一致（TP）。型が違えば「位置のみ一致」。
- 型の対応は TYPE_MAP。EXTRA_IN_DESIGN・UNTESTABLE は V1 の型に対応が無い。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["WEBSPEC2DOC_DOCVERIFY_SEMANTIC"] = "off"  # 埋め込み（LLM）経路を使わない

from web.services.docverify.pair.engine import inspect  # noqa: E402

REQ, DES = "spec_requirements.md", "spec_design.md"
TYPE_MAP = {"CONTRADICTION": "矛盾", "TABLE_MISMATCH": "矛盾", "MISSING_IN_DESIGN": "欠落",
            "AMBIGUOUS": "曖昧", "TERM_INCONSISTENCY": "用語揺れ",
            "EXTRA_IN_DESIGN": "(対応なし:余剰)", "UNTESTABLE": "(対応なし:検証不能)"}
_CH_HEAD = re.compile(r"^##\s+(\d+)\.")
_CH_SEC = re.compile(r"(?:^|/)\s*(\d+)\.")


def chapter_of_lines(md: str) -> list[str]:
    """行番号（1 始まり）→ 章番号。index 0 は未使用。"""
    out, cur = [""], ""
    for line in md.splitlines():
        m = _CH_HEAD.match(line)
        if m:
            cur = m.group(1)
        out.append(cur)
    return out


def _positions(doc: str, span: list[int], chap: list[str]) -> set[tuple[str, str]]:
    if not span:
        return set()
    lo, hi = span[0], span[-1]
    return {(doc, chap[n]) for n in range(lo, min(hi, len(chap) - 1) + 1) if chap[n]}


def finding_positions(d: dict, rch: list[str], dch: list[str]) -> set[tuple[str, str]]:
    return _positions(REQ, d.get("req_lines") or [], rch) | _positions(DES, d.get("design_lines") or [], dch)


def known_positions(k: dict) -> set[tuple[str, str]]:
    pos = set()
    for side in ("location", "counterpart"):
        loc = k.get(side) or {}
        for ch in _CH_SEC.findall(loc.get("section", "")):
            pos.add((loc.get("doc", ""), ch))
    return pos


def evaluate(area: Path) -> dict:
    req_md = (area / REQ).read_text(encoding="utf-8")
    des_md = (area / DES).read_text(encoding="utf-8")
    known = [json.loads(x) for x in (area / "known_defects.jsonl").read_text(encoding="utf-8").splitlines()
             if x.strip()]
    known = [k for k in known if "id" in k]
    res = inspect(req_md, des_md)
    rch, dch = chapter_of_lines(req_md), chapter_of_lines(des_md)
    finds = [{**d, "jtype": TYPE_MAP.get(d["type"], d["type"]),
              "pos": finding_positions(d, rch, dch)} for d in res["defects"]]
    tp, fn, pos_only, matched = [], [], [], set()
    for k in known:
        kp = known_positions(k)
        hits = [i for i, f in enumerate(finds) if f["pos"] & kp and f["jtype"] == k["type"]]
        near = [i for i, f in enumerate(finds) if f["pos"] & kp and f["jtype"] != k["type"]]
        if hits:
            tp.append(k["id"])
            matched.update(hits)
        else:
            fn.append(k)
            if near:
                pos_only.append((k["id"], sorted({finds[i]["type"] for i in near})))
    fp = [f for i, f in enumerate(finds) if i not in matched]
    n_f = len(finds)
    return {"area": area.name, "n_known": len(known), "n_findings": n_f, "tp": len(tp), "fn": len(fn),
            "fp": len(fp), "pos_only": pos_only,
            "recall": len(tp) / len(known) if known else 0.0,
            "precision": len(matched) / n_f if n_f else 0.0,
            "missed": [(k["id"], k["type"], k["location"]["section"]) for k in fn],
            "fp_list": [(f["type"], f.get("req_lines"), f.get("design_lines"), sorted(f["pos"]), f["reason"])
                        for f in fp[:10]],
            "by_type": _count([f["type"] for f in finds]), "errors": res["errors"]}


def _count(xs: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="V1 既知欠陥で対検査エンジンの検出率を測る")
    ap.add_argument("--v1", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()
    root = Path(args.v1)
    areas = sorted(p for p in root.iterdir() if (p / "known_defects.jsonl").is_file()) if root.is_dir() else []
    if not areas:
        print(f"V1 の領域が見つかりません: {root}。--v1 を確かめてください", file=sys.stderr)
        return 2
    results = [evaluate(a) for a in areas]
    for r in results:
        print(f"{r['area']}: 指摘{r['n_findings']} TP={r['tp']} FN={r['fn']} FP={r['fp']} "
              f"位置のみ={len(r['pos_only'])} 再現率={r['recall']:.2f} 適合率={r['precision']:.2f} "
              f"型={r['by_type']} errors={r['errors']}")
    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1, default=list),
                                  encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
