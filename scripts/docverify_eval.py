"""System 06 R5: 規則ごとの精度測定（FR-06-170・171・173・174）。

web.services.docverify.checks.candidates を評価セットの 1 文ずつに当て、規則ごとに
適合率・再現率・n を測り quality/docverify_eval/result.json に書く。

- 対象は規則ベースの検出だけ。LLM の指摘（FR-06-119・175）は対象外（送信先に依存し決定的でないため）
- 決定的: 同じ規則・同じ評価セット・同じ --date なら同じ result.json になる
- 回帰（FR-06-173）: 規則の版または評価セットが前回と違えば、前回の値を previous に移し差を delta に書く

使い方: venv/bin/python scripts/docverify_eval.py [--dataset PATH] [--out PATH] [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.services.docverify import checks  # noqa: E402

EVAL_DIR = ROOT / "quality" / "docverify_eval"
DEFAULT_DATASET = EVAL_DIR / "ja_v1.jsonl"
DEFAULT_OUT = EVAL_DIR / "result.json"
RULE_SOURCES = (ROOT / "web/services/docverify/checks.py", ROOT / "web/vendor/reverse_doc/ambiguity.py")

# 評価の単位（規則 ID → checks が出す rule の集合）。曖昧語は語彙の出所で 2 つの ID に分かれるが、
# 注釈者は語彙の出所を区別できないため 1 つにまとめて測る。
RULES: dict[str, tuple[str, ...]] = {
    "AMBIGUOUS": ("RD.AMBIGUOUS", "REQ.AMBIGUOUS_TERM"),
    "REQ.INCOMPLETE": ("REQ.INCOMPLETE",),
    "REQ.OPEN_ENDED": ("REQ.OPEN_ENDED",),
    "REQ.UNIVERSAL": ("REQ.UNIVERSAL",),
    "REQ.AND_OR": ("REQ.AND_OR",),
    "REQ.MEASURABILITY": ("REQ.MEASURABILITY",),
    "REQ.MULTIPLE_REQUIREMENTS": ("REQ.MULTIPLE_REQUIREMENTS",),
}
METHODS = ("injected", "authored", "real")
LIMITS = (
    "評価セットは自作の日本語要求文だけで、実文書（real）の測定はまだ無い。",
    "注釈者は 1 名（AI）で、2 名独立注釈・裁定・Cohen's kappa は未実施。",
    "LLM の指摘は対象外。規則ベースの検出だけを測っている。",
    "文単位の判定で、指摘の位置（どの語か）は照合していない。",
)


def _sha(paths) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(Path(p).read_bytes())
    return h.hexdigest()[:12]


def load_dataset(path: Path) -> list[dict]:
    rows = []
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        unknown = set(row.get("labels") or []) - set(RULES)
        if unknown or row.get("method") not in METHODS or not row.get("text"):
            raise ValueError(f"{path.name} {no} 行目: ラベル・method・text のいずれかが不正です: {sorted(unknown)}")
        rows.append(row)
    return rows


def predict(text: str) -> set[str]:
    """1 文を 1 段落として検査し、出た規則を評価単位に読み替える。"""
    found = {f["rule"] for f in checks.candidates([{"id": "p1", "location": "eval", "text": text}], apply_disabled=False)}
    return {rid for rid, members in RULES.items() if found & set(members)}


def _ratio(num: int, den: int):
    return round(num / den, 3) if den else None


def score(rows: list[dict]) -> dict:
    out = {}
    preds = [(set(r["labels"]), predict(r["text"])) for r in rows]
    for rid in RULES:
        tp = sum(1 for g, p in preds if rid in g and rid in p)
        fp = sum(1 for g, p in preds if rid not in g and rid in p)
        fn = sum(1 for g, p in preds if rid in g and rid not in p)
        out[rid] = {"n": len(rows), "n_gold": tp + fn, "n_predicted": tp + fp, "tp": tp, "fp": fp, "fn": fn,
                    "precision": _ratio(tp, tp + fp), "recall": _ratio(tp, tp + fn)}
    return out


def _delta(cur: dict, prev: dict | None) -> dict | None:
    if not prev:
        return None
    res = {}
    for rid, c in cur.items():
        p = prev.get(rid) or {}
        res[rid] = {k: (round(c[k] - p[k], 3) if c.get(k) is not None and p.get(k) is not None else None)
                    for k in ("precision", "recall")}
    return res


def build(rows: list[dict], dataset: Path, date: str, old: dict | None) -> dict:
    by_method = {}
    for m in METHODS:
        sub = [r for r in rows if r["method"] == m]
        by_method[m] = {"n": len(sub), "rules": score(sub)} if sub else None
    overall = score(rows)
    version, ds_sha = _sha(RULE_SOURCES), _sha([dataset])
    previous = None
    if old:
        same = old.get("rules_version") == version and (old.get("dataset") or {}).get("sha256") == ds_sha
        previous = old.get("previous") if same else {
            "measured_on": old.get("measured_on"), "rules_version": old.get("rules_version"),
            "dataset_sha256": (old.get("dataset") or {}).get("sha256"), "rules": old.get("rules")}
    return {
        "schema": 1,
        "measured_on": date,
        "rules_version": version,
        "scope": "規則ベースの検出のみ（LLM は対象外）",
        "dataset": {"name": dataset.stem, "language": "ja", "n": len(rows), "sha256": ds_sha,
                    "license": "自作文（第三者の著作物を含まない）",
                    "annotation": {"annotators": 1, "annotator_kind": "AI", "adjudicated": False, "kappa": None}},
        "rules": overall,
        "by_method": by_method,
        "previous": previous,
        "delta": _delta(overall, (previous or {}).get("rules")),
        "limits": list(LIMITS),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="System 06 規則別の精度測定")
    ap.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    a = ap.parse_args(argv)
    old = json.loads(a.out.read_text(encoding="utf-8")) if a.out.exists() else None
    result = build(load_dataset(a.dataset), a.dataset, a.date, old)
    a.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for rid, r in result["rules"].items():
        print(f"{rid}\tP={r['precision']}\tR={r['recall']}\tgold={r['n_gold']}\tpred={r['n_predicted']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
