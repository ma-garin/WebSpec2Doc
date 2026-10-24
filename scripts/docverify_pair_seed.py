"""対検査レビューの検証データを取り込む。

使い方: venv/bin/python scripts/docverify_pair_seed.py <src_dir> [--iid v1-a-order-payment] [--by 起票者名] [--prev <前版dir>] [--replace <退避先dir>] [--no-test-marks]
既定で検証用の付与（V1-A-01・05 を重大、V1-A-01・03・08 を今回の変更分）を行い meta.json の note に残す。
src_dir には spec_requirements.md・spec_design.md・known_defects.jsonl を置く。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web.services.docverify import pair_review  # noqa: E402

# 検証用の付与（元データの severity は全件空・changed_in_current は無い）。
# 判定の「重大未解決」と「今回の変更分」を通しで確かめるため、指揮官指示（2026-10-24）で付ける。
TEST_CRITICAL = {"V1-A-01", "V1-A-05"}
TEST_CHANGED = {"V1-A-01", "V1-A-03", "V1-A-08"}
TEST_NOTE = ("検証用の付与: V1-A-01・V1-A-05 の重要度を重大、V1-A-01・V1-A-03・V1-A-08 を今回の変更分とした。"
             "元データ（known_defects.jsonl）には無い値。")


def apply_test_marks(iid: str) -> None:
    """取り込み済みの指摘に検証用の重要度・変更分を付け、meta.json に note を残す。"""
    d = pair_review.pair_dir(iid)
    fpath, mpath = d / "findings.json", d / "docs" / "meta.json"
    findings = json.loads(fpath.read_text(encoding="utf-8"))
    marked = [{**f,
               "severity": "重大" if f["id"] in TEST_CRITICAL else f["severity"],
               "changed_in_current": f["id"] in TEST_CHANGED or bool(f.get("changed_in_current"))}
              for f in findings]
    meta = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {}
    pair_review._write(fpath, marked)
    pair_review._write(mpath, {**meta, "note": TEST_NOTE})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--iid", default="v1-a-order-payment")
    ap.add_argument("--by", default="_seed")
    ap.add_argument("--prev")
    ap.add_argument("--no-test-marks", action="store_true", help="検証用の重要度・変更分を付けない")
    ap.add_argument("--replace", metavar="BACKUP_DIR", help="既存の pair/ を BACKUP_DIR へ退避してから取り込む（削除しない）")
    a = ap.parse_args()
    if a.replace:
        cur = pair_review.pair_dir(a.iid)
        if cur.exists():
            dest = Path(a.replace) / f"{a.iid}-pair-{pair_review._now().replace(':', '')}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            cur.rename(dest)
            print(f"退避: {dest}", file=sys.stderr)
    try:
        out = pair_review.seed(a.iid, Path(a.src), a.by, Path(a.prev) if a.prev else None)
        if not a.no_test_marks:
            apply_test_marks(a.iid)
    except pair_review.PairError as e:
        print(e.message, file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
