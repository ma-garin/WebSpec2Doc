"""対検査エンジン（web/services/docverify/pair）を評価セットに通し、予測 JSONL を書く。

使い方:
    venv/bin/python scripts/docverify_pair_predict.py \
        --dataset quality/docverify_eval/pair_v1 --out-defects d.jsonl --out-trace t.jsonl
採点は scripts/docverify_pair_eval.py の --defects / --trace に渡す。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web.services.docverify.pair.engine import inspect  # noqa: E402


def _pairs(dataset: Path) -> list[Path]:
    return sorted(p for p in dataset.iterdir()
                  if (p / "requirements.md").is_file() and (p / "basic_design.md").is_file())


def main() -> int:
    ap = argparse.ArgumentParser(description="対検査エンジンの予測を書き出す")
    ap.add_argument("--dataset", default="quality/docverify_eval/pair_v1")
    ap.add_argument("--out-defects", required=True)
    ap.add_argument("--out-trace", required=True)
    args = ap.parse_args()
    dataset = Path(args.dataset)
    if not dataset.is_dir():
        print(f"評価セットが見つかりません: {dataset}。--dataset を確かめてください", file=sys.stderr)
        return 2
    n_def = n_link = 0
    with open(args.out_defects, "w", encoding="utf-8") as fd, \
            open(args.out_trace, "w", encoding="utf-8") as ft:
        for pair_dir in _pairs(dataset):
            res = inspect((pair_dir / "requirements.md").read_text(encoding="utf-8"),
                          (pair_dir / "basic_design.md").read_text(encoding="utf-8"))
            for e in res["errors"]:
                print(f"検出器の失敗 {pair_dir.name}: {e['detector']} {e['error']}", file=sys.stderr)
            for d in res["defects"]:
                fd.write(json.dumps({"pair": pair_dir.name, **d}, ensure_ascii=False) + "\n")
            for lk in res["links"]:
                ft.write(json.dumps({"pair": pair_dir.name, **lk}, ensure_ascii=False) + "\n")
            n_def += len(res["defects"])
            n_link += len(res["links"])
    print(f"組: {len(_pairs(dataset))}  指摘: {n_def}  リンク: {n_link}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
